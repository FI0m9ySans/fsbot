"""
FSBot AI Chat 模块
使用智谱AI (GLM-4-Flash) 实现对话功能
命令: .aichat <消息>  /  .aichat clear  /  .aichat
对话历史在 bot 运行期间持久保持, 每个用户独立
系统上下文 (命令列表/数据库结构等) 每次启动后仅构建一次
"""

import asyncio
import aiohttp
import json
import os
import re
import sqlite3
import datetime
import discord

# ── 智谱AI 配置 ──
ZHIPU_API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
ZHIPU_MODEL = "glm-4-flash"
ZHIPU_API_KEY = ""

# ── 运行时状态 ──
_system_context: str = ""          # 系统提示词 (启动后构建一次)
_conversations: dict = {}          # {user_id: [{"role":..., "content":...}, ...]}
_stats: dict = {}                  # {user_id: {"turns", "prompt_tokens", "completion_tokens", "total_tokens", "first_used", "last_used"}}
_initialized: bool = False
MAX_HISTORY = 20                   # 每用户最多保留 20 轮对话 (不含 system)
MAX_RETRIES = 3                    # API 调用最大重试次数

def _load_api_key():
    """从 ai_key.txt 读取 API Key"""
    global ZHIPU_API_KEY
    key_file = "ai_key.txt"
    if os.path.exists(key_file):
        with open(key_file, "r", encoding="utf-8") as f:
            ZHIPU_API_KEY = f.read().strip()
    else:
        # 回退: 环境变量
        ZHIPU_API_KEY = os.environ.get("ZHIPU_API_KEY", "")
    return bool(ZHIPU_API_KEY)

