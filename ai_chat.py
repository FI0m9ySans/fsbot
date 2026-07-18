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
import sqlite3

# ── 智谱AI 配置 ──
ZHIPU_API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
ZHIPU_MODEL = "glm-4-flash"
ZHIPU_API_KEY = ""

# ── 运行时状态 ──
_system_context: str = ""          # 系统提示词 (启动后构建一次)
_conversations: dict = {}          # {user_id: [{"role":..., "content":...}, ...]}
_initialized: bool = False
MAX_HISTORY = 20                   # 每用户最多保留 20 轮对话 (不含 system)

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


async def _call_zhipu_api(messages: list) -> str:
    """调用智谱AI API, 返回回复文本"""
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

    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(ZHIPU_API_URL, headers=headers, json=payload) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                raise Exception(f"API 返回 {resp.status}: {error_text[:200]}")
            data = await resp.json()
            return data["choices"][0]["message"]["content"]


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
            "```\n"
            "💡 对话历史在机器人运行期间一直保持，每个用户独立。"
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
        await message.reply(
            f"📊 **AI 聊天状态**\n"
            f"对话消息数: {msg_count} / {MAX_HISTORY * 2}\n"
            f"模型: {ZHIPU_MODEL}\n"
            f"上下文已加载: {'是' if _initialized else '否'}"
        )
        return True

    # .aichat <消息> — 正常对话
    user_id = message.author.id
    username = message.author.display_name
    conv = _get_conversation(user_id, username)

    # 添加用户消息
    conv.append({"role": "user", "content": args})

    # 显示"正在思考"提示
    thinking = await message.reply("🤔 正在思考...")

    try:
        reply = await _call_zhipu_api(conv)

        # 添加助手回复到历史
        conv.append({"role": "assistant", "content": reply})
        _trim_conversation(user_id)

        # Discord 消息长度限制 2000
        if len(reply) > 1950:
            # 分段发送
            parts = [reply[i:i+1950] for i in range(0, len(reply), 1950)]
            await thinking.edit(content=parts[0])
            for part in parts[1:]:
                await message.channel.send(part)
        else:
            await thinking.edit(content=reply)

    except asyncio.TimeoutError:
        await thinking.edit(content="⏱️ AI 回复超时，请稍后再试。")
    except Exception as e:
        await thinking.edit(content=f"❌ AI 回复失败: {e}")
        # 移除刚才添加的用户消息 (因为没得到回复)
        if conv and conv[-1]["role"] == "user":
            conv.pop()

    return True
