"""
web_dashboard_extras.py — SDK 公会 & Wiki API 扩展
由 web_dashboard.py 的 init_web_dashboard() 调用
"""
from fastapi import Query
from fastapi.responses import JSONResponse
import sqlite3


def register_extras(app, db_path_getter, add_log, bot_getter=None):
    """
    注册额外 API 端点。
    app:              FastAPI 实例
    db_path_getter:  零参函数，返回当前 db_path
    add_log:          web_dashboard.add_log 函数
    bot_getter:       零参函数，返回 bot 实例 (可选)
    """
    _ap = app
    _get_db = db_path_getter
    _log = add_log
    _get_bot = bot_getter

    @ _ap.get("/api/sdk-guilds")
    async def api_sdk_guilds(
        category: str = Query(""),
        search:   str = Query(""),
        page:     int = Query(1, ge=1),
        per_page: int = Query(20, ge=1, le=100),
    ):
        """SDK 公会列表（支持分类筛选和搜索）"""
        dp = _get_db()
        if not dp:
            return {"guilds": [], "total": 0, "total_pages": 0, "categories": []}

        try:
            conn = sqlite3.connect(dp)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            # 确保 category 字段存在
            try:
                cur.execute("ALTER TABLE sdk_guilds ADD COLUMN category TEXT DEFAULT '未分类'")
                conn.commit()
            except Exception:
                pass

            where = "1=1"
            params = []
            if category:
                where += " AND COALESCE(category, '未分类') = ?"
                params.append(category)
            if search:
                where += " AND (name LIKE ? OR description LIKE ?)"
                params.extend([f"%{search}%", f"%{search}%"])

            cur.execute(f"SELECT COUNT(*) FROM sdk_guilds WHERE {where}", params)
            total = cur.fetchone()[0]

            offset = (page - 1) * per_page
            cur.execute(
                f"SELECT id, guild_id, name, description, "
                f"COALESCE(category, '未分类') AS category, "
                f"level, exp, funds, leader_id, created_at "
                f"FROM sdk_guilds WHERE {where} ORDER BY level DESC, exp DESC LIMIT ? OFFSET ?",
                params + [per_page, offset]
            )
            rows = cur.fetchall()
            conn.close()

            guilds = [dict(r) for r in rows]

            # 获取所有分类 
            conn2 = sqlite3.connect(dp)
            cur2 = conn2.cursor()
            try:
                cur2.execute("SELECT DISTINCT category FROM sdk_guilds WHERE category IS NOT NULL AND category != ''")
                categories = [r[0] for r in cur2.fetchall()]
            except Exception:
                categories = []
            conn2.close()

            return {
                "guilds":      guilds,
                "total":        total,
                "total_pages":  (total + per_page - 1) // per_page,
                "categories":   categories,
            }
        except Exception as e:
            _log("ERROR", f"API /api/sdk-guilds 失败: {e}")
            return {"guilds": [], "total": 0, "total_pages": 0, "categories": []}

    @ _ap.get("/api/sdk-guild-leaderboard")
    async def api_sdk_guild_leaderboard(
        sort_by: str = Query("level"),
        limit:   int = Query(20, ge=1, le=100),
    ):
        """SDK 公会排行榜（按 level/exp/funds 排序）"""
        dp = _get_db()
        if not dp:
            return {"leaderboard": [], "sort_by": sort_by}

        if sort_by not in ("level", "exp", "funds"):
            sort_by = "level"

        try:
            conn = sqlite3.connect(dp)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            try:
                cur.execute(
                    f"SELECT id, guild_id, name, description, level, exp, funds, leader_id, created_at "
                    f"FROM sdk_guilds ORDER BY {sort_by} DESC, exp DESC LIMIT ?",
                    (limit,)
                )
            except Exception:
                cur.execute(
                    "SELECT id, guild_id, name, description, level, exp, funds, leader_id, created_at "
                    "FROM sdk_guilds ORDER BY level DESC, exp DESC LIMIT ?",
                    (limit,)
                )
            rows = cur.fetchall()
            conn.close()

            result = []
            for rank, r in enumerate(rows, 1):
                d = dict(r)
                d["rank"] = rank
                result.append(d)

            return {"leaderboard": result, "sort_by": sort_by}
        except Exception as e:
            _log("ERROR", f"API /api/sdk-guild-leaderboard 失败: {e}")
            return {"leaderboard": [], "sort_by": sort_by}

    @ _ap.get("/api/wiki")
    async def api_wiki(
        category: str = Query(""),
        search:   str = Query(""),
        page:     int = Query(1, ge=1),
        per_page: int = Query(20, ge=1, le=100),
    ):
        """Wiki 页面列表（支持分类筛选和搜索）"""
        dp = _get_db()
        if not dp:
            return {"pages": [], "total": 0, "total_pages": 0, "categories": []}

        try:
            conn = sqlite3.connect(dp)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            where = "1=1"
            params = []
            if category:
                where += " AND category = ?"
                params.append(category)
            if search:
                where += " AND (title LIKE ? OR content LIKE ?)"
                params.extend([f"%{search}%", f"%{search}%"])

            cur.execute(f"SELECT COUNT(*) FROM sdk_wiki_pages WHERE {where}", params)
            total = cur.fetchone()[0]

            offset = (page - 1) * per_page
            cur.execute(
                f"SELECT id, guild_id, title, category, author_id, created_at, updated_at "
                f"FROM sdk_wiki_pages WHERE {where} ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                params + [per_page, offset]
            )
            rows = cur.fetchall()
            conn.close()

            pages = [dict(r) for r in rows]

            # 获取所有分类 
            conn2 = sqlite3.connect(dp)
            cur2 = conn2.cursor()
            try:
                cur2.execute("SELECT DISTINCT category FROM sdk_wiki_pages WHERE category IS NOT NULL AND category != ''")
                categories = [r[0] for r in cur2.fetchall()]
            except Exception:
                categories = []
            conn2.close()

            return {
                "pages":        pages,
                "total":        total,
                "total_pages":  (total + per_page - 1) // per_page,
                "categories":   categories,
            }
        except Exception as e:
            _log("ERROR", f"API /api/wiki 失败: {e}")
            return {"pages": [], "total": 0, "total_pages": 0, "categories": []}

    # ════════════════════════════════════════════
    #  Wiki 详情 & 版本历史
    # ════════════════════════════════════════════

    @_ap.get("/api/wiki/{page_id}")
    async def api_wiki_detail(page_id: int):
        """获取单个 Wiki 页面内容 (最新版)"""
        dp = _get_db()
        if not dp:
            return {"error": "数据库未连接"}

        try:
            conn = sqlite3.connect(dp)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(
                "SELECT id, guild_id, title, content, category, author_id, "
                "created_at, updated_at FROM sdk_wiki_pages WHERE id = ?",
                (page_id,)
            )
            row = cur.fetchone()
            conn.close()
            if not row:
                return {"error": "页面不存在"}
            return dict(row)
        except Exception as e:
            _log("ERROR", f"API /api/wiki/{page_id} 失败: {e}")
            return {"error": str(e)}

    @_ap.get("/api/wiki/{page_id}/versions")
    async def api_wiki_versions(page_id: int):
        """获取 Wiki 页面的版本历史列表"""
        dp = _get_db()
        if not dp:
            return {"versions": []}

        try:
            conn = sqlite3.connect(dp)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            # 先查主表获取最新版信息
            cur.execute(
                "SELECT title, updated_at, author_id FROM sdk_wiki_pages WHERE id = ?",
                (page_id,)
            )
            page = cur.fetchone()
            if not page:
                conn.close()
                return {"versions": [], "error": "页面不存在"}

            # 查历史版本
            cur.execute(
                "SELECT version_num, title, editor_id, edited_at "
                "FROM sdk_wiki_versions WHERE page_id = ? ORDER BY version_num DESC",
                (page_id,)
            )
            rows = cur.fetchall()
            conn.close()

            versions = []
            # 最新版 (虚拟 version 0 = current)
            versions.append({
                "version_num": 0,
                "title": page["title"],
                "editor_id": page["author_id"],
                "edited_at": page["updated_at"],
                "is_current": True,
            })
            for r in rows:
                d = dict(r)
                d["is_current"] = False
                versions.append(d)

            return {"versions": versions, "total": len(versions)}
        except Exception as e:
            _log("ERROR", f"API /api/wiki/{page_id}/versions 失败: {e}")
            return {"versions": [], "error": str(e)}

    @_ap.get("/api/wiki/{page_id}/version/{version_num}")
    async def api_wiki_version_detail(page_id: int, version_num: int):
        """获取 Wiki 页面的特定历史版本内容
        version_num=0 表示最新版 (从主表读取)"""
        dp = _get_db()
        if not dp:
            return {"error": "数据库未连接"}

        try:
            conn = sqlite3.connect(dp)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            if version_num == 0:
                # 最新版
                cur.execute(
                    "SELECT id, title, content, category, author_id, "
                    "updated_at, created_at FROM sdk_wiki_pages WHERE id = ?",
                    (page_id,)
                )
                row = cur.fetchone()
                conn.close()
                if not row:
                    return {"error": "页面不存在"}
                d = dict(row)
                d["version_num"] = 0
                d["is_current"] = True
                return d
            else:
                # 历史版本
                cur.execute(
                    "SELECT page_id, version_num, title, content, category, "
                    "editor_id, edited_at FROM sdk_wiki_versions "
                    "WHERE page_id = ? AND version_num = ?",
                    (page_id, version_num)
                )
                row = cur.fetchone()
                conn.close()
                if not row:
                    return {"error": "版本不存在"}
                d = dict(row)
                d["is_current"] = False
                return d
        except Exception as e:
            _log("ERROR", f"API /api/wiki/{page_id}/version/{version_num} 失败: {e}")
            return {"error": str(e)}

    # ════════════════════════════════════════════
    #  公会详情 (Discord 服务器详细信息)
    # ════════════════════════════════════════════

    @_ap.get("/api/guilds-detail")
    async def api_guilds_detail():
        """获取所有 Discord 服务器的详细信息"""
        bot = _get_bot() if _get_bot else None
        if bot is None:
            return {"guilds": [], "total_members": 0, "total_online": 0}

        import discord
        guilds_detail = []
        total_members = 0
        total_online = 0

        for guild in bot.guilds:
            # 在线成员计数
            online = -1
            if bot.intents.members:
                # members intent 开启 → 遍历成员状态统计在线
                online = sum(
                    1 for m in guild.members
                    if m.status != discord.Status.offline
                )
            elif bot.intents.presences:
                # 仅 presence intent, 无 members intent → 无法精确统计
                online = -1
            else:
                online = -1

            # 频道统计
            text_channels = len(guild.text_channels)
            voice_channels = len(guild.voice_channels)
            categories = len(guild.categories)

            # boost
            boost_level = guild.premium_tier if hasattr(guild, 'premium_tier') else 0
            boost_count = guild.premium_subscription_count if hasattr(guild, 'premium_subscription_count') else 0

            # 创建时间
            created = guild.created_at.strftime("%Y-%m-%d") if guild.created_at else "—"

            # 图标
            icon_url = str(guild.icon.url) if guild.icon else None

            # 角色
            role_count = len(guild.roles)

            guilds_detail.append({
                "id": guild.id,
                "name": guild.name,
                "members": guild.member_count,
                "online": online,
                "owner": str(guild.owner) if guild.owner else "Unknown",
                "owner_id": guild.owner_id,
                "text_channels": text_channels,
                "voice_channels": voice_channels,
                "categories": categories,
                "roles": role_count,
                "boost_level": boost_level,
                "boost_count": boost_count,
                "created_at": created,
                "icon_url": icon_url,
            })
            total_members += guild.member_count
            if online > 0:
                total_online += online

        return {
            "guilds": guilds_detail,
            "total_members": total_members,
            "total_online": total_online,
            "guild_count": len(guilds_detail),
        }