def _build_system_context(bot) -> str:
    """构建系统上下文: 命令列表 + 数据库结构 + 功能说明"""
    lines = []
    lines.append("你是 FSBot 的 AI 助手，运行在一个 Discord 机器人中。")
    lines.append("你的任务是帮助用户了解机器人的功能、回答问题、提供建议。")
    lines.append("请用简洁友好的中文回答，支持使用 Markdown 格式。")
    lines.append("")
    lines.append("=== 机器人基本信息 ===")
    lines.append(f"Bot 名称: {bot.user.name if bot.user else 'FSBot'}")
    lines.append(f"所在服务器数: {len(bot.guilds)}")
    lines.append(f"总成员数: {sum(g.member_count or 0 for g in bot.guilds)}")
    lines.append("")

    # ── 斜杠命令 (/) ──
    lines.append("=== 斜杠命令 (/) ===")
    slash_cmds = []
    for cmd in bot.tree.walk_commands():
        if hasattr(cmd, 'description') and cmd.description:
            slash_cmds.append(f"/{cmd.name} — {cmd.description}")
        else:
            slash_cmds.append(f"/{cmd.name}")
    # 去重并排序
    for c in sorted(set(slash_cmds)):
        lines.append(f"  {c}")
    lines.append("")

    # ── 前缀命令 (!) ──
    lines.append("=== 前缀命令 (!) ===")
    prefix_cmds = []
    for cmd in bot.commands:
        if cmd.hidden:
            continue
        desc = cmd.help or cmd.short_doc or ""
        prefix_cmds.append(f"!{cmd.name}" + (f" — {desc}" if desc else ""))
    for c in sorted(set(prefix_cmds)):
        lines.append(f"  {c}")
    lines.append("")

    # ── 数据库表结构 ──
    lines.append("=== 数据库结构 (SQLite) ===")
    try:
        conn = sqlite3.connect("users.db", timeout=5)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [row[0] for row in cursor.fetchall()]
        for table in tables:
            cursor.execute(f"PRAGMA table_info({table})")
            cols = cursor.fetchall()
            col_info = ", ".join(f"{c['name']}({c['type']})" for c in cols)
            lines.append(f"  表 {table}: {col_info}")
        conn.close()
    except Exception as e:
        lines.append(f"  (读取数据库失败: {e})")
    lines.append("")

    # ── 功能模块说明 ──
    lines.append("=== 功能模块 ===")
    lines.append("1. 用户系统: 经验值/等级/签到, 每日签到得积分, 聊天获经验")
    lines.append("2. 积分系统: 永久积分(points, 商店/转账用) + 月度积分(monthly_points, 排行榜用, 每月清零)")
    lines.append("3. 天赋系统: 4种天赋(力量/幸运/勤奋/智慧), 影响游戏/经验/签到收益")
    lines.append("4. 商店: /pointshop 查看商品, /redeem 兑换, /transfer 转账")
    lines.append("5. 小游戏: 猜拳/猜数/骰子/轮盘赌/摇奖机/成语接龙/扫雷/UNO/狼人杀/俄罗斯轮盘")
    lines.append("6. 棋盘游戏: 重力四子棋/五子棋/围棋/跳棋/斗兽棋/飞行棋/中国象棋/国际象棋 (赢方+20积分)")
    lines.append("7. 路墙棋 (Quoridor): 支持自定义规则和4人模式")
    lines.append("8. 音乐机器人: !play !search !batch !skip !stop !pause !resume !queue !volume !speed !loop 等")
    lines.append("   - 支持 Bilibili 搜索/au号/URL, YouTube URL")
    lines.append("   - !speed 调倍速 (0.25~4.0x), !volume 调音量")
    lines.append("9. 模组系统: .fsbods 格式, 支持新增命令/自动消息/关键词回复, 按服务器隔离")
    lines.append("   - /listmods /loadmod /unloadmod /reloadmod /uploadmods /modscreatetutorial")
    lines.append("10. 红包系统: /redpacket create, 二倍均值法, 24h过期退款")
    lines.append("11. 跨服桥接: /bridge_create /bridge_connect 等, 跨服务器消息转发")
    lines.append("12. Web Dashboard: http://localhost:8080, 查看服务器/用户/模组信息")
    lines.append("13. 新手教程: /tutorial (6页分页, 多语言 zh/ja/fr/en)")
    lines.append("14. AI 聊天: .aichat (本功能)")
    lines.append("")
    lines.append("=== 升级公式 ===")
    lines.append("线性: Lv0→1需100EXP, 每级递增100EXP (Lv N→N+1 需 100*(N+1) EXP)")
    lines.append("")
    lines.append("=== 注意事项 ===")
    lines.append("- 回答用户关于机器人功能的问题时, 请给出具体命令")
    lines.append("- 如果用户问的超出机器人功能范围, 可以正常聊天但提醒这是机器人助手")
    lines.append("- 不要编造不存在的命令或功能")
    lines.append("- 如果用户要求你艾特/提及(@)某人, 请用 [@用户名] 格式 (如 [@花衫]), 系统会自动解析为 Discord 艾特")
    lines.append("- 用户名应使用该用户的昵称或用户名, 系统会精确匹配后再模糊匹配")

    return "\n".join(lines)


async def init_ai_chat(bot):
    """初始化 AI 聊天模块 (在 on_ready 中调用, 仅执行一次)"""
    global _system_context, _initialized

    if _initialized:
        return

    if not _load_api_key():
        print("[AIChat] ⚠️ 未找到 API Key, 请创建 ai_key.txt 文件")
        return

    _system_context = _build_system_context(bot)
    _initialized = True
    print(f"[AIChat] 系统上下文已构建 ({len(_system_context)} 字符)")


def _get_conversation(user_id: int, username: str) -> list:
    """获取用户的对话历史, 不存在则创建"""
    if user_id not in _conversations:
        _conversations[user_id] = [
            {"role": "system", "content": _system_context},
            {"role": "system", "content": f"当前用户: {username} (ID: {user_id})"},
        ]
    return _conversations[user_id]


