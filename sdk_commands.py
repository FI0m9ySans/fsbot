"""
sdk_commands.py — FSBot 通用 SDK 斜杠命令
为玩家提供：查询余额、背包、记事本、待办、物品使用、
商店、公会、知识库、自动化等操作

依赖：main.py 中已有的 bot, cursor, conn, mod_sdk
用法：在 main.py 的 on_ready 中 import sdk_commands 并调用 init_sdk_commands()
"""

import discord
from discord import app_commands

# ── 引用 main 中的全局对象（由 init_sdk_commands 注入）──
_bot = None
_cursor = None
_conn = None
_mod_sdk = None


def init_sdk_commands(bot, cursor, conn, mod_sdk):
    """在 main.py 的 on_ready 中调用，注入全局对象并注册命令"""
    global _bot, _cursor, _conn, _mod_sdk
    _bot = bot
    _cursor = cursor
    _conn = conn
    _mod_sdk = mod_sdk

    # 注册所有命令到 bot.tree
    _register_commands()

    print("[SDKCommands] 通用 SDK 命令已注册（共 22 个命令）")


# ── 辅助函数 ──

async def _safe_response(interaction, content=None, embed=None, ephemeral=True):
    """安全发送响应，避免重复响应错误"""
    try:
        if not interaction.response.is_done():
            if embed:
                await interaction.response.send_message(embed=embed, ephemeral=ephemeral)
            else:
                await interaction.response.send_message(content, ephemeral=ephemeral)
        else:
            if embed:
                await interaction.followup.send(embed=embed, ephemeral=ephemeral)
            else:
                await interaction.followup.send(content, ephemeral=ephemeral)
    except Exception as e:
        print(f"[SDKCommands] 发送响应失败: {e}")


def _ensure_table(table_name, create_sql):
    """确保表存在，如果不存在则创建"""
    try:
        _cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
        if not _cursor.fetchone():
            _cursor.execute(create_sql)
            _conn.commit()
            print(f"[SDKCommands] 自动创建表: {table_name}")
    except Exception as e:
        print(f"[SDKCommands] 检查/创建表 {table_name} 失败: {e}")


# ── 命令注册 ──

