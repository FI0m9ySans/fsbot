"""
FSBot admin Cog -- 基础管理命令
/ping /hello /stats /role /undertale /serverking !clear
"""
import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime

from utils.db import conn, cursor
from utils.guards import OWNER_ID, get_lockdown_mode, set_lockdown_mode, is_owner, is_admin


class AdminCog(commands.Cog, name="Admin"):
    """基础管理命令包"""

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print("[Cog:Admin] 已加载")

    # ── 全局权限检查（ServerKing 锁） ──
    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        """等效于 bot.tree.interaction_check，但 Cog 不支持直接注册 tree check"""
        pass  # interaction_check 留在 main.py

    # ── /hello ──
    @app_commands.command(name="hello", description="让机器人跟你打招呼")
    async def hello(self, interaction: discord.Interaction):
        locale = str(interaction.locale)
        if locale.startswith('zh'):
            title = "你好！👋"
            desc = f"{interaction.user.mention}，我是 **FI0m9ySans's Bot**，一个多功能 Discord 机器人！"
        elif locale.startswith('ja'):
            title = "こんにちは！👋"
            desc = f"{interaction.user.mention}、私は **FI0m9ySans's Bot**、多機能 Discord ボットだよ！"
        elif locale.startswith('fr'):
            title = "Salut！👋"
            desc = f"{interaction.user.mention}, je suis **FI0m9ySans's Bot**, un bot Discord multifonction !"
        else:
            title = "Hello！👋"
            desc = f"{interaction.user.mention}, I am **FI0m9ySans's Bot**, a multi-function Discord bot!"

        embed = discord.Embed(title=title, description=desc, color=discord.Color.blue())
        embed.set_thumbnail(url=interaction.client.user.display_avatar.url)
        embed.add_field(name="🌍 Languages / 语言", value="🇨🇳 zh | 🇬🇧 en | 🇯🇵 ja | 🇫🇷 fr", inline=False)
        await interaction.response.send_message(embed=embed)

    # ── /ping ──
    @app_commands.command(name="ping", description="查看机器人的网络延迟")
    async def ping(self, interaction: discord.Interaction):
        latency = round(self.bot.latency * 1000)

        if latency < 100:
            color = discord.Color.green()
            quality = "🟢 Excellent / 优秀"
        elif latency < 300:
            color = discord.Color.orange()
            quality = "🟡 Good / 良好"
        else:
            color = discord.Color.red()
            quality = "🔴 Poor / 较差"

        locale = str(interaction.locale)
        if locale.startswith('zh'):
            title = "🏓 Pong!"
            desc = f"我的延迟是 **{latency}** ms。"
        elif locale.startswith('ja'):
            title = "🏓 Pong!"
            desc = f"私の遅延は **{latency}** ms です。"
        elif locale.startswith('fr'):
            title = "🏓 Pong !"
            desc = f"Ma latence est de **{latency}** ms."
        else:
            title = "🏓 Pong!"
            desc = f"My latency is **{latency}** ms."

        embed = discord.Embed(title=title, description=desc, color=color)
        embed.add_field(name="Quality / 质量", value=quality, inline=False)
        await interaction.response.send_message(embed=embed)

    # ── /undertale ──
    @app_commands.command(name="undertale", description="触发 UNDERTALE 专属彩蛋")
    async def undertale(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="But nobody came. 🎵",
            description="(但是没有人来。)\n(でも、誰も来なかった。)\n(Mais personne n'est venu.)",
            color=discord.Color.purple()
        )
        embed.set_footer(text="from Undertale")
        await interaction.response.send_message(embed=embed)

    # ── /stats ──
    @app_commands.command(name="stats", description="查看服务器统计数据 / View server stats / サーバー統計 / Statistiques")
    async def stats(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild = interaction.guild
        online_count = sum(1 for member in guild.members if member.status != discord.Status.offline)

        user_locale = str(interaction.locale)
        if user_locale.startswith('zh'):
            title = f"📊 {guild.name} 服务器统计"
            fields = [
                ("👥 总成员数", f"{guild.member_count} 人"),
                ("🟢 在线成员", f"{online_count} 人"),
                ("📝 文本频道", f"{len(guild.text_channels)} 个"),
                ("🎤 语音频道", f"{len(guild.voice_channels)} 个"),
                ("🎭 身份组数量", f"{len(guild.roles)} 个")
            ]
        elif user_locale.startswith('ja'):
            title = f"📊 {guild.name} サーバー統計"
            fields = [
                ("👥 総メンバー数", f"{guild.member_count} 人"),
                ("🟢 オンライン", f"{online_count} 人"),
                ("📝 テキストチャンネル", f"{len(guild.text_channels)} 個"),
                ("🎤 ボイスチャンネル", f"{len(guild.voice_channels)} 個"),
                ("🎭 ロール数", f"{len(guild.roles)} 個")
            ]
        elif user_locale.startswith('fr'):
            title = f"📊 Statistiques de {guild.name}"
            fields = [
                ("👥 Membres", f"{guild.member_count}"),
                ("🟢 En ligne", f"{online_count}"),
                ("📝 Salons textuels", f"{len(guild.text_channels)}"),
                ("🎤 Salons vocaux", f"{len(guild.voice_channels)}"),
                ("🎭 Roles", f"{len(guild.roles)}")
            ]
        else:
            title = f"📊 {guild.name} Server Stats"
            fields = [
                ("👥 Total Members", f"{guild.member_count}"),
                ("🟢 Online", f"{online_count}"),
                ("📝 Text Channels", f"{len(guild.text_channels)}"),
                ("🎤 Voice Channels", f"{len(guild.voice_channels)}"),
                ("🎭 Roles", f"{len(guild.roles)}")
            ]

        embed = discord.Embed(title=title, color=discord.Color.blurple(), timestamp=datetime.now())
        for name, value in fields:
            embed.add_field(name=name, value=value, inline=True)
        embed.set_footer(text=f"Requested by {interaction.user.display_name}")
        await interaction.followup.send(embed=embed)

    # ── /role ──
    @app_commands.command(name="role", description="获取或移除游戏身份组 / Get or remove game role / ゲームロールを取得・削除")
    @app_commands.describe(action="你要添加还是移除身份组？", game="选择你想获取身份组的游戏")
    @app_commands.choices(action=[
        app_commands.Choice(name="添加 / Add / 追加", value="add"),
        app_commands.Choice(name="移除 / Remove / 削除", value="remove"),
    ])
    @app_commands.choices(game=[
        app_commands.Choice(name="UNDERTALE", value="undertale"),
        app_commands.Choice(name="DELTARUNE", value="deltarune"),
        app_commands.Choice(name="MINECRAFT", value="minecraft"),
        app_commands.Choice(name="World of Goo", value="world-of-goo"),
        app_commands.Choice(name="Plants vs Zombies", value="plants-vs-zombies"),
        app_commands.Choice(name="WorldBox", value="worldbox"),
        app_commands.Choice(name="Just Shapes & Beats", value="jsb"),
        app_commands.Choice(name="OSU!", value="osu"),
    ])
    async def role(self, interaction: discord.Interaction, action: app_commands.Choice[str], game: app_commands.Choice[str]):
        role_mapping = {
            'undertale': 1516910099459997715,
            'deltarune': 1516910159593607228,
            'minecraft': 1516910198437187778,
            'world-of-goo': 1516936561088925746,
            'plants-vs-zombies': 1516936451282178280,
            'worldbox': 1516936327755468860,
            'jsb': 1516937473811546252,
            'osu': 1516944039377768559,
        }
        target_role_id = role_mapping.get(game.value)
        role_obj = interaction.guild.get_role(target_role_id)

        if not role_obj:
            await interaction.response.send_message(f"❌ 找不到身份组 (Role not found) ID: {target_role_id}", ephemeral=True)
            return

        locale = str(interaction.locale)
        if locale.startswith('zh'):
            already_has = f"✅ 你已经拥有 {role_obj.mention} 身份组了！"
            added = f"🎉 成功为你添加 {role_obj.mention} 身份组！"
            not_have = f"❌ 你没有 {role_obj.mention} 身份组。"
            removed = f"✅ 已移除你的 {role_obj.mention} 身份组。"
        elif locale.startswith('ja'):
            already_has = f"✅ すでに {role_obj.mention} ロールを持っています！"
            added = f"🎉 {role_obj.mention} ロールを追加しました！"
            not_have = f"❌ {role_obj.mention} ロールを持っていません。"
            removed = f"✅ {role_obj.mention} ロールを削除しました。"
        elif locale.startswith('fr'):
            already_has = f"✅ Tu as déjà le rôle {role_obj.mention} !"
            added = f"🎉 Le rôle {role_obj.mention} t'a été ajouté !"
            not_have = f"❌ Tu n'as pas le rôle {role_obj.mention}."
            removed = f"✅ Le rôle {role_obj.mention} a été retiré."
        else:
            already_has = f"✅ You already have the {role_obj.mention} role!"
            added = f"🎉 Successfully added the {role_obj.mention} role!"
            not_have = f"❌ You don't have the {role_obj.mention} role."
            removed = f"✅ Removed the {role_obj.mention} role."

        if action.value == 'add':
            if role_obj in interaction.user.roles:
                await interaction.response.send_message(already_has, ephemeral=True)
            else:
                try:
                    await interaction.user.add_roles(role_obj)
                    await interaction.response.send_message(added, ephemeral=True)
                except discord.Forbidden:
                    await interaction.response.send_message(
                        "❌ 机器人权限不足！请在服务器设置中将 Bot 的身份组拖到所有游戏身份组的**上方**。\n"
                        "❌ Bot lacks permission! Please drag the Bot's role above all game roles in Server Settings.",
                        ephemeral=True
                    )
        elif action.value == 'remove':
            if role_obj not in interaction.user.roles:
                await interaction.response.send_message(not_have, ephemeral=True)
            else:
                try:
                    await interaction.user.remove_roles(role_obj)
                    await interaction.response.send_message(removed, ephemeral=True)
                except discord.Forbidden:
                    await interaction.response.send_message(
                        "❌ 机器人权限不足！请在服务器设置中将 Bot 的身份组拖到所有游戏身份组的**上方**。\n"
                        "❌ Bot lacks permission! Please drag the Bot's role above all game roles in Server Settings.",
                        ephemeral=True
                    )
        else:
            await interaction.response.send_message("❌ Invalid action.", ephemeral=True)

    # ── /serverking ──
    @app_commands.command(name="serverking", description="ServerKing 模式 — 锁定服主命令权限")
    @app_commands.describe(enable="True=锁定服主命令 / False=解除锁定")
    async def serverking(self, interaction: discord.Interaction, enable: bool):
        """ServerKing 全局锁：开启后服主所有命令被拦截，只有 /serverking 可用"""
        if interaction.user.id != OWNER_ID:
            await interaction.response.send_message("❌ 只有服主可以使用此命令。", ephemeral=True)
            return

        set_lockdown_mode(enable)
        if get_lockdown_mode():
            await interaction.response.send_message(
                "👑 **ServerKing 模式已开启**\n服主的所有命令已被锁定，只有 `/serverking False` 可以解锁。",
                ephemeral=False
            )
        else:
            await interaction.response.send_message(
                "✅ **ServerKing 模式已关闭**\n服主命令权限已恢复。",
                ephemeral=False
            )


async def setup(bot):
    await bot.add_cog(AdminCog(bot))
