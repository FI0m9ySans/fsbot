"""
FSBot User System Cog -- 签到 / 余额 / 等级 / 排行榜
"""
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime

from utils.db import conn, cursor, get_or_create_user, update_user_points, add_exp, get_talents, level_to_exp_required, record_daily_checkin


class UserSystemCog(commands.Cog, name="User"):
    """用户系统命令包"""

    def __init__(self, bot):
        self.bot = bot

    # ── /daily ──
    @app_commands.command(name="daily", description="每日签到领取积分")
    async def daily(self, interaction: discord.Interaction):
        await interaction.response.defer()
        user_id = interaction.user.id
        username = interaction.user.name
        user = get_or_create_user(user_id, username)

        today = datetime.now().strftime("%Y-%m-%d")

        if user[3] == today:
            await interaction.followup.send(
                "❌ 你今天已经签到过了！明天再来吧。| You've already checked in today! Come back tomorrow. | 今日はもうチェックインしたよ！また明日来てね。 | Tu t'es déjà connecté aujourd'hui ! Reviens demain.",
                ephemeral=True
            )
            return

        wisdom = get_talents(user_id)[3]
        exp_gain = int(100 * (1 + wisdom * 0.05))
        leveled_up, new_level, new_exp = add_exp(user_id, exp_gain)

        diligence = get_talents(user_id)[2]
        daily_bonus = 20 + (diligence * 2)
        new_points = user[2] + daily_bonus
        update_user_points(user_id, new_points, today)

        # S1 麦收季：记录签到时间戳（用于 Dashboard 每日排行榜）
        checkin_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        record_daily_checkin(user_id, username, checkin_iso)

        locale = str(interaction.locale)
        if locale.startswith('zh'):
            title = "✅ 签到成功！"
            desc = f"你获得了 **{exp_gain}** EXP (+{daily_bonus} 积分)。"
        elif locale.startswith('ja'):
            title = "✅ チェックイン成功！"
            desc = f"**{exp_gain}** EXP (+{daily_bonus} ポイント)を獲得しました。"
        elif locale.startswith('fr'):
            title = "✅ Check-in réussi !"
            desc = f"Tu as gagné **{exp_gain}** EXP (+{daily_bonus} points)."
        else:
            title = "✅ Check-in successful!"
            desc = f"You earned **{exp_gain}** EXP (+{daily_bonus} points)."

        embed = discord.Embed(title=title, description=desc, color=discord.Color.green())
        embed.add_field(name="💞 Total EXP", value=f"**{new_exp}** EXP", inline=True)
        embed.add_field(name="❤️ Love Level", value=f"**{new_level}**", inline=True)
        embed.add_field(name="⭐ Points", value=f"**{new_points}**", inline=True)

        if leveled_up:
            if locale.startswith('zh'):
                embed.add_field(name="🎉 升级！", value=f"你的 Love 等级提升到 **{new_level}**！", inline=False)
            elif locale.startswith('ja'):
                embed.add_field(name="🎉 レベルアップ！", value=f"Loveレベルが **{new_level}** に上がりました！", inline=False)
            elif locale.startswith('fr'):
                embed.add_field(name="🎉 Niveau supérieur !", value=f"Ton niveau Love est maintenant **{new_level}** !", inline=False)
            else:
                embed.add_field(name="🎉 Level Up!", value=f"Your Love Level is now **{new_level}**!", inline=False)

        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        await interaction.followup.send(embed=embed)

    # ── /balance ──
    @app_commands.command(name="balance", description="查看你的当前积分与等级 / View points & level / ポイントとレベル / Voir points & niveau")
    async def balance(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        username = interaction.user.name
        user = get_or_create_user(user_id, username)
        points = user[2]
        monthly_points = user[10] if len(user) > 10 else 0
        exp = user[4] if len(user) > 4 else 0
        level = user[5] if len(user) > 5 else 0

        locale = str(interaction.locale)
        if locale.startswith('zh'):
            title = f"💰 {interaction.user.display_name} 的个人资料"
            fields = [
                ("⭐ 永久积分", str(points)),
                ("📊 月度积分", str(monthly_points)),
                ("❤️ Love 等级", str(level)),
                ("经验值 (EXP)", f"{exp} / {level_to_exp_required(level)}"),
            ]
        elif locale.startswith('ja'):
            title = f"💰 {interaction.user.display_name} のプロフィール"
            fields = [
                ("⭐ 永久ポイント", str(points)),
                ("📊 月間ポイント", str(monthly_points)),
                ("❤️ Loveレベル", str(level)),
                ("経験値 (EXP)", f"{exp} / {level_to_exp_required(level)}"),
            ]
        elif locale.startswith('fr'):
            title = f"💰 Profil de {interaction.user.display_name}"
            fields = [
                ("⭐ Points permanents", str(points)),
                ("📊 Points mensuels", str(monthly_points)),
                ("❤️ Niveau Love", str(level)),
                ("EXP", f"{exp} / {level_to_exp_required(level)}"),
            ]
        else:
            title = f"💰 {interaction.user.display_name}'s Profile"
            fields = [
                ("⭐ Permanent Points", str(points)),
                ("📊 Monthly Points", str(monthly_points)),
                ("❤️ Love Level", str(level)),
                ("EXP", f"{exp} / {level_to_exp_required(level)}"),
            ]

        embed = discord.Embed(title=title, color=discord.Color.gold())
        for name, value in fields:
            embed.add_field(name=name, value=value, inline=True)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /rank ──
    @app_commands.command(name="rank", description="查看等级卡 / View rank card / ランクカード / Voir carte de niveau")
    async def rank(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        username = interaction.user.name
        user = get_or_create_user(user_id, username)
        exp = user[4] if len(user) > 4 else 0
        level = user[5] if len(user) > 5 else 0
        points = user[2]
        monthly_points = user[10] if len(user) > 10 else 0

        locale = str(interaction.locale)
        if locale.startswith('zh'):
            title = f"🏆 {interaction.user.display_name} 的等级卡"
            desc = "Love 等级反映了你在这个社区的活跃度 ❤️"
            fields = [
                ("❤️ Love 等级", f"**{level}**"),
                ("✨ 总经验值", f"**{exp}** EXP"),
                ("⭐ 永久积分", f"**{points}**"),
                ("📊 月度积分", f"**{monthly_points}**"),
                ("📈 距离下一级", f"**{level_to_exp_required(level) - exp}** EXP")
            ]
            footer = "线性升级: 每级所需EXP递增 | 签到+100 | 消息+10 | 反应+5"
        elif locale.startswith('ja'):
            title = f"🏆 {interaction.user.display_name} のランクカード"
            desc = "Loveレベルはこのコミュニティでの活躍度を示します ❤️"
            fields = [
                ("❤️ Loveレベル", f"**{level}**"),
                ("✨ 総経験値", f"**{exp}** EXP"),
                ("⭐ 永久ポイント", f"**{points}**"),
                ("📊 月間ポイント", f"**{monthly_points}**"),
                ("📈 次のレベルまで", f"**{level_to_exp_required(level) - exp}** EXP")
            ]
            footer = "線形レベルアップ: 毎レベル必要EXP増加 | チェックイン+100 | メッセージ+10 | リアクション+5"
        elif locale.startswith('fr'):
            title = f"🏆 Carte de niveau de {interaction.user.display_name}"
            desc = "Le niveau Love reflète ton activité dans cette communauté ❤️"
            fields = [
                ("❤️ Niveau Love", f"**{level}**"),
                ("✨ EXP total", f"**{exp}** EXP"),
                ("⭐ Points permanents", f"**{points}**"),
                ("📊 Points mensuels", f"**{monthly_points}**"),
                ("📈 Prochain niveau", f"**{level_to_exp_required(level) - exp}** EXP")
            ]
            footer = "Montée linéaire : EXP requis augmente | Check-in +100 | Message +10 | Réaction +5"
        else:
            title = f"🏆 {interaction.user.display_name}'s Rank Card"
            desc = "Love Level reflects your activity in this community ❤️"
            fields = [
                ("❤️ Love Level", f"**{level}**"),
                ("✨ Total EXP", f"**{exp}** EXP"),
                ("⭐ Permanent Points", f"**{points}**"),
                ("📊 Monthly Points", f"**{monthly_points}**"),
                ("📈 Next Level", f"**{level_to_exp_required(level) - exp}** EXP")
            ]
            footer = "Linear leveling: EXP required increases each level | Daily +100 | Message +10 | Reaction +5"

        embed = discord.Embed(title=title, description=desc, color=discord.Color.purple())
        for name, value in fields:
            embed.add_field(name=name, value=value, inline=(name != fields[-1][0]))
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text=footer)

        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /leaderboard ──
    @app_commands.command(name="leaderboard", description="查看积分排行榜 / View points leaderboard / ポイントランキング / Classement des points")
    async def leaderboard(self, interaction: discord.Interaction):
        await interaction.response.defer()
        locale = str(interaction.locale)
        lang = 'zh' if locale.startswith('zh') else ('ja' if locale.startswith('ja') else ('fr' if locale.startswith('fr') else 'en'))

        cursor.execute("SELECT user_id, username, monthly_points FROM users WHERE monthly_points > 0 ORDER BY monthly_points DESC LIMIT 10")
        rows = cursor.fetchall()

        if lang == 'zh':
            title = "🏆 月度积分排行榜 Top 10"
            desc = "以下是本月积分最高的用户（每月1日清零结算）："
            no_data = "暂无数据，快去签到和玩游戏赚积分吧！"
            rank_header = "排名"
            user_header = "用户"
            pts_header = "月度积分"
            footer = "月度积分每月1日清零 | 永久积分用于商店兑换 | /daily 每日签到"
        elif lang == 'ja':
            title = "🏆 月間ポイントランキング Top 10"
            desc = "今月のポイント上位ユーザー（毎月1日にリセット）："
            no_data = "データがありません。チェックインやゲームでポイントを獲得しましょう！"
            rank_header = "順位"
            user_header = "ユーザー"
            pts_header = "月間ポイント"
            footer = "月間ポイントは毎月1日にリセット | 永久ポイントはショップで使用 | /daily で毎日チェックイン"
        elif lang == 'fr':
            title = "🏆 Classement mensuel Top 10"
            desc = "Utilisateurs avec le plus de points mensuels (réinitialisés le 1er de chaque mois) :"
            no_data = "Aucune donnée. Gagne des points avec les jeux et le check-in !"
            rank_header = "Rang"
            user_header = "Utilisateur"
            pts_header = "Points mensuels"
            footer = "Points mensuels réinitialisés le 1er | Points permanents pour la boutique | /daily pour le check-in"
        else:
            title = "🏆 Monthly Points Leaderboard Top 10"
            desc = "Users with the most monthly points (reset on the 1st of each month):"
            no_data = "No data yet. Earn points by playing games and daily check-in!"
            rank_header = "Rank"
            user_header = "User"
            pts_header = "Monthly Pts"
            footer = "Monthly points reset on the 1st | Permanent points for shop | /daily for check-in"

        embed = discord.Embed(title=title, description=desc, color=discord.Color.gold())

        if not rows:
            embed.add_field(name="📭", value=no_data, inline=False)
        else:
            medals = {0: '🥇', 1: '🥈', 2: '🥉'}
            rank_lines = []
            user_lines = []
            pts_lines = []
            for i, (uid, uname, pts) in enumerate(rows):
                rank_lines.append(medals.get(i, f'**#{i+1}**'))
                try:
                    member = interaction.guild.get_member(uid) if interaction.guild else None
                    display = member.display_name if member else str(uname)
                except:
                    display = str(uname)
                user_lines.append(display)
                pts_lines.append(f'**{pts}** ⭐')

            embed.add_field(name=rank_header, value='\n'.join(rank_lines), inline=True)
            embed.add_field(name=user_header, value='\n'.join(user_lines), inline=True)
            embed.add_field(name=pts_header, value='\n'.join(pts_lines), inline=True)

        embed.set_footer(text=footer)
        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(UserSystemCog(bot))