def _trim_conversation(user_id: int):
    """裁剪对话历史, 保留最近 MAX_HISTORY 条 (不含 system 消息)"""
    conv = _conversations.get(user_id, [])
    # 保留所有 system 消息 + 最近 MAX_HISTORY 条非 system 消息
    system_msgs = [m for m in conv if m["role"] == "system"]
    other_msgs = [m for m in conv if m["role"] != "system"]
    if len(other_msgs) > MAX_HISTORY * 2:  # 每轮 = user + assistant
        other_msgs = other_msgs[-(MAX_HISTORY * 2):]
    _conversations[user_id] = system_msgs + other_msgs


async def _get_dynamic_context(message, bot) -> str:
    """获取动态上下文: 当前频道名 + 最近消息摘要 (每次调用时生成)"""
    lines = []
    lines.append("=== 当前上下文 ===")
    guild_name = message.guild.name if message.guild else "私聊"
    channel_name = getattr(message.channel, "name", "DM")
    lines.append(f"服务器: {guild_name}")
    lines.append(f"频道: #{channel_name}")

    # 最近几条消息摘要 (排除当前 .aichat 消息和 bot 消息)
    try:
        recent = []
        async for msg in message.channel.history(limit=6, before=message):
            if msg.author.bot:
                continue
            text = msg.content.strip()
            if not text:
                continue
            author = msg.author.display_name
            if len(text) > 100:
                text = text[:100] + "..."
            recent.append(f"{author}: {text}")
        if recent:
            lines.append("最近对话 (从新到旧):")
            for r in recent[:5]:
                lines.append(f"  {r}")
    except Exception:
        pass  # 无权限读历史等，静默跳过

    return "\n".join(lines)


def _update_stats(user_id: int, usage: dict):
    """更新用户统计"""
    if user_id not in _stats:
        _stats[user_id] = {
            "turns": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "first_used": "",
            "last_used": "",
        }
    s = _stats[user_id]
    s["turns"] += 1
    s["prompt_tokens"] += usage.get("prompt_tokens", 0)
    s["completion_tokens"] += usage.get("completion_tokens", 0)
    s["total_tokens"] += usage.get("total_tokens", 0)
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    if not s["first_used"]:
        s["first_used"] = now
    s["last_used"] = now


async def _call_zhipu_api(messages: list) -> tuple:
    """
    调用智谱AI API, 返回 (回复文本, usage统计)
    遇到 429/5xx/超时/网络错误时自动指数退避重试
    """
    headers = {
        "Authorization": f"Bearer {ZHIPU_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": ZHIPU_MODEL,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 1024,
    }

    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(ZHIPU_API_URL, headers=headers, json=payload) as resp:
                    if resp.status == 429 or resp.status >= 500:
                        # 可重试错误 (限流 / 服务器内部错误)
                        error_text = await resp.text()
                        last_error = Exception(f"API 返回 {resp.status}: {error_text[:200]}")
                        if attempt < MAX_RETRIES:
                            wait = 2 ** attempt  # 1s, 2s, 4s
                            print(f"[AIChat] API {resp.status}, 第 {attempt+1} 次重试 (等待 {wait}s)")
                            await asyncio.sleep(wait)
                            continue
                        raise last_error
                    if resp.status != 200:
                        error_text = await resp.text()
                        raise Exception(f"API 返回 {resp.status}: {error_text[:200]}")
                    data = await resp.json()
                    reply = data["choices"][0]["message"]["content"]
                    usage = data.get("usage", {})
                    return reply, usage
        except asyncio.TimeoutError:
            last_error = asyncio.TimeoutError("API 请求超时")
            if attempt < MAX_RETRIES:
                wait = 2 ** attempt
                print(f"[AIChat] 超时, 第 {attempt+1} 次重试 (等待 {wait}s)")
                await asyncio.sleep(wait)
                continue
            raise last_error
        except aiohttp.ClientError as e:
            last_error = e
            if attempt < MAX_RETRIES:
                wait = 2 ** attempt
                print(f"[AIChat] 网络错误 {e}, 第 {attempt+1} 次重试 (等待 {wait}s)")
                await asyncio.sleep(wait)
                continue
            raise

    raise last_error or Exception("API 调用失败")


