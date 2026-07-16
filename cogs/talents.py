"""
FSBot Talents Cog -- 天赋查看与升级
"""
import discord
from discord.ext import commands
from discord import app_commands

from utils.db import conn, cursor, get_or_create_user, get_talents

TALENT_COST_BASE = 50
TALENT_MAX_LEVEL = 10


class TalentsCog(commands.Cog, name="Talents"):
    """天赋系统命令包"""

    def __init__(self, bot):
        self.bot = bot

    # ── /talents ──
    @app_commands.command(name="talents", description="查看天赋树 / View talents / 天賦 / Talents")
    async def talents(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        user = get_or_create_user(user_id, interaction.user.name)
        raw_talents = get_talents(user_id)
        power, luck, diligence, wisdom = raw_talents
        points = user[2]

        locale = str(interaction.locale)
        lang = 'zh' if locale.startswith('zh') else ('ja' if locale.startswith('ja') else ('fr' if locale.startswith('fr') else 'en'))

        if lang == 'zh':
            title = f"🌟 {interaction.user.display_name} 的天赋"
            desc = "使用 /upgrade 升级天赋，消耗积分"
            fields = [
                (f"💪 力量 Lv.{power}", f"Battle 战力 +{power*2} | 升级消耗: {TALENT_COST_BASE*(power+1)} ⭐"),
                (f"🍀 幸运 Lv.{luck}", f"游戏积分 +{luck*5}% | 升级消耗: {TALENT_COST_BASE*(luck+1)} ⭐"),
                (f"📅 勤奋 Lv.{diligence}", f"每日签到 +{diligence*2} 积分 | 升级消耗: {TALENT_COST_BASE*(diligence+1)} ⭐"),
                (f"📖 智慧 Lv.{wisdom}", f"经验获取 +{wisdom*5}% | 升级消耗: {TALENT_COST_BASE*(wisdom+1)} ⭐"),
            ]
            footer = f"当前积分: {points} ⭐ | 最大等级: {TALENT_MAX_LEVEL}"
        elif lang == 'ja':
            title = f"🌟 {interaction.user.display_name} の天賦"
            desc = "/upgrade で天賦をアップグレード（ポイント消費）"
            fields = [
                (f"💪 力量 Lv.{power}", f"Battle 戦力 +{power*2} | コスト: {TALENT_COST_BASE*(power+1)} ⭐"),
                (f"🍀 幸運 Lv.{luck}", f"ゲームポイント +{luck*5}% | コスト: {TALENT_COST_BASE*(luck+1)} ⭐"),
                (f"📅 勤勉 Lv.{diligence}", f"チェックイン +{diligence*2} | コスト: {TALENT_COST_BASE*(diligence+1)} ⭐"),
                (f"📖 知恵 Lv.{wisdom}", f"EXP +{wisdom*5}% | コスト: {TALENT_COST_BASE*(wisdom+1)} ⭐"),
            ]
            footer = f"現在のポイント: {points} ⭐ | 最大レベル: {TALENT_MAX_LEVEL}"
        elif lang == 'fr':
            title = f"🌟 Talents de {interaction.user.display_name}"
            desc = "Utilise /upgrade pour améliorer tes talents (coûte des points)"
            fields = [
                (f"💪 Puissance Lv.{power}", f"Battle +{power*2} | Coût : {TALENT_COST_BASE*(power+1)} ⭐"),
                (f"🍀 Chance Lv.{luck}", f"Points de jeu +{luck*5}% | Coût : {TALENT_COST_BASE*(luck+1)} ⭐"),
                (f"📅 Diligence Lv.{diligence}", f"Check-in +{diligence*2} | Coût : {TALENT_COST_BASE*(diligence+1)} ⭐"),
                (f"📖 Sagesse Lv.{wisdom}", f"EXP +{wisdom*5}% | Coût : {TALENT_COST_BASE*(wisdom+1)} ⭐"),
            ]
            footer = f"Points actuels : {points} ⭐ | Niveau max : {TALENT_MAX_LEVEL}"
        else:
            title = f"🌟 {interaction.user.display_name}'s Talents"
            desc = "Use /upgrade to level up talents (costs points)"
            fields = [
                (f"💪 Power Lv.{power}", f"Battle power +{power*2} | Cost: {TALENT_COST_BASE*(power+1)} ⭐"),
                (f"🍀 Luck Lv.{luck}", f"Game points +{luck*5}% | Cost: {TALENT_COST_BASE*(luck+1)} ⭐"),
                (f"📅 Diligence Lv.{diligence}", f"Daily check-in +{diligence*2} | Cost: {TALENT_COST_BASE*(diligence+1)} ⭐"),
                (f"📖 Wisdom Lv.{wisdom}", f"EXP gain +{wisdom*5}% | Cost: {TALENT_COST_BASE*(wisdom+1)} ⭐"),
            ]
            footer = f"Current points: {points} ⭐ | Max level: {TALENT_MAX_LEVEL}"

        embed = discord.Embed(title=title, description=desc, color=discord.Color.dark_purple())
        for name, value in fields:
            embed.add_field(name=name, value=value, inline=False)
        embed.set_footer(text=footer)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /upgrade ──
    @app_commands.command(name="upgrade", description="升级天赋 / Upgrade talent / 天賦アップグレード / Améliorer talent")
    @app_commands.describe(talent="选择天赋 / Select talent")
    @app_commands.choices(talent=[
        app_commands.Choice(name="💪 力量 / Power", value="power"),
        app_commands.Choice(name="🍀 幸运 / Luck", value="luck"),
        app_commands.Choice(name="📅 勤奋 / Diligence", value="diligence"),
        app_commands.Choice(name="📖 智慧 / Wisdom", value="wisdom"),
    ])
    async def upgrade(self, interaction: discord.Interaction, talent: app_commands.Choice[str]):
        user_id = interaction.user.id
        user = get_or_create_user(user_id, interaction.user.name)
        points = user[2]
        raw_talents = get_talents(user_id)
        talent_map = {'power': 0, 'luck': 1, 'diligence': 2, 'wisdom': 3}
        col_map = {'power': 'talent_power', 'luck': 'talent_luck', 'diligence': 'talent_diligence', 'wisdom': 'talent_wisdom'}

        idx = talent_map[talent.value]
        current_lv = raw_talents[idx]

        locale = str(interaction.locale)
        lang = 'zh' if locale.startswith('zh') else ('ja' if locale.startswith('ja') else ('fr' if locale.startswith('fr') else 'en'))

        talent_names = {
            'power': {'zh': '力量', 'en': 'Power', 'ja': '力量', 'fr': 'Puissance'},
            'luck': {'zh': '幸运', 'en': 'Luck', 'ja': '幸運', 'fr': 'Chance'},
            'diligence': {'zh': '勤奋', 'en': 'Diligence', 'ja': '勤勉', 'fr': 'Diligence'},
            'wisdom': {'zh': '智慧', 'en': 'Wisdom', 'ja': '知恵', 'fr': 'Sagesse'},
        }
        tname = talent_names[talent.value][lang]

        if current_lv >= TALENT_MAX_LEVEL:
            if lang == 'zh':
                msg = f"❌ {tname} 已达到最大等级 ({TALENT_MAX_LEVEL})！"
            elif lang == 'ja':
                msg = f"❌ {tname} は既に最大レベル ({TALENT_MAX_LEVEL}) です！"
            elif lang == 'fr':
                msg = f"❌ {tname} est déjà au niveau max ({TALENT_MAX_LEVEL}) !"
            else:
                msg = f"❌ {tname} is already at max level ({TALENT_MAX_LEVEL})!"
            await interaction.response.send_message(msg, ephemeral=True)
            return

        cost = TALENT_COST_BASE * (current_lv + 1)
        if points < cost:
            if lang == 'zh':
                msg = f"❌ 积分不足！升级 {tname} 需要 **{cost}** ⭐，你只有 **{points}** ⭐。"
            elif lang == 'ja':
                msg = f"❌ ポイントが足りません！{tname} のアップグレードに **{cost}** ⭐必要ですが、**{points}** ⭐しかありません。"
            elif lang == 'fr':
                msg = f"❌ Pas assez de points ! L'amélioration de {tname} coûte **{cost}** ⭐, mais tu n'en as que **{points}** ⭐."
            else:
                msg = f"❌ Not enough points! Upgrading {tname} costs **{cost}** ⭐, but you only have **{points}** ⭐."
            await interaction.response.send_message(msg, ephemeral=True)
            return

        new_points = points - cost
        cursor.execute(
            f"UPDATE users SET points = ?, {col_map[talent.value]} = ? WHERE user_id = ?",
            (new_points, current_lv + 1, user_id)
        )
        conn.commit()

        if lang == 'zh':
            msg = f"🎉 {tname} 升级到 Lv.{current_lv + 1}！消耗 **{cost}** ⭐ | 剩余积分: **{new_points}** ⭐"
        elif lang == 'ja':
            msg = f"🎉 {tname} が Lv.{current_lv + 1} にアップグレード！**{cost}** ⭐消費 | 残りポイント: **{new_points}** ⭐"
        elif lang == 'fr':
            msg = f"🎉 {tname} est passé au niveau {current_lv + 1} ! **{cost}** ⭐ dépensés | Points restants : **{new_points}** ⭐"
        else:
            msg = f"🎉 {tname} upgraded to Lv.{current_lv + 1}! Spent **{cost}** ⭐ | Remaining: **{new_points}** ⭐"

        await interaction.response.send_message(msg, ephemeral=True)


async def setup(bot):
    await bot.add_cog(TalentsCog(bot))
