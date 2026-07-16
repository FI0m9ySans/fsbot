"""
FSBot Web Dashboard — FastAPI 管理面板
提供 Web 界面查看 Bot 状态、用户数据、模组管理、实时日志
"""
import asyncio
import threading
import time
import json
import os
from datetime import datetime
from collections import deque
from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

try:
    from web_dashboard_extras import register_extras
except Exception:
    register_extras = None

# ── 全局状态引用 (由 main.py 注入) ──
bot_ref = None          # discord.ext.commands.Bot
db_path = None          # sqlite3 数据库文件路径 (每个请求独立开连接，避免跨线程)
mod_sdk_ref = None      # mod_sdk 模块
start_time = None       # Bot 启动时间

# 日志缓冲区 (最近 500 条)
log_buffer = deque(maxlen=500)

def add_log(level: str, message: str):
    """向 Web Dashboard 日志缓冲区添加一条日志"""
    log_buffer.append({
        "time": datetime.now().strftime("%H:%M:%S"),
        "level": level,
        "message": message
    })

# ── FastAPI App ──
app = FastAPI(title="FSBot Dashboard", version="2.0.0")

# 静态文件 & 模板路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

# 确保目录存在
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(TEMPLATES_DIR, exist_ok=True)

# 挂载静态文件
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Dashboard HTML 文件路径
DASHBOARD_HTML = os.path.join(TEMPLATES_DIR, "dashboard.html")
MOD_EDITOR_HTML = os.path.join(TEMPLATES_DIR, "mod_editor.html")
GAMEPAD_SETTINGS_HTML = os.path.join(TEMPLATES_DIR, "gamepad-settings.html")


# ═══════════════════════════════════════════
# API 路由
# ═══════════════════════════════════════════

@app.get("/api/status")
async def api_status():
    """Bot 运行状态"""
    if bot_ref is None:
        return JSONResponse({"error": "Bot 未连接"}, status_code=503)

    bot = bot_ref
    uptime_seconds = int(time.time() - start_time) if start_time else 0
    hours, remainder = divmod(uptime_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    guilds_info = []
    total_members = 0
    for guild in bot.guilds:
        guilds_info.append({
            "id": guild.id,
            "name": guild.name,
            "members": guild.member_count,
            "owner": str(guild.owner) if guild.owner else "Unknown"
        })
        total_members += guild.member_count

    return {
        "bot_name": str(bot.user),
        "bot_id": bot.user.id if bot.user else 0,
        "ping_ms": round(bot.latency * 1000, 1) if bot.latency and bot.latency != float('inf') else -1,
        "uptime": f"{hours}h {minutes}m {seconds}s",
        "uptime_seconds": uptime_seconds,
        "guild_count": len(bot.guilds),
        "total_members": total_members,
        "guilds": guilds_info,
        "loaded_mods": _get_mod_list(),
        "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "intents": {
            "message_content": bot.intents.message_content,
            "members": bot.intents.members,
            "presences": bot.intents.presences,
        }
    }


import sqlite3

@app.get("/api/users")
async def api_users(page: int = Query(1, ge=1), per_page: int = Query(50, ge=1, le=200)):
    """用户列表 (分页)"""
    if db_path is None:
        return JSONResponse({"error": "数据库未连接", "users": [], "total": 0, "page": page, "per_page": per_page, "total_pages": 1}, status_code=200)

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT COUNT(*) FROM users")
            total = cursor.fetchone()[0]

            offset = (page - 1) * per_page
            cursor.execute(
                "SELECT user_id, username, points, monthly_points, exp, level, last_daily FROM users "
                "ORDER BY points DESC LIMIT ? OFFSET ?",
                (per_page, offset)
            )
            rows = cursor.fetchall()

            users = []
            for row in rows:
                users.append({
                    "user_id": row[0],
                    "username": row[1] if row[1] else f"User_{row[0]}",
                    "points": row[2],
                    "monthly_points": row[3],
                    "exp": row[4],
                    "level": row[5],
                    "last_daily": row[6]
                })

            return {
                "total": total,
                "page": page,
                "per_page": per_page,
                "total_pages": max(1, (total + per_page - 1) // per_page),
                "users": users
            }
        finally:
            conn.close()
    except Exception as e:
        add_log("ERROR", f"API /api/users 失败: {e}")
        return JSONResponse({"error": str(e), "users": []}, status_code=200)


@app.get("/api/leaderboard")
async def api_leaderboard(limit: int = Query(20, ge=1, le=100)):
    """月度积分排行榜"""
    if db_path is None:
        return JSONResponse({"error": "数据库未连接", "leaderboard": [], "total": 0}, status_code=200)

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT user_id, username, points, monthly_points, exp, level FROM users "
                "WHERE monthly_points > 0 ORDER BY monthly_points DESC LIMIT ?",
                (limit,)
            )
            rows = cursor.fetchall()

            leaderboard = []
            for i, row in enumerate(rows, 1):
                leaderboard.append({
                    "rank": i,
                    "user_id": row[0],
                    "username": row[1] if row[1] else f"User_{row[0]}",
                    "points": row[2],
                    "monthly_points": row[3],
                    "exp": row[4],
                    "level": row[5]
                })

            return {"leaderboard": leaderboard, "total": len(leaderboard)}
        finally:
            conn.close()
    except Exception as e:
        add_log("ERROR", f"API /api/leaderboard 失败: {e}")
        return JSONResponse({"error": str(e), "leaderboard": []}, status_code=200)