# ── @mention 解析 ──
_MENTION_PATTERN = re.compile(r'\[@(.*?)\]')

async def _resolve_mentions(reply: str, message) -> tuple:
    """
    解析 AI 回复中的 [@用户名] 标记, 匹配 Discord 用户并替换为 <@ID>
    返回 (处理后的文本, AllowedMentions 或 None)
    匹配优先级: display_name 精确 → name 精确 → nick 精确 → display_name 模糊 → name 模糊
    """
    matches = _MENTION_PATTERN.findall(reply)
    if not matches:
        return reply, None

    guild = message.guild
    if not guild or not guild.members:
        return reply, None

    matched_users = []
    resolved = {}  # {name_lower: member}

    for raw_name in matches:
        name = raw_name.strip()
        name_lower = name.lower()

        if name_lower in resolved:
            continue

        found = None
        # 第一轮: 精确匹配
        for m in guild.members:
            if (m.display_name.lower() == name_lower or
                m.name.lower() == name_lower or
                (m.nick and m.nick.lower() == name_lower)):
                found = m
                break

        # 第二轮: 模糊匹配 (包含)
        if not found:
            for m in guild.members:
                if (name_lower in m.display_name.lower() or
                    name_lower in m.name.lower()):
                    found = m
                    break

        if found:
            resolved[name_lower] = found
            if found not in matched_users:
                matched_users.append(found)

    # 替换文本
    for name_lower, member in resolved.items():
        # 找到原始大小写的 name 来替换
        for raw_name in matches:
            if raw_name.strip().lower() == name_lower:
                reply = reply.replace(f"[@{raw_name}]", f"<@{member.id}>")
                break

    if matched_users:
        allowed = discord.AllowedMentions(users=matched_users)
        return reply, allowed

    return reply, None


