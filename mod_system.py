"""
mod_system.py — FSBot 模组系统加载器（按服务器隔离版）
负责热加载/卸载 .fsbods 模组文件，支持按 Discord 服务器隔离

依赖：main.py 中已有的 bot, cursor, conn
用法：在 main.py 的 on_ready 中调用 init_mod_system(bot, cursor, conn, mod_sdk)
"""

import json
import os
import inspect
import traceback
import asyncio
import discord
from datetime import datetime

# ── 全局状态 ──
_mod_cache = {}           # {mod_name: {data, file_path}} — 所有已解析的 .fsbods 文件缓存
guild_mod_state = {}      # {guild_id: {mod_name: mod_info}} — 每个服务器已加载的模组
auto_message_tasks = {}   # {(mod_name, guild_id): [task1, ...]}
registered_handlers = {}  # {command_name: (mod_name, cmd_def, options)} — 命令元数据（跨服务器共享）
_reply_cooldowns = {}     # {(channel_id, mod_name, rule_id): last_trigger_time}
MODS_DIR = './mods'

# 向后兼容：loaded_mods 作为只读属性，聚合所有服务器的模组
class _LoadedModsProxy:
    """兼容旧代码的 loaded_mods 代理，返回所有服务器中已加载的模组（去重）"""
    def __bool__(self):
        return any(guild_mod_state.values())
    def __contains__(self, key):
        return any(key in mods for mods in guild_mod_state.values())
    def __iter__(self):
        return iter(self.items())
    def __len__(self):
        return len(self.items())
    def items(self):
        all_mods = {}
        for mods in guild_mod_state.values():
            for mod_name, mod_info in mods.items():
                if mod_name not in all_mods:
                    all_mods[mod_name] = mod_info
        return all_mods.items()
    def keys(self):
        return [k for k, _ in self.items()]
    def values(self):
        return [v for _, v in self.items()]
    def get(self, key, default=None):
        for mods in guild_mod_state.values():
            if key in mods:
                return mods[key]
        return default

loaded_mods = _LoadedModsProxy()

# ── 引用 main 中的全局对象（由 init_mod_system 注入）──
_bot = None
_cursor = None
_conn = None
_mod_sdk = None


def _get_meta(key, default=None):
    """从 bot_meta 表读取"""
    try:
        _cursor.execute("SELECT value FROM bot_meta WHERE key = ?", (key,))
        row = _cursor.fetchone()
        return row[0] if row else default
    except Exception:
        return default


def _set_meta(key, value):
    """写入 bot_meta 表"""
    try:
        _cursor.execute("INSERT OR REPLACE INTO bot_meta (key, value) VALUES (?, ?)", (key, str(value)))
        _conn.commit()
    except Exception as e:
        print(f"[ModSystem] _set_meta 失败: {e}")