def _register_commands():
    """注册所有通用 SDK 命令"""

    # 确保所需的数据库表存在
    _ensure_table('sdk_notes', '''
        CREATE TABLE IF NOT EXISTS sdk_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            content TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    _ensure_table('sdk_todos', '''
        CREATE TABLE IF NOT EXISTS sdk_todos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            task TEXT NOT NULL,
            completed INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP DEFAULT NULL
        )
    ''')

    _ensure_table('sdk_currencies', '''
        CREATE TABLE IF NOT EXISTS sdk_currencies (
            id TEXT PRIMARY KEY,
            guild_id TEXT NOT NULL,
            name TEXT NOT NULL,
            symbol TEXT NOT NULL,
            description TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    _ensure_table('sdk_user_currencies', '''
        CREATE TABLE IF NOT EXISTS sdk_user_currencies (
            user_id INTEGER NOT NULL,
            currency_id TEXT NOT NULL,
            amount REAL DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, currency_id)
        )
    ''')

    _ensure_table('sdk_items', '''
        CREATE TABLE IF NOT EXISTS sdk_items (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            item_type TEXT DEFAULT 'item',
            description TEXT DEFAULT '',
            properties TEXT DEFAULT '{}',
            transferable INTEGER DEFAULT 1,
            created_by TEXT DEFAULT 'system',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    _ensure_table('sdk_inventory', '''
        CREATE TABLE IF NOT EXISTS sdk_inventory (
            user_id INTEGER NOT NULL,
            item_id TEXT NOT NULL,
            quantity INTEGER DEFAULT 1,
            acquired_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, item_id)
        )
    ''')

    # ================================================================
    # 1. /sdk_balance - 查询自定义货币余额
    # ================================================================
    @_bot.tree.command(name="sdk_balance", description="查询自定义货币余额 / View custom currency balance")
    async def sdk_balance_slash(interaction: discord.Interaction):
        try:
            guild_id = str(interaction.guild_id) if interaction.guild_id else 'global'
            _cursor.execute("SELECT id, name, symbol FROM sdk_currencies WHERE guild_id = ?", (guild_id,))
            currencies = _cursor.fetchall()

            if not currencies:
                await _safe_response(interaction, "📦 当前服务器没有自定义货币。")
                return

            embed = discord.Embed(title="💰 自定义货币余额", color=discord.Color.gold())
            for curr_id, curr_name, curr_symbol in currencies:
                _cursor.execute(
                    "SELECT amount FROM sdk_user_currencies WHERE user_id=? AND currency_id=?",
                    (str(interaction.user.id), curr_id),
                )
                row = _cursor.fetchone()
                balance = row[0] if row else 0.0
                embed.add_field(name=f"{curr_symbol} {curr_name}", value=f"余额: **{balance:.2f}**", inline=False)

            await _safe_response(interaction, embed=embed)

        except Exception as e:
            await _safe_response(interaction, f"❌ 查询失败: `{e}`")

    # ================================================================
    # 2. /sdk_items - 查询背包
    # ================================================================
    @_bot.tree.command(name="sdk_items", description="查询背包 / View inventory")
    async def sdk_items_slash(interaction: discord.Interaction):
        try:
            _cursor.execute("""
                SELECT i.name, inv.quantity, i.item_type
                FROM sdk_inventory inv
                JOIN sdk_items i ON inv.item_id = i.id
                WHERE inv.user_id = ?
            """, (str(interaction.user.id),))
            items = _cursor.fetchall()

            if not items:
                await _safe_response(interaction, "🎒 背包为空。")
                return

            embed = discord.Embed(title="🎒 背包物品", color=discord.Color.green())
            for item_name, quantity, item_type in items:
                embed.add_field(name=item_name, value=f"类型: {item_type}\n数量: **{quantity}**", inline=True)

            await _safe_response(interaction, embed=embed)

        except Exception as e:
            await _safe_response(interaction, f"❌ 查询失败: `{e}`")

    # ================================================================
    # 3. /sdk_notes - 查询记事本
    # ================================================================
    @_bot.tree.command(name="sdk_notes", description="查询记事本 / View notes")
    async def sdk_notes_slash(interaction: discord.Interaction):
        try:
            _cursor.execute(
                "SELECT id, title, content FROM sdk_notes WHERE user_id=? ORDER BY created_at DESC LIMIT 10",
                (str(interaction.user.id),),
            )
            notes = _cursor.fetchall()

            if not notes:
                await _safe_response(interaction, "📝 记事本为空。\n使用 `/sdk_note_create` 创建新笔记。")
                return

            embed = discord.Embed(title="📝 你的记事本", color=discord.Color.blue())
            embed.set_footer(text=f"共 {len(notes)} 条笔记 | 使用 /sdk_note_remove 删除")

            for note_id, note_title, note_content in notes:
                content_preview = (note_content[:100] + "...") if note_content and len(note_content) > 100 else (note_content or "(空)")
                embed.add_field(name=f"📌 {note_title}", value=content_preview, inline=False)

            await _safe_response(interaction, embed=embed)

        except Exception as e:
            await _safe_response(interaction, f"❌ 查询失败: `{e}`")

    # ================================================================
    # 4. /sdk_todos - 查询待办事项
    # ================================================================
    @_bot.tree.command(name="sdk_todos", description="查询待办事项 / View todos")
    async def sdk_todos_slash(interaction: discord.Interaction):
        try:
            _cursor.execute(
                "SELECT id, task, completed FROM sdk_todos WHERE user_id=? ORDER BY completed ASC, created_at DESC LIMIT 10",
                (str(interaction.user.id),),
            )
            todos = _cursor.fetchall()

            if not todos:
                await _safe_response(interaction, "✅ 待办事项为空。\n使用 `/sdk_todo_add` 添加新任务。")
                return

            embed = discord.Embed(title="✅ 待办事项", color=discord.Color.orange())

            pending_list = []
            done_list = []

            for todo_id, task_text, completed_flag in todos:
                if completed_flag:
                    done_list.append(f"~~{task_text}~~ ✅")
                else:
                    pending_list.append(f"☐ {task_text}")

            if pending_list:
                embed.add_field(name="⏳ 待完成", value="\n".join(pending_list[:5]), inline=False)

            if done_list:
                embed.add_field(name="✅ 已完成", value="\n".join(done_list[:5]), inline=False)

            embed.set_footer(text="使用 /sdk_todo_complete 完成任务 | /sdk_todo_remove 删除任务")
            await _safe_response(interaction, embed=embed)

        except Exception as e:
            await _safe_response(interaction, f"❌ 查询失败: `{e}`")

    # ================================================================
    # 5. /sdk_note_create - 创建记事本
    # ================================================================
    @_bot.tree.command(name="sdk_note_create", description="创建记事本 / Create a note")
    @app_commands.describe(title="标题 / Title", content="内容 / Content (可选)")
    async def sdk_note_create_slash(interaction: discord.Interaction, title: str, content: str = ""):
        try:
            if not title.strip():
                await _safe_response(interaction, "❌ 标题不能为空！")
                return

            _cursor.execute(
                "INSERT INTO sdk_notes (user_id, title, content) VALUES (?, ?, ?)",
                (str(interaction.user.id), title.strip(), content.strip()),
            )
            _conn.commit()

            embed = discord.Embed(
                title="✅ 创建成功",
                description=f"已创建记事本：**{title.strip()}**\n内容：{(content[:50] + '...' if len(content)>50 else content) or '(空)'}",
                color=discord.Color.green(),
            )
            await _safe_response(interaction, embed=embed)

        except Exception as e:
            await _safe_response(interaction, f"❌ 创建失败: `{e}`")

    # ================================================================
    # 6. /sdk_todo_add - 添加待办事项
    # ================================================================
    @_bot.tree.command(name="sdk_todo_add", description="添加待办事项 / Add a todo")
    @app_commands.describe(task="任务内容 / Task")
    async def sdk_todo_add_slash(interaction: discord.Interaction, task: str):
        try:
            if not task.strip():
                await _safe_response(interaction, "❌ 任务不能为空！")
                return

            _cursor.execute(
                "INSERT INTO sdk_todos (user_id, task) VALUES (?, ?)",
                (str(interaction.user.id), task.strip()),
            )
            _conn.commit()

            embed = discord.Embed(
                title="✅ 添加成功",
                description=f"已添加待办事项：**{task.strip()}**",
                color=discord.Color.green(),
            )
            await _safe_response(interaction, embed=embed)

        except Exception as e:
            await _safe_response(interaction, f"❌ 添加失败: `{e}`")

    # ================================================================
    # 7. /sdk_note_remove - 删除记事本
    # ================================================================
    @_bot.tree.command(name="sdk_note_remove", description="删除记事本 / Remove a note")
    @app_commands.describe(title="要删除的笔记标题 / Note title (exact match)")
    async def sdk_note_remove_slash(interaction: discord.Interaction, title: str):
        try:
            _cursor.execute(
                "SELECT id FROM sdk_notes WHERE user_id=? AND title=?",
                (str(interaction.user.id), title),
            )
            note = _cursor.fetchone()

            if not note:
                await _safe_response(interaction, f"❌ 找不到标题为 **{title}** 的笔记\n使用 `/sdk_notes` 查看所有笔记")
                return

            _cursor.execute("DELETE FROM sdk_notes WHERE user_id=? AND title=?", (str(interaction.user.id), title))
            _conn.commit()

            embed = discord.Embed(title="🗑️ 删除成功", description=f"已删除笔记：**{title}**", color=discord.Color.orange())
            await _safe_response(interaction, embed=embed)

        except Exception as e:
            await _safe_response(interaction, f"❌ 删除失败: `{e}`")

    # ================================================================
    # 8. /sdk_todo_complete - 完成待办事项
    # ================================================================
    @_bot.tree.command(name="sdk_todo_complete", description="完成待办事项 / Complete a todo")
    @app_commands.describe(task="要完成的任务内容 / Task (exact match)")
    async def sdk_todo_complete_slash(interaction: discord.Interaction, task: str):
        try:
            _cursor.execute(
                "SELECT id, completed FROM sdk_todos WHERE user_id=? AND task=?",
                (str(interaction.user.id), task),
            )
            todo = _cursor.fetchone()

            if not todo:
                await _safe_response(interaction, f"❌ 找不到任务 **{task}**\n使用 `/sdk_todos` 查看所有待办")
                return

            todo_id, already_done = todo
            if already_done:
                await _safe_response(interaction, f"ℹ️ 任务 **{task}** 已经完成过了 ✓")
                return

            from datetime import datetime
            _cursor.execute(
                "UPDATE sdk_todos SET completed=1, completed_at=? WHERE id=?",
                (datetime.now().isoformat(), todo_id),
            )
            _conn.commit()

            embed = discord.Embed(title="✅ 已完成", description=f"太棒了！完成了：**{task}** 🎉", color=discord.Color.green())
            await _safe_response(interaction, embed=embed)

        except Exception as e:
            await _safe_response(interaction, f"❌ 操作失败: `{e}`")

    # ================================================================
    # 9. /sdk_todo_remove - 删除待办事项
    # ================================================================
    @_bot.tree.command(name="sdk_todo_remove", description="删除待办事项 / Remove a todo")
    @app_commands.describe(task="要删除的任务内容 / Task (exact match)")
    async def sdk_todo_remove_slash(interaction: discord.Interaction, task: str):
        try:
            _cursor.execute(
                "SELECT id FROM sdk_todos WHERE user_id=? AND task=?",
                (str(interaction.user.id), task),
            )
            todo = _cursor.fetchone()

            if not todo:
                await _safe_response(interaction, f"❌ 找不到任务 **{task}**\n使用 `/sdk_todos` 查看所有待办")
                return

            _cursor.execute("DELETE FROM sdk_todos WHERE user_id=? AND task=?", (str(interaction.user.id), task))
            _conn.commit()

            embed = discord.Embed(title="🗑️ 删除成功", description=f"已删除待办：**{task}**", color=discord.Color.orange())
            await _safe_response(interaction, embed=embed)

        except Exception as e:
            await _safe_response(interaction, f"❌ 删除失败: `{e}`")

    # ================================================================
    # 10. /item_use - 使用物品
    # ================================================================
    @_bot.tree.command(name="item_use", description="使用背包中的物品 / Use an item")
    @app_commands.describe(item_name="物品名称 / Item name")
    async def item_use_slash(interaction: discord.Interaction, item_name: str):
        try:
            _cursor.execute('''
                SELECT i.id, i.name, inv.quantity
                FROM sdk_inventory inv
                JOIN sdk_items i ON inv.item_id = i.id
                WHERE inv.user_id = ? AND i.name LIKE ?
            ''', (str(interaction.user.id), f'%{item_name}%'))
            items = _cursor.fetchall()
            if not items:
                await _safe_response(interaction, f"❌ 背包中没有 [{item_name}]")
                return
            if len(items) > 1:
                names = ', '.join(i[1] for i in items)
                await _safe_response(interaction, f"❌ 找到多个匹配物品：{names}\n请使用更精确的名称")
                return
            item_id = items[0][0]
            ok, msg = _mod_sdk.SDK_API['item_use'](str(interaction.user.id), item_id)
            if ok:
                await _safe_response(interaction, f"✅ {msg}")
            else:
                await _safe_response(interaction, f"❌ {msg}")
        except Exception as e:
            await _safe_response(interaction, f"❌ 使用失败: {e}")

    # ================================================================
    # 11. /store_browse - 浏览商店
    # ================================================================
    @_bot.tree.command(name="store_browse", description="浏览模组商店 / Browse mod stores")
    @app_commands.describe(mod_name="模组名称（留空则显示所有） / Mod name (optional)")
    async def store_browse_slash(interaction: discord.Interaction, mod_name: str = ''):
        try:
            ok, result = _mod_sdk.SDK_API['store_list'](mod_name=mod_name or None, guild_id=str(interaction.guild_id) if interaction.guild_id else None)
            if not ok or not result:
                await _safe_response(interaction, "🛒 当前没有上架的商品")
                return
            embed = discord.Embed(title="🛒 模组商店", color=discord.Color.gold())
            for item in result[:10]:
                embed.add_field(
                    name=f"🛒 {item['item_name']} ({item['item_type']})",
                    value=f"价格: **{item['price']}**\n商店: {item['shop_name']}\nID: {item['shop_item_id']}",
                    inline=False
                )
            await _safe_response(interaction, embed=embed)
        except Exception as e:
            await _safe_response(interaction, f"❌ 查询失败: {e}")

    # ================================================================
    # 12. /store_buy - 购买商品
    # ================================================================
    @_bot.tree.command(name="store_buy", description="购买商店商品 / Buy item from store")
    @app_commands.describe(shop_item_id="商品ID（从 /store_browse 获取） / Shop item ID")
    async def store_buy_slash(interaction: discord.Interaction, shop_item_id: int):
        try:
            ok, msg = _mod_sdk.SDK_API['store_buy'](str(interaction.user.id), shop_item_id)
            if ok:
                embed = discord.Embed(title="🛒 购买成功", description=msg, color=discord.Color.green())
                await _safe_response(interaction, embed=embed)
            else:
                await _safe_response(interaction, f"❌ {msg}")
        except Exception as e:
            await _safe_response(interaction, f"❌ 购买失败: {e}")

    # ================================================================
    # 13. /guild_create - 创建公会
    # ================================================================
    @_bot.tree.command(name="guild_create", description="创建公会 / Create a guild")
    @app_commands.describe(name="公会名称 / Guild name", description="公会描述 / Description (optional)")
    async def guild_create_slash(interaction: discord.Interaction, name: str, description: str = ''):
        try:
            if not name.strip():
                await _safe_response(interaction, "❌ 公会名称不能为空！")
                return
            guild_id = str(interaction.guild_id) if interaction.guild_id else 'global'
            ok, result = _mod_sdk.SDK_API['guild_create'](guild_id, 'sdk_commands', name.strip(), description, str(interaction.user.id))
            if ok:
                embed = discord.Embed(title="⚔️ 公会创建成功", description=f"公会 **{name.strip()}** 已创建！\nID: {result}", color=discord.Color.green())
                await _safe_response(interaction, embed=embed)
            else:
                await _safe_response(interaction, f"❌ {result}")
        except Exception as e:
            await _safe_response(interaction, f"❌ 创建失败: {e}")

    # ================================================================
    # 14. /guild_join - 加入公会
    # ================================================================
    @_bot.tree.command(name="guild_join", description="加入公会 / Join a guild")
    @app_commands.describe(guild_id_val="公会ID（从 /guild_list 获取） / Guild ID")
    async def guild_join_slash(interaction: discord.Interaction, guild_id_val: int):
        try:
            guild_str = str(interaction.guild_id) if interaction.guild_id else 'global'
            ok, msg = _mod_sdk.SDK_API['guild_join'](guild_str, guild_id_val, str(interaction.user.id))
            if ok:
                await _safe_response(interaction, f"✅ {msg}")
            else:
                await _safe_response(interaction, f"❌ {msg}")
        except Exception as e:
            await _safe_response(interaction, f"❌ 加入失败: {e}")

    # ================================================================
    # 15. /guild_leave - 退出公会
    # ================================================================
    @_bot.tree.command(name="guild_leave", description="退出公会 / Leave guild")
    @app_commands.describe(guild_id_val="公会ID / Guild ID")
    async def guild_leave_slash(interaction: discord.Interaction, guild_id_val: int):
        try:
            guild_str = str(interaction.guild_id) if interaction.guild_id else 'global'
            ok, msg = _mod_sdk.SDK_API['guild_leave'](guild_str, guild_id_val, str(interaction.user.id))
            if ok:
                await _safe_response(interaction, f"✅ {msg}")
            else:
                await _safe_response(interaction, f"❌ {msg}")
        except Exception as e:
            await _safe_response(interaction, f"❌ 退出失败: {e}")

    # ================================================================
    # 16. /guild_info - 查看公会信息
    # ================================================================
    @_bot.tree.command(name="guild_info", description="查看公会信息 / View guild info")
    @app_commands.describe(guild_id_val="公会ID / Guild ID")
    async def guild_info_slash(interaction: discord.Interaction, guild_id_val: int):
        try:
            ok, info = _mod_sdk.SDK_API['guild_get_info'](guild_id_val)
            if not ok:
                await _safe_response(interaction, f"❌ {info}")
                return
            embed = discord.Embed(title=f"⚔️ {info['name']}", description=info['description'] or '暂无描述', color=discord.Color.blue())
            embed.add_field(name="等级", value=str(info['level']), inline=True)
            embed.add_field(name="经验", value=str(info['exp']), inline=True)
            embed.add_field(name="资金", value=str(info['funds']), inline=True)
            embed.add_field(name="成员数", value=str(info['member_count']), inline=True)
            embed.add_field(name="总贡献", value=str(info['total_contrib']), inline=True)
            embed.set_footer(text=f"会长ID: {info['leader_id']}")
            await _safe_response(interaction, embed=embed)
        except Exception as e:
            await _safe_response(interaction, f"❌ 查询失败: {e}")

    # ================================================================
    # 17. /guild_list - 列出公会
    # ================================================================
    @_bot.tree.command(name="guild_list", description="列出所有公会 / List all guilds")
    async def guild_list_slash(interaction: discord.Interaction):
        try:
            guild_str = str(interaction.guild_id) if interaction.guild_id else ''
            ok, result = _mod_sdk.SDK_API['guild_list'](guild_str or None)
            if not ok or not result:
                await _safe_response(interaction, "⚔️ 当前没有公会")
                return
            embed = discord.Embed(title="⚔️ 公会列表", color=discord.Color.blue())
            for g in result[:10]:
                embed.add_field(name=f"{g['name']} (Lv.{g['level']})", value=f"ID: {g['id']}\n会长: <@{g['leader_id']}>", inline=False)
            await _safe_response(interaction, embed=embed)
        except Exception as e:
            await _safe_response(interaction, f"❌ 查询失败: {e}")

    # ================================================================
    # 18. /wiki_search - 搜索知识库
    # ================================================================
    @_bot.tree.command(name="wiki_search", description="搜索知识库 / Search wiki")
    @app_commands.describe(keyword="关键词 / Keyword")
    async def wiki_search_slash(interaction: discord.Interaction, keyword: str):
        try:
            guild_str = str(interaction.guild_id) if interaction.guild_id else ''
            ok, result = _mod_sdk.SDK_API['wiki_search'](guild_str or None, keyword)
            if not ok or not result:
                await _safe_response(interaction, f"📖 知识库中没有关于 [{keyword}] 的内容")
                return
            embed = discord.Embed(title=f"📖 搜索结果: {keyword}", color=discord.Color.teal())
            for page in result[:10]:
                embed.add_field(name=f"📄 {page['title']}", value=f"分类: {page.get('category', '未分类')}\n作者: <@{page['author_id']}>", inline=False)
            await _safe_response(interaction, embed=embed)
        except Exception as e:
            await _safe_response(interaction, f"❌ 搜索失败: {e}")

    # ================================================================
    # 19. /wiki_create - 创建知识库页面
    # ================================================================
    @_bot.tree.command(name="wiki_create", description="创建知识库页面 / Create wiki page")
    @app_commands.describe(title="标题 / Title", content="内容 / Content", category="分类 / Category (optional)")
    async def wiki_create_slash(interaction: discord.Interaction, title: str, content: str, category: str = ''):
        try:
            if not title.strip():
                await _safe_response(interaction, "❌ 标题不能为空！")
                return
            guild_str = str(interaction.guild_id) if interaction.guild_id else 'global'
            ok, page_id = _mod_sdk.SDK_API['wiki_create_page'](guild_str, 'sdk_commands', title.strip(), content, str(interaction.user.id), category)
            if ok:
                await _safe_response(interaction, f"✅ 知识库页面 **{title.strip()}** 已创建！(ID: {page_id})")
            else:
                await _safe_response(interaction, f"❌ 创建失败: {page_id}")
        except Exception as e:
            await _safe_response(interaction, f"❌ 创建失败: {e}")

    # ================================================================
    # 20. /wiki_list - 列出知识库页面
    # ================================================================
    @_bot.tree.command(name="wiki_list", description="列出知识库页面 / List wiki pages")
    @app_commands.describe(category="分类筛选（留空则显示所有） / Category filter (optional)")
    async def wiki_list_slash(interaction: discord.Interaction, category: str = ''):
        try:
            guild_str = str(interaction.guild_id) if interaction.guild_id else ''
            ok, result = _mod_sdk.SDK_API['wiki_list_by_category'](guild_str or None, category)
            if not ok or not result:
                await _safe_response(interaction, "📖 知识库为空")
                return
            embed = discord.Embed(title="📖 知识库页面列表", color=discord.Color.teal())
            for page in result[:15]:
                embed.add_field(name=f"📄 {page['title']}", value=f"分类: {page.get('category', '未分类')}", inline=False)
            await _safe_response(interaction, embed=embed)
        except Exception as e:
            await _safe_response(interaction, f"❌ 查询失败: {e}")

    # ================================================================
    # 21. /automation_list - 列出自动化规则
    # ================================================================
    @_bot.tree.command(name="automation_list", description="列出自动化规则 / List automation rules")
    async def automation_list_slash(interaction: discord.Interaction):
        try:
            guild_str = str(interaction.guild_id) if interaction.guild_id else ''
            ok, result = _mod_sdk.SDK_API['automation_list'](guild_str or None)
            if not ok or not result:
                await _safe_response(interaction, "⚙️ 当前没有自动化规则")
                return
            embed = discord.Embed(title="⚙️ 自动化规则", color=discord.Color.purple())
            for rule in result:
                status = '✅ 启用' if rule['enabled'] else '❌ 禁用'
                embed.add_field(name=f"{rule['name']} ({status})", value=f"触发类型: {rule['trigger_type']}\nID: {rule['id']}", inline=False)
            await _safe_response(interaction, embed=embed)
        except Exception as e:
            await _safe_response(interaction, f"❌ 查询失败: {e}")

    # ================================================================
    # 22. /guild_dissolve - 解散公会（仅会长可操作）
    # ================================================================
    @_bot.tree.command(name="guild_dissolve", description="解散公会（仅会长） / Dissolve guild (leader only)")
    @app_commands.describe(guild_id_val="公会ID / Guild ID")
    async def guild_dissolve_slash(interaction: discord.Interaction, guild_id_val: int):
        try:
            guild_str = str(interaction.guild_id) if interaction.guild_id else 'global'
            ok, msg = _mod_sdk.SDK_API['guild_dissolve'](guild_str, guild_id_val, str(interaction.user.id))
            if ok:
                await _safe_response(interaction, f"⚔️ {msg}")
            else:
                await _safe_response(interaction, f"❌ {msg}")
        except Exception as e:
            await _safe_response(interaction, f"❌ 操作失败: {e}")

    # ================================================================
    # 23. /wiki_view - 查看知识库页面（默认最新版）
    # ================================================================
    @_bot.tree.command(name="wiki_view", description="查看知识库页面内容 / View wiki page (latest by default)")
    @app_commands.describe(title="页面标题 / Page title")
    async def wiki_view_slash(interaction: discord.Interaction, title: str):
        try:
            guild_str = str(interaction.guild_id) if interaction.guild_id else ''
            _cursor.execute('SELECT id, title, content, category, author_id, updated_at FROM sdk_wiki_pages WHERE guild_id = ? AND title = ?', (guild_str, title))
            row = _cursor.fetchone()
            if not row:
                await _safe_response(interaction, f"📖 找不到标题为 **{title}** 的页面")
                return
            page_id, page_title, content, category, author_id, updated_at = row
            _cursor.execute('SELECT COUNT(*) FROM sdk_wiki_versions WHERE page_id = ?', (page_id,))
            vrow = _cursor.fetchone()
            version_count = vrow[0] if vrow else 0
            embed = discord.Embed(
                title=f"📖 {page_title}（最新版）",
                description=content[:4096] or '(空)',
                color=discord.Color.teal()
            )
            embed.add_field(name="分类", value=category or '未分类', inline=True)
            embed.add_field(name="创建者", value=f"<@{author_id}>", inline=True)
            embed.add_field(name="历史版本数", value=str(version_count), inline=True)
            embed.set_footer(text=f"更新时间: {updated_at} | 使用 /wiki_version {title} <版本号> 查看历史")
            await _safe_response(interaction, embed=embed)
        except Exception as e:
            await _safe_response(interaction, f"❌ 查询失败: {e}")

    # ================================================================
    # 24. /wiki_edit - 编辑知识库页面（所有人可编辑）
    # ================================================================
    @_bot.tree.command(name="wiki_edit", description="编辑知识库页面（所有人可编辑，自动保存历史版本） / Edit wiki page")
    @app_commands.describe(title="页面标题 / Page title", content="新内容 / New content", category="新分类（可选） / New category (optional)")
    async def wiki_edit_slash(interaction: discord.Interaction, title: str, content: str, category: str = ''):
        try:
            if not title.strip():
                await _safe_response(interaction, "❌ 标题不能为空！")
                return
            guild_str = str(interaction.guild_id) if interaction.guild_id else ''
            _cursor.execute('SELECT id FROM sdk_wiki_pages WHERE guild_id = ? AND title = ?', (guild_str, title))
            row = _cursor.fetchone()
            if not row:
                await _safe_response(interaction, f"📖 找不到标题为 **{title}** 的页面")
                return
            page_id = row[0]
            new_cat = category.strip() if category.strip() else None
            ok, saved_version = _mod_sdk.SDK_API['wiki_edit_page'](page_id, new_content=content, new_category=new_cat)
            if ok:
                await _safe_response(interaction, f"✅ 页面 **{title}** 已更新！历史版本 {saved_version} 已自动保存。")
            else:
                await _safe_response(interaction, f"❌ 编辑失败: {saved_version}")
        except Exception as e:
            await _safe_response(interaction, f"❌ 编辑失败: {e}")

    # ================================================================
    # 25. /wiki_version - 查看历史版本
    # ================================================================
    @_bot.tree.command(name="wiki_version", description="查看知识库页面历史版本 / View wiki page version")
    @app_commands.describe(title="页面标题 / Page title", version_num="版本号 / Version number")
    async def wiki_version_slash(interaction: discord.Interaction, title: str, version_num: int):
        try:
            guild_str = str(interaction.guild_id) if interaction.guild_id else ''
            _cursor.execute('SELECT id FROM sdk_wiki_pages WHERE guild_id = ? AND title = ?', (guild_str, title))
            row = _cursor.fetchone()
            if not row:
                await _safe_response(interaction, f"📖 找不到标题为 **{title}** 的页面")
                return
            page_id = row[0]
            ok, ver = _mod_sdk.SDK_API['wiki_get_page'](page_id, version_num)
            if not ok:
                await _safe_response(interaction, f"❌ {ver}")
                return
            embed = discord.Embed(
                title=f"📖 {ver['title']}（版本 {ver['version']}）",
                description=ver['content'][:4096] or '(空)',
                color=discord.Color.teal()
            )
            embed.add_field(name="分类", value=ver.get('category', '未分类'), inline=True)
            embed.add_field(name="编辑者", value=f"<@{ver['author_id']}>", inline=True)
            embed.set_footer(text=f"版本: {ver['version']} | 编辑时间: {ver['updated_at']}")
            await _safe_response(interaction, embed=embed)
        except Exception as e:
            await _safe_response(interaction, f"❌ 查询失败: {e}")

    # ================================================================
    # 26. /wiki_versions - 列出所有历史版本
    # ================================================================
    @_bot.tree.command(name="wiki_versions", description="列出知识库页面的所有历史版本 / List wiki page versions")
    @app_commands.describe(title="页面标题 / Page title")
    async def wiki_versions_slash(interaction: discord.Interaction, title: str):
        try:
            guild_str = str(interaction.guild_id) if interaction.guild_id else ''
            _cursor.execute('SELECT id, title FROM sdk_wiki_pages WHERE guild_id = ? AND title = ?', (guild_str, title))
            row = _cursor.fetchone()
            if not row:
                await _safe_response(interaction, f"📖 找不到标题为 **{title}** 的页面")
                return
            page_id, page_title = row
            ok, versions = _mod_sdk.SDK_API['wiki_list_versions'](page_id)
            if not ok:
                await _safe_response(interaction, f"❌ 查询失败: {versions}")
                return
            if not versions:
                await _safe_response(interaction, f"📖 **{page_title}** 暂无历史版本（还未被编辑过）")
                return
            embed = discord.Embed(title=f"📖 {page_title} - 历史版本列表", color=discord.Color.teal())
            for v in versions:
                embed.add_field(
                    name=f"版本 {v['version']}",
                    value=f"编辑者: <@{v['editor_id']}>\n时间: {v['edited_at']}",
                    inline=False
                )
            embed.set_footer(text="使用 /wiki_version <标题> <版本号> 查看该版本内容")
            await _safe_response(interaction, embed=embed)
        except Exception as e:
            await _safe_response(interaction, f"❌ 查询失败: {e}")


__all__ = ['init_sdk_commands']