async def handle_aichat(message, bot):
    """
    处理 .aichat 命令
    在 on_message 中调用, 返回 True 表示已处理
    """
    content = message.content.strip()

    # 只处理 .aichat 开头的消息
    if not content.startswith(".aichat"):
        return False

    # 排除 bot 自己
    if message.author.bot:
        return False

    if not _initialized:
        await message.reply("⚠️ AI 聊天尚未初始化，请检查 ai_key.txt 是否存在。")
        return True

    # 解析参数
    args = content[len(".aichat"):].strip()

    # .aichat (无参数) — 显示帮助
    if not args:
        help_text = (
            "**🤖 AI 聊天**\n"
            "```\n"
            ".aichat <消息>  — 和 AI 对话\n"
            ".aichat clear   — 清空对话历史\n"
            ".aichat status  — 查看对话状态\n"
            ".aichat stats   — 查看使用统计\n"
            "```\n"
            "💡 对话历史在机器人运行期间一直保持，每个用户独立。\n"
            "💡 AI 会感知当前频道名和最近对话内容。"
        )
        await message.reply(help_text)
        return True

    # .aichat clear — 清空历史
    if args.lower() in ("clear", "reset", "清除", "重置"):
        if message.author.id in _conversations:
            del _conversations[message.author.id]
        await message.reply("🗑️ 对话历史已清空。")
        return True

    # .aichat status — 查看状态
    if args.lower() in ("status", "状态"):
        conv = _conversations.get(message.author.id, [])
        msg_count = len([m for m in conv if m["role"] != "system"])
        user_stats = _stats.get(message.author.id, {})
        await message.reply(
            f"📊 **AI 聊天状态**\n"
            f"对话消息数: {msg_count} / {MAX_HISTORY * 2}\n"
            f"累计对话轮数: {user_stats.get('turns', 0)}\n"
            f"累计 Token: {user_stats.get('total_tokens', 0)}\n"
            f"模型: {ZHIPU_MODEL}\n"
            f"上下文已加载: {'是' if _initialized else '否'}"
        )
        return True

    # .aichat stats — 查看使用统计
    if args.lower() in ("stats", "统计"):
        user_stats = _stats.get(message.author.id, {})
        global_turns = sum(s["turns"] for s in _stats.values())
        global_tokens = sum(s["total_tokens"] for s in _stats.values())
        global_prompt = sum(s["prompt_tokens"] for s in _stats.values())
        global_completion = sum(s["completion_tokens"] for s in _stats.values())
        active_users = len(_stats)

        if user_stats:
            stats_text = (
                f"📈 **AI 聊天统计**\n"
                f"**你的统计:**\n"
                f"  对话轮数: {user_stats['turns']}\n"
                f"  Token 消耗: {user_stats['total_tokens']}\n"
                f"  ├─ 输入 (prompt): {user_stats['prompt_tokens']}\n"
                f"  └─ 输出 (completion): {user_stats['completion_tokens']}\n"
                f"  首次使用: {user_stats.get('first_used', '未知')}\n"
                f"  最后使用: {user_stats.get('last_used', '未知')}\n"
                f"**全局统计:**\n"
                f"  活跃用户: {active_users}\n"
                f"  总对话轮数: {global_turns}\n"
                f"  总 Token: {global_tokens}\n"
                f"  ├─ 输入: {global_prompt}\n"
                f"  └─ 输出: {global_completion}"
            )
        else:
            stats_text = (
                f"📈 **AI 聊天统计**\n"
                f"你还没有使用过 AI 聊天。\n"
                f"**全局统计:**\n"
                f"  活跃用户: {active_users}\n"
                f"  总对话轮数: {global_turns}\n"
                f"  总 Token: {global_tokens}\n"
                f"  ├─ 输入: {global_prompt}\n"
                f"  └─ 输出: {global_completion}"
            )
        await message.reply(stats_text)
        return True

    # .aichat <消息> — 正常对话
    user_id = message.author.id
    username = message.author.display_name
    conv = _get_conversation(user_id, username)

    # 添加用户消息
    conv.append({"role": "user", "content": args})

    # 获取动态上下文 (当前频道名 + 最近消息摘要)
    dynamic_ctx = await _get_dynamic_context(message, bot)

    # 构建发送给 API 的消息列表 (在最后一条 user 消息前插入动态上下文)
    messages_to_send = list(conv)
    if dynamic_ctx:
        messages_to_send.insert(-1, {"role": "system", "content": dynamic_ctx})

    # 显示"正在思考"提示
    thinking = await message.reply("🤔 正在思考...")

    try:
        reply, usage = await _call_zhipu_api(messages_to_send)

        # 添加助手回复到历史
        conv.append({"role": "assistant", "content": reply})
        _trim_conversation(user_id)

        # 更新统计
        _update_stats(user_id, usage)

        # 解析 [@用户名] 标记为 Discord mention
        reply, allowed_mentions = await _resolve_mentions(reply, message)

        # Discord 消息长度限制 2000
        if len(reply) > 1950:
            # 分段发送
            parts = [reply[i:i+1950] for i in range(0, len(reply), 1950)]
            await thinking.edit(content=parts[0], allowed_mentions=allowed_mentions)
            for part in parts[1:]:
                await message.channel.send(part, allowed_mentions=allowed_mentions)
        else:
            await thinking.edit(content=reply, allowed_mentions=allowed_mentions)

    except asyncio.TimeoutError:
        await thinking.edit(content="⏱️ AI 回复超时，已重试但仍未成功，请稍后再试。")
    except Exception as e:
        await thinking.edit(content=f"❌ AI 回复失败: {e}")
        # 移除刚才添加的用户消息 (因为没得到回复)
        if conv and conv[-1]["role"] == "user":
            conv.pop()

    return True
