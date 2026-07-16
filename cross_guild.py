"""
FSBot Cross-Guild Bridge — 跨服互通模块
通过 Webhook 在不同 Discord 服务器的频道之间桥接消息
"""
import asyncio
import sqlite3
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime
import json
import os


# ── 数据库初始化 ──
DB_PATH = "bridges.db"

def _get_db():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """初始化桥接数据库表"""
    conn = _get_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS bridges (
            bridge_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            owner_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            active INTEGER DEFAULT 1
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS bridge_connections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bridge_id TEXT NOT NULL,
            guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            webhook_url TEXT,
            joined_at TEXT NOT NULL,
            FOREIGN KEY (bridge_id) REFERENCES bridges(bridge_id)
        )
    ''')
    conn.commit()
    conn.close()


# ── 全局 Bot 引用 ──
bot_ref: commands.Bot = None


# ══════════════════════════════════════════════
# CrossGuild Cog
# ══════════════════════════════════════════════

class CrossGuild(commands.Cog):
    """跨服消息桥接"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        init_db()

    @app_commands.command(name="bridge_create", description="🌉 创建跨服桥接")
    @app_commands.describe(name="桥接名称", description_text="桥接描述 (可选)")
    async def bridge_create(self, interaction: discord.Interaction, name: str, description_text: str = ""):
        import uuid
        bridge_id = str(uuid.uuid4())[:8]

        conn = _get_db()
        conn.execute(
            "INSERT INTO bridges (bridge_id, name, owner_id, created_at, active) VALUES (?, ?, ?, ?, 1)",
            (bridge_id, name, interaction.user.id, datetime.now().isoformat())
        )
        conn.commit()
        conn.close()

        embed = discord.Embed(
            title="🌉 跨服桥接已创建",
            description=f"桥接 **{name}** (`{bridge_id}`) 已创建！",
            color=0x5865F2
        )
        embed.add_field(name="🔗 桥接 ID", value=f"`{bridge_id}`", inline=False)
        embed.add_field(name="📌 下一步", value=f"使用 `/bridge_connect {bridge_id}` 来连接其他频道的服务器", inline=False)
        if description_text:
            embed.add_field(name="📝 描述", value=description_text, inline=False)
        embed.set_footer(text=f"创建者: {interaction.user.display_name}")

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="bridge_connect", description="🔗 将当前频道连接到桥接")
    @app_commands.describe(bridge_id="桥接 ID")
    async def bridge_connect(self, interaction: discord.Interaction, bridge_id: str):
        """连接当前频道到桥接"""
        if not interaction.guild:
            await interaction.response.send_message("❌ 此命令仅限服务器内使用", ephemeral=True)
            return

        # 检查桥接是否存在
        conn = _get_db()
        bridge = conn.execute(
            "SELECT * FROM bridges WHERE bridge_id = ? AND active = 1",
            (bridge_id,)
        ).fetchone()

        if not bridge:
            conn.close()
            await interaction.response.send_message(f"❌ 找不到桥接 `{bridge_id}`", ephemeral=True)
            return

        # 检查该频道是否已连接
        existing = conn.execute(
            "SELECT * FROM bridge_connections WHERE bridge_id = ? AND guild_id = ? AND channel_id = ?",
            (bridge_id, interaction.guild_id, interaction.channel_id)
        ).fetchone()

        if existing:
            conn.close()
            await interaction.response.send_message("❌ 此频道已经连接到该桥接！", ephemeral=True)
            return

        # 获取该频道的已存在 webhook，或创建新的
        channel = interaction.channel
        webhook_url = None

        # 尝试查找已存在的 webhook
        try:
            webhooks = await channel.webhooks()
            for wh in webhooks:
                if wh.user and wh.user.id == self.bot.user.id:
                    webhook_url = wh.url
                    break
        except Exception:
            pass

        # 如果没有找到，创建新的 webhook
        if not webhook_url:
            try:
                webhook = await channel.create_webhook(name=f"FSBot Bridge - {bridge['name']}")
                webhook_url = webhook.url
            except discord.Forbidden:
                conn.close()
                await interaction.response.send_message(
                    "❌ Bot 缺少「管理 Webhooks」权限，无法创建桥接！",
                    ephemeral=True
                )
                return
            except Exception as e:
                conn.close()
                await interaction.response.send_message(f"❌ 创建 Webhook 失败: {e}", ephemeral=True)
                return

        # 保存连接
        conn.execute(
            "INSERT INTO bridge_connections (bridge_id, guild_id, channel_id, webhook_url, joined_at) VALUES (?, ?, ?, ?, ?)",
            (bridge_id, interaction.guild_id, interaction.channel_id, webhook_url, datetime.now().isoformat())
        )
        conn.commit()

        # 统计当前连接数
        count = conn.execute(
            "SELECT COUNT(*) FROM bridge_connections WHERE bridge_id = ?",
            (bridge_id,)
        ).fetchone()[0]
        conn.close()

        embed = discord.Embed(
            title="🔗 已连接到桥接",
            description=f"频道 {interaction.channel.mention} 已加入桥接 **{bridge['name']}** (`{bridge_id}`)",
            color=0x57F287
        )
        embed.add_field(name="🌐 当前连接数", value=str(count))
        embed.add_field(name="👤 创建者", value=f"<@{bridge['owner_id']}>")
        embed.set_footer(text=f"服务器: {interaction.guild.name}")

        await interaction.response.send_message(embed=embed)

        # 通知其他连接的频道
        await self._broadcast(
            bridge_id,
            interaction.guild_id,
            interaction.channel_id,
            embed=discord.Embed(
                title="🌉 新服务器已加入桥接",
                description=f"**{interaction.guild.name}** → #{interaction.channel.name}",
                color=0x5865F2
            ).set_footer(text=f"桥接: {bridge['name']}")
        )

    @app_commands.command(name="bridge_disconnect", description="🔌 断开当前频道与桥接的连接")
    @app_commands.describe(bridge_id="桥接 ID")
    async def bridge_disconnect(self, interaction: discord.Interaction, bridge_id: str):
        if not interaction.guild:
            await interaction.response.send_message("❌ 此命令仅限服务器内使用", ephemeral=True)
            return

        conn = _get_db()
        connection = conn.execute(
            "SELECT * FROM bridge_connections WHERE bridge_id = ? AND guild_id = ? AND channel_id = ?",
            (bridge_id, interaction.guild_id, interaction.channel_id)
        ).fetchone()

        if not connection:
            conn.close()
            await interaction.response.send_message("❌ 此频道未连接到此桥接", ephemeral=True)
            return

        conn.execute(
            "DELETE FROM bridge_connections WHERE bridge_id = ? AND guild_id = ? AND channel_id = ?",
            (bridge_id, interaction.guild_id, interaction.channel_id)
        )
        conn.commit()

        count = conn.execute(
            "SELECT COUNT(*) FROM bridge_connections WHERE bridge_id = ?",
            (bridge_id,)
        ).fetchone()[0]
        conn.close()

        # 尝试删除 webhook
        try:
            webhooks = await interaction.channel.webhooks()
            for wh in webhooks:
                if wh.url == connection["webhook_url"]:
                    await wh.delete()
                    break
        except Exception:
            pass

        embed = discord.Embed(
            title="🔌 已断开桥接",
            description=f"频道 {interaction.channel.mention} 已离开桥接 `{bridge_id}`",
            color=0xED4245
        )
        embed.add_field(name="🌐 剩余连接数", value=str(count))
        await interaction.response.send_message(embed=embed)

        if count > 0:
            await self._broadcast(
                bridge_id,
                interaction.guild_id,
                interaction.channel_id,
                embed=discord.Embed(
                    title="🔌 服务器已离开桥接",
                    description=f"**{interaction.guild.name}** 已断开连接",
                    color=0xED4245
                )
            )

        # 如果没有连接了，标记桥接为非活跃
        if count == 0:
            conn = _get_db()
            conn.execute("UPDATE bridges SET active = 0 WHERE bridge_id = ?", (bridge_id,))
            conn.commit()
            conn.close()

    @app_commands.command(name="bridge_list", description="📋 列出所有桥接")
    async def bridge_list(self, interaction: discord.Interaction):
        conn = _get_db()
        bridges = conn.execute(
            "SELECT b.*, COUNT(bc.id) as conn_count FROM bridges b "
            "LEFT JOIN bridge_connections bc ON b.bridge_id = bc.bridge_id "
            "WHERE b.active = 1 GROUP BY b.bridge_id"
        ).fetchall()

        if not bridges:
            conn.close()
            await interaction.response.send_message("📭 当前没有活跃的桥接", ephemeral=True)
            return

        embed = discord.Embed(title="🌉 活跃的跨服桥接", color=0x5865F2)

        for b in bridges:
            embed.add_field(
                name=f"🔗 {b['name']} (`{b['bridge_id']}`)",
                value=f"🌐 {b['conn_count']} 个连接 | 👑 <@{b['owner_id']}> | 📅 {b['created_at'][:10]}",
                inline=False
            )

        conn.close()
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="bridge_delete", description="🗑 删除桥接（仅创建者可操作）")
    @app_commands.describe(bridge_id="桥接 ID")
    async def bridge_delete(self, interaction: discord.Interaction, bridge_id: str):
        conn = _get_db()
        bridge = conn.execute(
            "SELECT * FROM bridges WHERE bridge_id = ?",
            (bridge_id,)
        ).fetchone()

        if not bridge:
            conn.close()
            await interaction.response.send_message(f"❌ 找不到桥接 `{bridge_id}`", ephemeral=True)
            return

        # 只有创建者可以删除
        if interaction.user.id != bridge['owner_id']:
            conn.close()
            await interaction.response.send_message("❌ 只有桥接创建者才能删除！", ephemeral=True)
            return

        # 先删除所有连接（webhook 也需要清理）
        connections = conn.execute(
            "SELECT * FROM bridge_connections WHERE bridge_id = ?",
            (bridge_id,)
        ).fetchall()

        cleaned_webhooks = 0
        for conn_row in connections:
            try:
                guild = self.bot.get_guild(conn_row['guild_id'])
                if guild:
                    webhooks = await guild.webhooks()
                    for wh in webhooks:
                        if wh.url == conn_row['webhook_url']:
                            await wh.delete()
                            cleaned_webhooks += 1
                            break
            except Exception as e:
                print(f"[CrossGuild] 删除 webhook 失败 ({conn_row['guild_id']}): {e}")

        # 删除数据库记录
        conn.execute("DELETE FROM bridge_connections WHERE bridge_id = ?", (bridge_id,))
        conn.execute("DELETE FROM bridges WHERE bridge_id = ?", (bridge_id,))
        conn.commit()
        conn.close()

        embed = discord.Embed(
            title="🗑 桥接已删除",
            description=f"**{bridge['name']}** (`{bridge_id}`) 已永久删除",
            color=0xED4245
        )
        embed.add_field(name="🧹 已清理", value=f"{len(connections)} 个连接记录，{cleaned_webhooks} 个 Webhook", inline=False)
        embed.set_footer(text=f"操作者: {interaction.user.display_name}")

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="bridge_info", description="ℹ️ 查看桥接详情")
    @app_commands.describe(bridge_id="桥接 ID")
    async def bridge_info(self, interaction: discord.Interaction, bridge_id: str):
        conn = _get_db()
        bridge = conn.execute(
            "SELECT * FROM bridges WHERE bridge_id = ?",
            (bridge_id,)
        ).fetchone()

        if not bridge:
            conn.close()
            await interaction.response.send_message(f"❌ 找不到桥接 `{bridge_id}`", ephemeral=True)
            return

        connections = conn.execute(
            "SELECT * FROM bridge_connections WHERE bridge_id = ?",
            (bridge_id,)
        ).fetchall()
        conn.close()

        embed = discord.Embed(
            title=f"🌉 桥接: {bridge['name']}",
            description=f"ID: `{bridge_id}`",
            color=0x5865F2
        )
        embed.add_field(name="👑 创建者", value=f"<@{bridge['owner_id']}>", inline=True)
        embed.add_field(name="📅 创建时间", value=bridge['created_at'][:19], inline=True)
        embed.add_field(name="🌐 连接数", value=str(len(connections)), inline=True)
        embed.add_field(
            name="📡 状态",
            value="🟢 活跃" if bridge['active'] else "🔴 非活跃",
            inline=True
        )

        if connections:
            conn_text = ""
            for c in connections:
                guild = self.bot.get_guild(c['guild_id'])
                guild_name = guild.name if guild else f"Unknown ({c['guild_id']})"
                channel = self.bot.get_channel(c['channel_id'])
                channel_name = f"#{channel.name}" if channel else f"#{c['channel_id']}"
                conn_text += f"• **{guild_name}** → {channel_name}\n"
            embed.add_field(name="📋 已连接的频道", value=conn_text, inline=False)

        await interaction.response.send_message(embed=embed)

    # ══════════════════════════════════════════════
    # 内部方法: 消息广播
    # ══════════════════════════════════════════════

    async def _broadcast(self, bridge_id: str, source_guild_id: int, source_channel_id: int,
                         content: str = None, embed: discord.Embed = None,
                         username: str = None, avatar_url: str = None):
        """向桥接中所有其他频道发送消息"""
        conn = _get_db()
        connections = conn.execute(
            "SELECT * FROM bridge_connections WHERE bridge_id = ?",
            (bridge_id,)
        ).fetchall()
        conn.close()

        for conn_row in connections:
            if conn_row['guild_id'] == source_guild_id and conn_row['channel_id'] == source_channel_id:
                continue  # 不给自己发

            webhook_url = conn_row['webhook_url']
            if not webhook_url:
                continue

            try:
                webhook = discord.Webhook.from_url(webhook_url, session=self.bot.http._HTTPClient__session)
                await webhook.send(
                    content=content,
                    embed=embed,
                    username=username or "FSBot Bridge",
                    avatar_url=avatar_url
                )
            except Exception as e:
                print(f"[CrossGuild] 广播失败 ({conn_row['guild_id']}): {e}")


# ══════════════════════════════════════════════
# on_message 监听 (在 main.py 中调用)
# ══════════════════════════════════════════════

async def handle_cross_guild_message(message: discord.Message):
    """处理跨服消息转发 (由 main.py on_message 调用)"""
    if message.author.bot:
        return
    if not message.guild:
        return

    conn = _get_db()
    connections = conn.execute(
        "SELECT DISTINCT bc.bridge_id, b.name FROM bridge_connections bc "
        "JOIN bridges b ON bc.bridge_id = b.bridge_id "
        "WHERE bc.guild_id = ? AND bc.channel_id = ? AND b.active = 1",
        (message.guild.id, message.channel.id)
    ).fetchall()
    conn.close()

    if not connections:
        return

    guild_name = message.guild.name
    author_name = message.author.display_name
    content = message.content[:1900] if message.content else ""

    embed = discord.Embed(
        description=content or "*[附件/图片]*",
        color=0x5865F2,
        timestamp=message.created_at
    )
    embed.set_author(name=f"{author_name} @ {guild_name}", icon_url=message.author.display_avatar.url)

    if message.attachments:
        # 取第一个图片附件作为 embed 图片
        for att in message.attachments:
            if att.content_type and att.content_type.startswith("image/"):
                embed.set_image(url=att.url)
                break

    if message.reference and message.reference.resolved:
        ref_msg = message.reference.resolved
        if isinstance(ref_msg, discord.Message):
            ref_text = ref_msg.content[:100] if ref_msg.content else "*[附件]*"
            embed.add_field(
                name=f"↩ 回复 {ref_msg.author.display_name}",
                value=f"> {ref_text}",
                inline=False
            )

    # 发送到所有连接的桥接
    for bridge_row in connections:
        conn2 = _get_db()
        all_conns = conn2.execute(
            "SELECT * FROM bridge_connections WHERE bridge_id = ?",
            (bridge_row['bridge_id'],)
        ).fetchall()
        conn2.close()

        for target in all_conns:
            if target['guild_id'] == message.guild.id and target['channel_id'] == message.channel.id:
                continue

            try:
                webhook = discord.Webhook.from_url(
                    target['webhook_url'],
                    session=message._state.http._HTTPClient__session
                )
                await webhook.send(
                    content=f"🌉 **{bridge_row['name']}**",
                    embed=embed,
                    username=author_name,
                    avatar_url=message.author.display_avatar.url
                )
            except Exception as e:
                print(f"[CrossGuild] 转发失败: {e}")


# ══════════════════════════════════════════════
# 模块初始化
# ══════════════════════════════════════════════

async def init_cross_guild(bot: commands.Bot):
    """注册 CrossGuild Cog"""
    global bot_ref
    bot_ref = bot
    init_db()
    await bot.add_cog(CrossGuild(bot))
    print("[CrossGuild] 跨服桥接模块已初始化 (/bridge_create, /bridge_connect, /bridge_disconnect, /bridge_list, /bridge_info)")