def init_mod_system(bot, cursor, conn, mod_sdk_module=None):
    """在 main.py 的 on_ready 中调用，注入全局对象并初始化按服务器隔离的模组系统"""
    global _bot, _cursor, _conn, _mod_sdk
    _bot = bot
    _cursor = cursor
    _conn = conn
    if mod_sdk_module:
        _mod_sdk = mod_sdk_module

    # 创建 guild_mods 表（持久化每个服务器的模组启用状态）
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS guild_mods (
            guild_id INTEGER NOT NULL,
            mod_name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            enabled INTEGER DEFAULT 1,
            loaded_at TEXT,
            PRIMARY KEY (guild_id, mod_name)
        )
    ''')
    conn.commit()

    # 扫描并缓存所有 .fsbods 文件
    scan_mod_files()

    # 迁移：如果 guild_mods 表为空（首次运行），为所有服务器启用所有模组
    cursor.execute("SELECT COUNT(*) FROM guild_mods")
    count = cursor.fetchone()[0]
    if count == 0 and _mod_cache:
        for guild in bot.guilds:
            for mod_name, mod_info in _mod_cache.items():
                cursor.execute(
                    "INSERT OR REPLACE INTO guild_mods (guild_id, mod_name, file_path, enabled, loaded_at) VALUES (?, ?, ?, 1, ?)",
                    (guild.id, mod_name, mod_info['file_path'], datetime.now().isoformat())
                )
        conn.commit()
        print(f"[ModSystem] 首次运行迁移: 已为 {len(bot.guilds)} 个服务器启用 {len(_mod_cache)} 个模组")

    # 为每个服务器加载已启用的模组
    total_loaded = 0
    for guild in bot.guilds:
        loaded = _load_guild_mods_from_db(guild.id, defer_sync=True)
        total_loaded += loaded

    # 统一同步所有服务器的命令
    if bot.guilds:
        asyncio.create_task(_sync_all_guilds())

    print(f"[ModSystem] 模组系统已初始化（按服务器隔离，{len(bot.guilds)} 个服务器，共加载 {total_loaded} 个模组实例）")


def scan_mod_files():
    """扫描 mods/ 目录，缓存所有 .fsbods 文件的解析结果"""
    global _mod_cache
    _mod_cache = {}

    if not os.path.exists(MODS_DIR):
        os.makedirs(MODS_DIR, exist_ok=True)
        print(f"[ModSystem] 创建模组目录: {MODS_DIR}")
        return

    for filename in os.listdir(MODS_DIR):
        if not filename.endswith('.fsbods'):
            continue
        filepath = os.path.join(MODS_DIR, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                mod_data = json.load(f)
            if 'name' not in mod_data:
                print(f"[ModSystem] 跳过 {filename}: 缺少 'name' 字段")
                continue
            mod_name = mod_data['name']
            _mod_cache[mod_name] = {
                'data': mod_data,
                'file_path': filepath,
            }
        except json.JSONDecodeError as e:
            print(f"[ModSystem] 缓存模组 {filename} JSON 错误: {e}")
        except Exception as e:
            print(f"[ModSystem] 缓存模组 {filename} 失败: {e}")

    print(f"[ModSystem] 已缓存 {len(_mod_cache)} 个模组文件")


def _load_guild_mods_from_db(guild_id, defer_sync=False):
    """从数据库加载指定服务器的所有已启用模组。返回加载的模组数量"""
    _cursor.execute(
        "SELECT mod_name FROM guild_mods WHERE guild_id = ? AND enabled = 1",
        (guild_id,)
    )
    rows = _cursor.fetchall()

    loaded_count = 0
    for (mod_name,) in rows:
        if mod_name not in _mod_cache:
            # 文件可能被删除了，标记为禁用
            _cursor.execute(
                "UPDATE guild_mods SET enabled = 0 WHERE guild_id = ? AND mod_name = ?",
                (guild_id, mod_name)
            )
            _conn.commit()
            print(f"[ModSystem] 模组 {mod_name} 文件不存在，已从服务器 {guild_id} 禁用")
            continue
        result = _load_mod_for_guild(mod_name, guild_id, defer_sync=True)
        if result[0]:
            loaded_count += 1
            print(f"[ModSystem] 自动加载成功: {mod_name} (服务器 {guild_id})")
        else:
            print(f"[ModSystem] 自动加载失败 {mod_name}: {result[1]}")

    if not defer_sync and loaded_count > 0:
        asyncio.create_task(_sync_guild(guild_id, force=True))

    return loaded_count


# ══════════════════════════════════════════════
#  加载 / 卸载 / 重载（按服务器隔离）
# ══════════════════════════════════════════════

def _load_mod_for_guild(mod_name, guild_id, defer_sync=False):
    """为指定服务器加载一个模组（从缓存）。返回: (success, message)"""
    global guild_mod_state

    if mod_name not in _mod_cache:
        return False, f"模组 '{mod_name}' 不在模组缓存中"

    if guild_id not in guild_mod_state:
        guild_mod_state[guild_id] = {}

    if mod_name in guild_mod_state[guild_id]:
        return False, f"模组 '{mod_name}' 在此服务器已加载"

    mod_data = _mod_cache[mod_name]['data']

    # 检查依赖（在该服务器的已加载模组中检查）
    deps_result = _check_dependencies(mod_data.get('dependencies'), guild_id)
    if deps_result is not None:
        return False, deps_result

    # 注册斜杠命令（按服务器注册）
    registered_commands = []
    if 'commands' in mod_data:
        for cmd in mod_data['commands']:
            success, msg = _register_mod_command(mod_name, cmd, guild_id)
            if success:
                registered_commands.append(cmd['name'])
            else:
                print(f"[ModSystem] 警告: 注册命令 {cmd.get('name', '?')} 失败: {msg}")

    # 注册自动消息任务
    if 'auto_messages' in mod_data:
        tasks = []
        for msg_def in mod_data['auto_messages']:
            task = asyncio.create_task(_auto_message_loop(mod_name, msg_def, guild_id))
            tasks.append(task)
        auto_message_tasks[(mod_name, guild_id)] = tasks
        print(f"[ModSystem] 模组 {mod_name} 在服务器 {guild_id} 已注册 {len(tasks)} 个自动消息任务")

    guild_mod_state[guild_id][mod_name] = {
        'data': mod_data,
        'file_path': _mod_cache[mod_name]['file_path'],
        'loaded_at': datetime.now().isoformat(),
        'registered_commands': registered_commands,
    }

    if not defer_sync:
        asyncio.create_task(_sync_guild(guild_id, force=True))
    return True, f"模组 '{mod_name}' 加载成功，已注册 {len(registered_commands)} 个命令"


def load_mod_for_guild(mod_name, guild_id):
    """为服务器加载一个模组（从缓存），并更新数据库。返回: (success, message)"""
    if mod_name not in _mod_cache:
        return False, f"模组 '{mod_name}' 不存在于 mods/ 目录"

    if guild_id not in guild_mod_state:
        guild_mod_state[guild_id] = {}

    if mod_name in guild_mod_state[guild_id]:
        return False, f"模组 '{mod_name}' 在此服务器已加载"

    result = _load_mod_for_guild(mod_name, guild_id, defer_sync=False)
    if result[0]:
        # 更新数据库
        _cursor.execute(
            "INSERT OR REPLACE INTO guild_mods (guild_id, mod_name, file_path, enabled, loaded_at) VALUES (?, ?, ?, 1, ?)",
            (guild_id, mod_name, _mod_cache[mod_name]['file_path'], datetime.now().isoformat())
        )
        _conn.commit()

    return result


def unload_mod_from_guild(mod_name, guild_id):
    """从指定服务器卸载模组。返回: (success, message)"""
    global guild_mod_state

    if guild_id not in guild_mod_state or mod_name not in guild_mod_state[guild_id]:
        return False, f"模组 '{mod_name}' 在此服务器未加载"

    # 取消自动消息任务
    if (mod_name, guild_id) in auto_message_tasks:
        for task in auto_message_tasks[(mod_name, guild_id)]:
            task.cancel()
        del auto_message_tasks[(mod_name, guild_id)]
        print(f"[ModSystem] 模组 {mod_name} 在服务器 {guild_id} 的自动消息任务已取消")

    # 检查反向依赖
    for other_name, other_data in guild_mod_state.get(guild_id, {}).items():
        if other_name == mod_name:
            continue
        err = _check_dependencies(other_data['data'].get('dependencies'), guild_id)
        if err and mod_name in err:
            return False, f"模组 '{other_name}' 依赖此模组，无法卸载"

    # 从该服务器的命令树中移除命令
    guild_obj = discord.Object(id=guild_id)
    for cmd_name in guild_mod_state[guild_id][mod_name].get('registered_commands', []):
        try:
            _bot.tree.remove_command(cmd_name, guild=guild_obj)
        except Exception:
            pass

        # 检查是否还有其他服务器在使用此命令名
        still_used = False
        for gid, mods in guild_mod_state.items():
            if gid == guild_id:
                continue
            for mn, mi in mods.items():
                if cmd_name in mi.get('registered_commands', []):
                    still_used = True
                    break
            if still_used:
                break

        if not still_used:
            registered_handlers.pop(cmd_name, None)
            dynamic_func_name = f'_cmd_{cmd_name}'
            if dynamic_func_name in globals():
                del globals()[dynamic_func_name]

    # 更新数据库
    _cursor.execute(
        "UPDATE guild_mods SET enabled = 0 WHERE guild_id = ? AND mod_name = ?",
        (guild_id, mod_name)
    )
    _conn.commit()

    del guild_mod_state[guild_id][mod_name]

    asyncio.create_task(_sync_guild(guild_id, force=True))
    return True, f"模组 '{mod_name}' 已从服务器卸载"


def reload_mod_for_guild(mod_name, guild_id):
    """为服务器重新加载模组。返回: (success, message)"""
    if guild_id not in guild_mod_state or mod_name not in guild_mod_state[guild_id]:
        return False, f"模组 '{mod_name}' 在此服务器未加载"

    # 重新扫描缓存（以防文件被修改）
    scan_mod_files()

    success, msg = unload_mod_from_guild(mod_name, guild_id)
    if not success:
        return False, f"卸载失败: {msg}"

    return load_mod_for_guild(mod_name, guild_id)


def list_mods(guild_id=None):
    """列出已加载的模组。guild_id 不为 None 时返回该服务器的模组"""
    if guild_id is not None:
        return guild_mod_state.get(guild_id, {})
    # 聚合所有服务器的模组（去重）
    all_mods = {}
    for mods in guild_mod_state.values():
        for mod_name, mod_info in mods.items():
            if mod_name not in all_mods:
                all_mods[mod_name] = mod_info
    return all_mods


def list_available_mods():
    """列出所有可用的模组（缓存中的）"""
    return _mod_cache


def is_mod_loaded_in_guild(mod_name, guild_id):
    """检查模组是否在指定服务器已加载"""
    return mod_name in guild_mod_state.get(guild_id, {})


def on_guild_join(guild):
    """当 bot 加入新服务器时调用，初始化空模组状态"""
    if guild.id not in guild_mod_state:
        guild_mod_state[guild.id] = {}
    print(f"[ModSystem] 新服务器 {guild.id} ({guild.name}) 已初始化模组状态（默认无模组）")
    # 同步空命令树（让全局命令生效）
    asyncio.create_task(_sync_guild(guild.id, force=True))


# ══════════════════════════════════════════════
#  依赖检查
# ══════════════════════════════════════════════

def _check_dependencies(deps, guild_id=None):
    """检查依赖是否满足。guild_id 不为 None 时检查该服务器的已加载模组"""
    if not deps:
        return None

    required_deps = []
    if isinstance(deps, list):
        for dep in deps:
            if isinstance(dep, str):
                required_deps.append(dep)
            elif isinstance(dep, dict):
                dep_name = dep.get('name', '')
                dep_type = dep.get('type', 'required')
                if dep_type == 'required' and dep_name:
                    required_deps.append(dep_name)
    elif isinstance(deps, dict):
        required_deps.extend(deps.get('requires', []))

    for dep_name in required_deps:
        if guild_id is not None:
            if dep_name not in guild_mod_state.get(guild_id, {}):
                return f"缺少必需依赖: {dep_name}"
        else:
            if dep_name not in _mod_cache:
                return f"缺少必需依赖: {dep_name}"

    return None


# ══════════════════════════════════════════════
#  命令注册：exec() 动态定义真实函数
#  discord.py 要求回调是"真实"函数对象，
#  用 exec() 在全局作用域定义函数可以满足要求
# ══════════════════════════════════════════════

def _register_mod_command(mod_name, cmd_def, guild_id):
    """
    注册一个模组定义的斜杠命令到指定服务器。
    用 exec() 真正定义一个模块级函数，discord.py 能正确解析参数。
    返回: (success, message)
    """
    global _bot

    try:
        cmd_name = cmd_def['name']
        cmd_description = cmd_def.get('description', f'模组 {mod_name} 的命令')
        options = cmd_def.get('options', [])
        num_opts = len(options)

        if num_opts > 5:
            return False, f"暂不支持超过 5 个参数的命令（当前 {num_opts} 个）"

        # 存储元数据供运行时查找（跨服务器共享）
        registered_handlers[cmd_name] = (mod_name, cmd_def, options)

        # 用 exec() 在全局作用域定义唯一的函数对象（只定义一次）
        func_name = f'_cmd_{cmd_name}'

        if func_name not in globals():
            # 构建参数列表（含类型注解）
            param_parts = ['interaction: discord.Interaction']
            for i, opt in enumerate(options):
                opt_name = opt.get('name', f'p{i}')
                opt_type = _fsbods_type_to_python(opt.get('type', 'str'))
                param_parts.append(f'{opt_name}: {opt_type}')

            params_str = ', '.join(param_parts)

            # 逐行构建函数体 —— defer 必须是第一操作！
            lines = []
            lines.append(f'async def {func_name}({params_str}):')
            lines.append('    try:')
            lines.append('        await interaction.response.defer(ephemeral=True)')
            lines.append('    except Exception:')
            lines.append('        return')
            lines.append(f'    cmd_name_inner = interaction.command.name')
            lines.append(f'    info = registered_handlers.get(cmd_name_inner)')
            lines.append('    if info is None:')
            lines.append('        await interaction.followup.send("❌ 未找到命令 " + cmd_name_inner, ephemeral=True)')
            lines.append('        return')
            lines.append('    mod_name_inner, cmd_def_inner, _ = info')

            if options:
                lines.append('    kwargs = {}')
                for i, opt in enumerate(options):
                    opt_name = opt.get('name', f'p{i}')
                    lines.append(f"    kwargs['{opt_name}'] = {opt_name}")
            else:
                lines.append('    kwargs = {}')

            lines.append(f'    await _mod_dispatch(interaction, cmd_def_inner, kwargs, mod_name_inner)')

            func_code = '\n'.join(lines)
            exec(func_code, globals())

        # 从 globals() 获取函数
        handler = globals()[func_name]

        # 注册为服务器特定命令（guild= 参数使其只在该服务器可见）
        guild_obj = discord.Object(id=guild_id)
        _bot.tree.command(name=cmd_name, description=cmd_description, guild=guild_obj)(handler)

        print(f"[ModSystem] 注册命令: {cmd_name} (来自模组 {mod_name}, 服务器 {guild_id})")
        return True, f"命令 {cmd_name} 注册成功"

    except Exception as e:
        traceback.print_exc()
        return False, str(e)


def _fsbods_type_to_python(type_str):
    """将 .fsbods 中的类型字符串转换为 Python 类型注解字符串"""
    mapping = {
        'str': 'str',
        'string': 'str',
        'int': 'int',
        'integer': 'int',
        'float': 'float',
        'bool': 'bool',
        'boolean': 'bool',
    }
    return mapping.get((type_str or 'str').lower(), 'str')


# ══════════════════════════════════════════════
#  命令分发器（不变）
# ══════════════════════════════════════════════

async def _mod_dispatch(interaction, cmd_def, kwargs, mod_name=''):
    """
    统一的模组命令分发器。
    注意: 调用此函数前必须已 defer（由 exec 生成的处理函数负责）。
    所有回复通过 followup.send 发送。
    """
    try:
        # ── 情况 1：静态响应（无 action，有 response）──
        if 'action' not in cmd_def or not cmd_def.get('action'):
            response_data = cmd_def.get('response')
            if response_data:
                text = _resolve_response(response_data, {})
                await _send_reply(interaction, text)
            else:
                await _send_reply(interaction, "✅ 执行成功")
            return

        # ── 情况 2/3：有 action ──
        action = cmd_def['action']

        # 情况 2：字典格式的 action
        if isinstance(action, dict):
            result_text = await _execute_dict_action(interaction, action, kwargs, mod_name)
            if result_text is not None:
                await _send_reply(interaction, result_text)
            return

        # 情况 3：字符串格式（legacy sdk.xxx）
        if isinstance(action, str):
            result = _execute_string_action(interaction, action)
            if result is None or result is True:
                await _send_reply(interaction, "✅ 执行成功")
            elif isinstance(result, str):
                await _send_reply(interaction, result)
            else:
                await _send_reply(interaction, f"✅ {result}")
            return

        # 未知格式
        await _send_reply(interaction, "✅ 命令执行完成")

    except Exception as e:
        print(f"[ModSystem] 执行命令 {interaction.command.name} 出错: {e}")
        traceback.print_exc()
        try:
            await _send_reply(interaction, f"❌ 错误: {e}")
        except Exception:
            pass


async def _execute_dict_action(interaction, action_def, user_kwargs, mod_name=''):
    """执行字典格式的 action：调用 SDK 函数并格式化响应

    自动注入机制：SDK 函数的 user_id / mod_name / guild_id 参数若未在 args 中显式声明，
    则根据函数签名自动注入 interaction.user.id / 模组名 / interaction.guild_id。
    模组作者只需在 args 中列出用户提供的参数（如 amount, item_id 等）。
    """
    func_name = action_def.get('function', '')
    raw_args = action_def.get('args', [])
    response_tpl = action_def.get('response', '')

    # 解析参数列表，替换变量引用（{"var": "user_id"} 等）
    resolved_args = []
    explicit_vars = set()  # 记录显式声明的变量名
    for arg in raw_args:
        if isinstance(arg, dict):
            var_name = arg.get('var', '')
            if var_name == 'user_id':
                resolved_args.append(interaction.user.id)
                explicit_vars.add('user_id')
            elif var_name == 'guild_id':
                resolved_args.append(interaction.guild_id or 0)
                explicit_vars.add('guild_id')
            elif var_name == 'mod_name':
                resolved_args.append(mod_name)
                explicit_vars.add('mod_name')
            else:
                resolved_args.append(arg.get('default', ''))
        else:
            resolved_args.append(arg)

    # 调用 SDK 函数
    result_value = None
    error_msg = None

    if func_name and _mod_sdk and hasattr(_mod_sdk, func_name):
        func = getattr(_mod_sdk, func_name)
        try:
            # 自动注入 user_id / mod_name / guild_id
            # 遍历函数签名，对未显式声明的特殊参数自动注入
            sig = inspect.signature(func)
            params = list(sig.parameters.values())
            final_args = []
            resolved_idx = 0

            for param in params:
                # 跳过 *args / **kwargs
                if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                    break

                pname = param.name
                if pname == 'user_id' and 'user_id' not in explicit_vars:
                    final_args.append(interaction.user.id)
                elif pname == 'mod_name' and 'mod_name' not in explicit_vars:
                    final_args.append(mod_name)
                elif pname == 'guild_id' and 'guild_id' not in explicit_vars:
                    final_args.append(interaction.guild_id or 0)
                elif resolved_idx < len(resolved_args):
                    final_args.append(resolved_args[resolved_idx])
                    resolved_idx += 1
                elif param.default is not param.empty:
                    # 有默认值的参数，不传则使用默认值
                    pass
                else:
                    # 必需参数缺失
                    break

            result_value = func(*final_args)
        except Exception as e:
            error_msg = f"❌ SDK 函数 {func_name} 执行失败: {e}"
            print(f"[ModSystem] {error_msg}")
    elif func_name and not (_mod_sdk and hasattr(_mod_sdk, func_name)):
        error_msg = f"❌ 找不到 SDK 函数: {func_name}"

    # 格式化响应模板
    if response_tpl:
        format_dict = {'result': result_value}
        format_dict.update(user_kwargs)
        text = _resolve_response(response_tpl, format_dict)
        if error_msg:
            text = f"{error_msg}\n{text}"
        return text

    return error_msg or f"✅ 执行完成"


def _execute_string_action(interaction, action_str):
    """执行字符串格式的 action（旧 sdk.xxx 格式）"""
    if not action_str:
        return "✅ 命令执行成功"

    if action_str.startswith('sdk.') and _mod_sdk:
        func_name = action_str[4:]
        if hasattr(_mod_sdk, func_name):
            func = getattr(_mod_sdk, func_name)
            try:
                return func(interaction.user.id)
            except Exception as e:
                return f"❌ SDK 函数 {func_name} 执行失败: {e}"
        return f"❌ 找不到 SDK 函数: {func_name}"

    return f"✅ 命令执行成功"


def _resolve_response(response_data, format_dict=None):
    """
    解析响应数据，支持多语言和模板变量。
    格式：
      - 字符串: "你好"
      - 多语言字典: {"zh": "你好", "en": "Hello"}
    模板变量用 Python format()，如 "{result}"
    """
    if format_dict is None:
        format_dict = {}

    if isinstance(response_data, dict):
        # 尝试按语言获取文本（默认中文）
        text = response_data.get('zh', response_data.get('en', ''))
    elif isinstance(response_data, str):
        text = response_data
    else:
        text = str(response_data)

    # 安全地替换模板变量
    try:
        if text and '{' in text:
            return text.format(**format_dict)
    except (KeyError, IndexError, ValueError):
        pass  # 模板变量缺失时返回原文

    return text


async def _send_reply(interaction, content):
    """
    在已 defer 的 interaction 上发送回复（必须用 followup）。
    此函数必须在 _mod_dispatch 中 defer 成功之后调用。
    """
    try:
        await interaction.followup.send(content, ephemeral=True)
    except discord.errors.NotFound:
        print(f"[ModSystem] 警告: 交互已过期无法发送回复")
    except Exception as e:
        print(f"[ModSystem] 发送回复失败: {e}")


def _execute_action(mod_name, action, interaction, kwargs):
    """执行模组命令的 action（保留以供兼容）"""
    if not action:
        return f"✅ 模组 {mod_name} 命令执行成功"

    if action.startswith('sdk.') and _mod_sdk:
        func_name = action[4:]
        if hasattr(_mod_sdk, func_name):
            func = getattr(_mod_sdk, func_name)
            try:
                return func(interaction.user.id, **kwargs)
            except Exception as e:
                return f"❌ SDK 函数 {func_name} 执行失败: {e}"
        return f"❌ 找不到 SDK 函数: {func_name}"

    return f"✅ 模组 {mod_name} 的命令执行成功"


# ══════════════════════════════════════════════
#  命令同步（按服务器）
# ══════════════════════════════════════════════

async def _sync_guild(guild_id, force=False):
    """同步指定服务器的命令树

    Args:
        guild_id: 服务器 ID
        force: True=强制同步（load/unload/reload 时用），False=检查今日是否已同步（init 时用）
    """
    from datetime import date
    today = date.today().isoformat()
    meta_key = f'guild_sync_{guild_id}_date'

    if not force:
        last = _get_meta(meta_key)
        if last == today:
            print(f"[ModSystem] 服务器 {guild_id} 今日已同步，跳过")
            return

    try:
        guild_obj = discord.Object(id=guild_id)
        synced = await _bot.tree.sync(guild=guild_obj)
        _set_meta(meta_key, today)
        print(f"[ModSystem] 服务器 {guild_id} 同步了 {len(synced)} 个命令")
    except Exception as e:
        print(f"[ModSystem] 同步服务器 {guild_id} 命令失败: {e}")


async def _sync_all_guilds():
    """同步所有服务器的命令树（init 时调用，会检查今日是否已同步）"""
    for guild in _bot.guilds:
        await _sync_guild(guild.id, force=False)


async def _sync_commands():
    """兼容旧代码：同步所有服务器的命令树"""
    await _sync_all_guilds()


# ══════════════════════════════════════════════
#  自动消息循环（按服务器隔离）
# ══════════════════════════════════════════════

async def _auto_message_loop(mod_name, msg_def, guild_id):
    """自动消息循环（检查 guild 启用状态）"""
    interval = int(msg_def.get('interval', 3600))
    channel_id = msg_def.get('channel_id')
    message_template = msg_def.get('message', '')
    task_name = msg_def.get('name', '?')

    if not channel_id:
        print(f"[ModSystem] 警告: 自动消息 '{task_name}' 缺少 channel_id，已跳过")
        return

    print(f"[ModSystem] 自动消息 '{task_name}' 已启动，间隔 {interval} 秒，频道 {channel_id}，服务器 {guild_id}")

    while True:
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            print(f"[ModSystem] 自动消息 '{task_name}' 已取消")
            break

        # 检查模组是否仍在此服务器启用
        if guild_id not in guild_mod_state or mod_name not in guild_mod_state.get(guild_id, {}):
            print(f"[ModSystem] 自动消息 '{task_name}' 停止: 模组已从服务器 {guild_id} 卸载")
            break

        now = datetime.now()
        message = message_template.replace('{date}', now.strftime('%Y-%m-%d'))
        message = message.replace('{time}', now.strftime('%H:%M:%S'))
        message = message.replace('{datetime}', now.strftime('%Y-%m-%d %H:%M:%S'))
        message = message.replace('{mod_name}', mod_name)

        try:
            ch = _bot.get_channel(int(channel_id))
            if ch:
                await ch.send(message)
            else:
                print(f"[ModSystem] 警告: 找不到频道 {channel_id}")
        except Exception as e:
            print(f"[ModSystem] 自动消息 '{task_name}' 发送失败: {e}")


# ══════════════════════════════════════════════
#  消息处理（按服务器隔离）
# ══════════════════════════════════════════════

async def handle_message(message):
    """
    处理消息规则（keyword_reply / message_rules）— 只处理消息所在服务器的已启用模组。
    在 main.py 的 on_message 里调用：await mod_system.handle_message(message)

    模组格式支持：

    "keyword_reply": [
      {
        "keywords": ["垃圾", "广告"],         # 消息含这些词时触发（任一匹配）
        "watch_users": [123456789],             # 可选：只监控这些用户ID（省略=监控所有人）
        "exempt_roles": [987654321],            # 可选：拥有这些身份组ID的用户豁免此规则
        "action": "mute",                       # "mute" / "warn" / "reply" / "delete_and_dm"
        "duration": 60,                         # mute时长（秒），仅action=mute时有效
        "reason": "违反规则",                   # 禁言原因
        "reply": "你违反了规则！"               # action=reply/warn 时回复的内容
      }
    ]
    """
    if not message.guild:
        return

    guild_id = message.guild.id
    active_mods = guild_mod_state.get(guild_id, {})

    if not active_mods:
        return

    content = message.content.lower() if message.content else ''
    author_id = message.author.id

    for mod_name, mod_info in active_mods.items():
        mod_data = mod_info.get('data', {})
        keyword_rules = mod_data.get('keyword_reply', [])
        if not keyword_rules:
            continue

        for rule in keyword_rules:
            try:
                # 检查是否限定监控用户
                watch_users = rule.get('watch_users', [])
                if watch_users and author_id not in watch_users:
                    continue

                # 检查豁免身份组（拥有豁免身份组的用户跳过此规则）
                exempt_roles = rule.get('exempt_roles', [])
                if exempt_roles and message.guild:
                    skip = False
                    for role_id in exempt_roles:
                        role = message.guild.get_role(role_id)
                        if role and role in message.author.roles:
                            skip = True
                            break
                    if skip:
                        continue

                # 检查关键词匹配
                keywords = rule.get('keywords', [])
                matched = False
                if keywords:
                    matched = any(kw.lower() in content for kw in keywords)
                else:
                    # 无关键词 = 匹配所有消息（用于全局用户监控）
                    matched = True

                if not matched:
                    continue

                action = rule.get('action', 'reply')

                # ── 频道级冷却检查（仅 reply/warn，mute/delete 不受影响）──
                if action in ('reply', 'warn'):
                    cooldown_sec = int(rule.get('cooldown', 300))  # 默认 5 分钟
                    _cd_key = (message.channel.id, mod_name, id(rule))
                    _now_ts = datetime.now().timestamp()
                    _last_trigger = _reply_cooldowns.get(_cd_key, 0)
                    if _now_ts - _last_trigger < cooldown_sec:
                        # 冷却中，跳过
                        continue

                # ── action: reply ──
                if action == 'reply':
                    reply_text = rule.get('reply', '⚠️ 注意规则！')
                    try:
                        await message.channel.send(f"{message.author.mention} {reply_text}")
                        _reply_cooldowns[(message.channel.id, mod_name, id(rule))] = datetime.now().timestamp()
                    except Exception as e:
                        print(f"[ModSystem] keyword_reply 回复失败: {e}")

                # ── action: warn ──
                elif action == 'warn':
                    reply_text = rule.get('reply', '⚠️ 警告：你的消息违反了规则！')
                    try:
                        await message.channel.send(f"{message.author.mention} ⚠️ {reply_text}")
                        _reply_cooldowns[(message.channel.id, mod_name, id(rule))] = datetime.now().timestamp()
                    except Exception as e:
                        print(f"[ModSystem] keyword_reply warn 失败: {e}")

                # ── action: mute ──
                elif action == 'mute':
                    duration_sec = int(rule.get('duration', 60))
                    reason = rule.get('reason', f'违反规则 (模组: {mod_name})')
                    reply_text = rule.get('reply', f'⏱️ 你已被禁言 {duration_sec} 秒：{reason}')
                    try:
                        import datetime as _dt
                        mute_until = _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(seconds=duration_sec)
                        member = message.author
                        # 必须是 guild 成员且有禁言权限
                        if hasattr(member, 'timeout') and message.guild:
                            await member.timeout(mute_until, reason=reason)
                            await message.channel.send(f"{message.author.mention} {reply_text}")
                            print(f"[ModSystem] 已禁言 {member} {duration_sec}s，原因: {reason}")
                        else:
                            print(f"[ModSystem] 无法禁言: 非guild成员或无权限")
                    except discord.Forbidden:
                        print(f"[ModSystem] 禁言 {message.author} 失败: 权限不足")
                    except Exception as e:
                        print(f"[ModSystem] 禁言操作失败: {e}")

                # ── action: delete_and_dm ──
                elif action == 'delete_and_dm':
                    reason = rule.get('reason', f'违反规则 (模组: {mod_name})')
                    dm_title = rule.get('dm_title', '⚠️ 消息已被删除 — 违规通知')
                    dm_text = rule.get('reply', reason)
                    try:
                        # 1. 删除违规消息
                        await message.delete()
                        print(f"[ModSystem] 已删除 {message.author} 的违规消息，原因: {reason}")
                    except discord.Forbidden:
                        print(f"[ModSystem] 删除消息失败: 权限不足（需要 Manage Messages 权限）")
                    except discord.NotFound:
                        print(f"[ModSystem] 删除消息失败: 消息已不存在")
                    except Exception as e:
                        print(f"[ModSystem] 删除消息失败: {e}")

                    # 2. DM 通知用户
                    try:
                        embed = discord.Embed(
                            title=dm_title,
                            description=dm_text,
                            color=discord.Color.orange(),
                            timestamp=message.created_at
                        )
                        embed.add_field(name="原始消息", value=message.content[:1024] or "(空/仅附件)", inline=False)
                        embed.set_footer(text=f"模组: {mod_name} | 服务器: {message.guild.name} | FSBot 自律监管")
                        await message.author.send(embed=embed)
                    except discord.Forbidden:
                        print(f"[ModSystem] DM 发送失败: {message.author} 禁止私信或已屏蔽")
                    except Exception as e:
                        print(f"[ModSystem] DM 发送失败: {e}")

            except Exception as e:
                print(f"[ModSystem] 处理消息规则 [{mod_name}] 出错: {e}")


__all__ = [
    'init_mod_system',
    'scan_mod_files',
    'load_mod_for_guild',
    'unload_mod_from_guild',
    'reload_mod_for_guild',
    'list_mods',
    'list_available_mods',
    'is_mod_loaded_in_guild',
    'on_guild_join',
    'guild_mod_state',
    'loaded_mods',
    'handle_message',
    'MODS_DIR',
]