@app.get("/api/mods")
async def api_mods():
    """已加载的模组列表"""
    return {"mods": _get_mod_list()}


@app.get("/api/daily-checkin-ranking")
async def api_daily_checkin_ranking(limit: int = Query(50, ge=1, le=200)):
    """每日签到时间排行榜（S1 麦收季）— 仅在 Dashboard 可见"""
    if db_path is None:
        return JSONResponse({"error": "数据库未连接", "ranking": [], "total": 0}, status_code=200)

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            cursor.execute(
                "SELECT user_id, username, daily_checkin_time FROM users "
                "WHERE daily_checkin_time LIKE ? "
                "ORDER BY daily_checkin_time ASC LIMIT ?",
                (today + '%', limit)
            )
            rows = cursor.fetchall()

            ranking = []
            for i, row in enumerate(rows, 1):
                ranking.append({
                    "rank": i,
                    "user_id": row[0],
                    "username": row[1] if row[1] else f"User_{row[0]}",
                    "checkin_time": row[2]
                })

            return {
                "date": today,
                "season": "S1 麦收季",
                "ranking": ranking,
                "total": len(ranking)
            }
        finally:
            conn.close()
    except Exception as e:
        add_log("ERROR", f"API /api/daily-checkin-ranking 失败: {e}")
        return JSONResponse({"error": str(e), "ranking": []}, status_code=200)


@app.get("/api/best-luck-ranking")
async def api_best_luck_ranking(limit: int = Query(50, ge=1, le=200)):
    """手气最佳排行榜（S1 麦收季）— 仅在 Dashboard 可见"""
    if db_path is None:
        return JSONResponse({"error": "数据库未连接", "ranking": [], "total": 0}, status_code=200)

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT user_id, username, best_luck_count FROM users "
                "WHERE best_luck_count > 0 "
                "ORDER BY best_luck_count DESC LIMIT ?",
                (limit,)
            )
            rows = cursor.fetchall()

            ranking = []
            for i, row in enumerate(rows, 1):
                ranking.append({
                    "rank": i,
                    "user_id": row[0],
                    "username": row[1] if row[1] else f"User_{row[0]}",
                    "best_luck_count": row[2]
                })

            return {
                "season": "S1 麦收季",
                "ranking": ranking,
                "total": len(ranking)
            }
        finally:
            conn.close()
    except Exception as e:
        add_log("ERROR", f"API /api/best-luck-ranking 失败: {e}")
        return JSONResponse({"error": str(e), "ranking": []}, status_code=200)


@app.get("/api/logs")
async def api_logs(limit: int = Query(100, ge=1, le=500)):
    """最近的日志"""
    logs = list(log_buffer)[-limit:]
    return {"logs": logs, "total": len(logs)}


@app.get("/api/commands")
async def api_commands():
    """已注册的斜杠命令列表"""
    if bot_ref is None:
        return JSONResponse({"error": "Bot 未连接"}, status_code=503)

    commands = []
    for cmd in bot_ref.tree.get_commands():
        commands.append({
            "name": cmd.name,
            "description": cmd.description,
            "type": "slash"
        })

    return {"commands": commands, "total": len(commands)}


# ═══════════════════════════════════════════
# 主页面
# ═══════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request):
    """Dashboard 主页（纯静态 HTML，数据通过 JS API 加载）"""
    return FileResponse(DASHBOARD_HTML, media_type="text/html")


@app.get("/mod-editor", response_class=HTMLResponse)
async def mod_editor(request: Request):
    """模组可视化制作工具"""
    return FileResponse(MOD_EDITOR_HTML, media_type="text/html")


@app.get("/gamepad-settings", response_class=HTMLResponse)
async def gamepad_settings(request: Request):
    """Xbox 手柄设置页面"""
    return FileResponse(GAMEPAD_SETTINGS_HTML, media_type="text/html")


@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "ok", "bot_connected": bot_ref is not None and bot_ref.is_ready()}


# ═══════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════

def _get_mod_list():
    """获取已加载的模组列表（聚合所有服务器，去重）
    mod_system.guild_mod_state 结构: {guild_id: {mod_name: mod_info}}
    """
    result = []
    try:
        import mod_system as _ms
        # 新版：从 guild_mod_state 聚合
        if hasattr(_ms, 'guild_mod_state'):
            seen = set()
            for guild_id, mods in _ms.guild_mod_state.items():
                for mod_name, mod_info in mods.items():
                    if mod_name in seen:
                        continue
                    seen.add(mod_name)
                    mod_data = mod_info.get('data', {})
                    # 统计此模组在多少个服务器启用
                    guild_count = sum(1 for g, gm in _ms.guild_mod_state.items() if mod_name in gm)
                    result.append({
                        "name": mod_data.get("name", mod_name),
                        "version": mod_data.get("version", "?"),
                        "author": mod_data.get("author", "?"),
                        "description": mod_data.get("description", ""),
                        "guilds": guild_count,
                    })
        # 向后兼容：旧版 loaded_mods
        elif hasattr(_ms, 'loaded_mods') and isinstance(_ms.loaded_mods, dict):
            for mod_name, mod_info in _ms.loaded_mods.items():
                mod_data = mod_info.get('data', {})
                result.append({
                    "name": mod_data.get("name", mod_name),
                    "version": mod_data.get("version", "?"),
                    "author": mod_data.get("author", "?"),
                    "description": mod_data.get("description", ""),
                })
        elif mod_sdk_ref and "mod_list" in mod_sdk_ref.SDK_API:
            raw = mod_sdk_ref.SDK_API["mod_list"]()
            if isinstance(raw, list):
                return raw
    except Exception as e:
        add_log("ERROR", f"获取模组列表失败: {e}")
    return result


# ═══════════════════════════════════════════
# Web 服务器启动
# ═══════════════════════════════════════════

_server_thread = None
_server_running = False


def start_web_server(host: str = "0.0.0.0", port: int = 8080):
    """在独立线程中启动 Web 服务器"""
    global _server_thread, _server_running

    if _server_running:
        add_log("WARN", "Web 服务器已在运行中")
        return False

    def _run():
        global _server_running
        _server_running = True
        add_log("INFO", f"Web Dashboard 启动于 http://{host}:{port}")
        uvicorn.run(app, host=host, port=port, log_level="warning", access_log=False)

    _server_thread = threading.Thread(target=_run, daemon=True, name="WebDashboard")
    _server_thread.start()
    return True


def stop_web_server():
    """停止 Web 服务器 (daemon 线程随进程退出)"""
    global _server_running
    _server_running = False
    add_log("INFO", "Web Dashboard 已停止")


def init_web_dashboard(bot, db_path_param: str, mod_sdk, start_t):
    """由 main.py 调用，注入依赖并启动
    - db_path_param: users.db 的完整路径，每个 API 请求独立开连接（避免跨线程 SQLite 错误）
    """
    global bot_ref, db_path, mod_sdk_ref, start_time
    bot_ref = bot
    db_path = db_path_param
    mod_sdk_ref = mod_sdk
    start_time = start_t

    add_log("INFO", "Web Dashboard 模块已初始化")

    # 注册扩展 API（公会排行榜 / Wiki / 公会详情）
    if register_extras is not None:
        register_extras(app, lambda: db_path, add_log, lambda: bot_ref)
        add_log("INFO", "扩展 API 已注册")

    return app
