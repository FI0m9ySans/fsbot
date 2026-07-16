"""
FSBot Shop Cog -- 积分商店 / 每月结算 / 自动 Bump / 转账
"""
import asyncio
import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta

from utils.db import conn, cursor, get_or_create_user, deduct_points, get_meta, set_meta


# ── 商店配置 ──
SHOP_ITEMS = {
    'no_slow': {
        'role_id': 1517070986606805012,
        'price': 1000,
        'name': {'zh': 'No Slow（不再慢速）', 'en': 'No Slow', 'ja': 'No Slow', 'fr': 'No Slow'},
    },
    'promote': {
        'role_id': 1517202067859574856,
        'price': 3500,
        'name': {'zh': 'Promote your own server（宣传你自己的服务器）', 'en': 'Promote your own server', 'ja': 'Promote your own server', 'fr': 'Promote your own server'},
    },
    'thread_mgr': {
        'role_id': 1517385970171904081,
        'price': 5000,
        'name': {'zh': 'Thread Manager2（子区创建者2）', 'en': 'Thread Manager2', 'ja': 'Thread Manager2', 'fr': 'Thread Manager2'},
    },
}


class ShopCog(commands.Cog, name="Shop"):
    """积分商店 + 月度结算 + Bump 提醒"""

    BUMP_CHANNEL_ID = 1516860607217926316
    MONTHLY_LEADERBOARD_CHANNEL_ID = 1517382763706323075
    _monthly_settled = None

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        ShopCog._monthly_settled = get_meta('monthly_settled', None)
        print(f"[Cog:Shop] 月度结算状态: {ShopCog._monthly_settled}")

    # ── /pointshop ──
    @app_commands.command(name="pointshop", description="查看积分商店 / View point shop / ポイントショップ / Boutique de points")
    async def pointshop(self, interaction: discord.Interaction):
        locale = str(interaction.locale)
        if locale.startswith('zh'):
            title = "🛒 积分商店"
            desc = "使用永久积分兑换身份组！（永久积分不会被月度清零）"
            price_label = "价格"
        elif locale.startswith('ja'):
            title = "🛒 ポイントショップ"
            desc = "永久ポイントでロールを交換しよう！（永久ポイントは月間リセットの対象外）"
            price_label = "価格"
        elif locale.startswith('fr'):
            title = "🛒 Boutique de points"
            desc = "Échange tes points permanents contre des rôles ! (non affectés par la réinitialisation mensuelle)"
            price_label = "Prix"
        else:
            title = "🛒 Point Shop"
            desc = "Redeem permanent points for roles! (not affected by monthly reset)"
            price_label = "Price"

        embed = discord.Embed(title=title, description=desc, color=discord.Color.orange())
        for key, item in SHOP_ITEMS.items():
            name = item['name'].get('zh' if locale.startswith('zh') else ('ja' if locale.startswith('ja') else ('fr' if locale.startswith('fr') else 'en')), item['name']['en'])
            embed.add_field(name=name, value=f"{price_label}: **{item['price']}** ⭐", inline=False)
        embed.set_footer(text="使用 /redeem 兑换商品 | Use /redeem to redeem")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /redeem ──
    @app_commands.command(name="redeem", description="兑换积分商店商品 / Redeem shop item / 商品を交換 / Échanger un article")
    @app_commands.describe(item="选择你想兑换的商品")
    @app_commands.choices(item=[
        app_commands.Choice(name="No Slow", value="no_slow"),
        app_commands.Choice(name="Promote your own server", value="promote"),
        app_commands.Choice(name="Thread Manager2", value="thread_mgr"),
    ])
    async def redeem(self, interaction: discord.Interaction, item: app_commands.Choice[str]):
        user_id = interaction.user.id
        user = get_or_create_user(user_id, interaction.user.name)
        points = user[2]

        shop_item = SHOP_ITEMS.get(item.value)
        if not shop_item:
            await interaction.response.send_message("❌ 商品不存在 | Item not found", ephemeral=True)
            return

        locale = str(interaction.locale)
        item_name = shop_item['name'].get('zh' if locale.startswith('zh') else ('ja' if locale.startswith('ja') else ('fr' if locale.startswith('fr') else 'en')), shop_item['name']['en'])

        if shop_item['role_id'] == 0:
            await interaction.response.send_message(
                "❌ 该商品尚未配置身份组 ID，请联系管理员。\n"
                "❌ This item has not been configured with a role ID yet. Please contact an admin.",
                ephemeral=True
            )
            return

        role = interaction.guild.get_role(shop_item['role_id'])
        if not role:
            await interaction.response.send_message(
                "❌ 找不到对应的身份组，请检查配置。\n"
                "❌ Corresponding role not found. Please check configuration.",
                ephemeral=True
            )
            return

        if role in interaction.user.roles:
            if locale.startswith('zh'):
                msg = f"✅ 你已经拥有 {role.mention} 身份组了！"
            elif locale.startswith('ja'):
                msg = f"✅ すでに {role.mention} ロールを持っています！"
            elif locale.startswith('fr'):
                msg = f"✅ Tu as déjà le rôle {role.mention} !"
            else:
                msg = f"✅ You already have the {role.mention} role!"
            await interaction.response.send_message(msg, ephemeral=True)
            return

        if points < shop_item['price']:
            if locale.startswith('zh'):
                msg = f"❌ 积分不足！你需要 **{shop_item['price']}** ⭐，当前只有 **{points}** ⭐。"
            elif locale.startswith('ja'):
                msg = f"❌ ポイントが足りません！**{shop_item['price']}** ⭐必要ですが、現在は**{points}** ⭐しかありません。"
            elif locale.startswith('fr'):
                msg = f"❌ Pas assez de points ! Tu as besoin de **{shop_item['price']}** ⭐, mais tu n'en as que **{points}** ⭐."
            else:
                msg = f"❌ Not enough points! You need **{shop_item['price']}** ⭐, but you only have **{points}** ⭐."
            await interaction.response.send_message(msg, ephemeral=True)
            return

        success, new_points = deduct_points(user_id, shop_item['price'])
        if not success:
            await interaction.response.send_message("❌ 扣除积分失败 | Failed to deduct points", ephemeral=True)
            return

        try:
            await interaction.user.add_roles(role)
            if locale.startswith('zh'):
                msg = f"🎉 兑换成功！你花费了 **{shop_item['price']}** ⭐ 获得了 {role.mention} 身份组！\n💰 剩余积分: **{new_points}** ⭐"
            elif locale.startswith('ja'):
                msg = f"🎉 交換成功！**{shop_item['price']}** ⭐を消費して {role.mention} ロールを獲得しました！\n💰 残りポイント: **{new_points}** ⭐"
            elif locale.startswith('fr'):
                msg = f"🎉 Échange réussi ! Tu as dépensé **{shop_item['price']}** ⭐ pour obtenir le rôle {role.mention} !\n💰 Points restants : **{new_points}** ⭐"
            else:
                msg = f"🎉 Redemption successful! You spent **{shop_item['price']}** ⭐ to get the {role.mention} role!\n💰 Remaining points: **{new_points}** ⭐"
            await interaction.response.send_message(msg, ephemeral=True)
        except discord.Forbidden:
            cursor.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (shop_item['price'], user_id))
            conn.commit()
            await interaction.response.send_message(
                "❌ 机器人权限不足，无法分配身份组。已退回积分。\n"
                "❌ Bot lacks permission to assign this role. Points have been refunded.",
                ephemeral=True
            )

    # ── /transfer ──
    @app_commands.command(name="transfer", description="转账积分给其他用户 / Transfer points / ポイントを送る / Transférer des points")
    @app_commands.describe(target="接收积分的用户", amount="转账金额")
    async def transfer(self, interaction: discord.Interaction, target: discord.Member, amount: int):
        locale = str(interaction.locale)
        if amount <= 0:
            if locale.startswith('zh'):
                msg = "❌ 转账金额必须大于 0！"
            else:
                msg = "❌ Transfer amount must be greater than 0!"
            await interaction.response.send_message(msg, ephemeral=True)
            return

        if target.bot:
            if locale.startswith('zh'):
                msg = "❌ 不能转账给机器人！"
            else:
                msg = "❌ Cannot transfer to a bot!"
            await interaction.response.send_message(msg, ephemeral=True)
            return

        if target.id == interaction.user.id:
            if locale.startswith('zh'):
                msg = "❌ 不能转账给自己！"
            else:
                msg = "❌ Cannot transfer to yourself!"
            await interaction.response.send_message(msg, ephemeral=True)
            return

        sender_id = interaction.user.id
        sender = get_or_create_user(sender_id, interaction.user.name)
        sender_points = sender[2]

        if sender_points < amount:
            if locale.startswith('zh'):
                msg = f"❌ 积分不足！你只有 **{sender_points}** ⭐，无法转账 **{amount}** ⭐。"
            elif locale.startswith('ja'):
                msg = f"❌ ポイントが足りません！現在**{sender_points}** ⭐、**{amount}** ⭐を送金できません。"
            elif locale.startswith('fr'):
                msg = f"❌ Pas assez de points ! Vous avez **{sender_points}** ⭐, impossible de transférer **{amount}** ⭐."
            else:
                msg = f"❌ Not enough points! You have **{sender_points}** ⭐, cannot transfer **{amount}** ⭐."
            await interaction.response.send_message(msg, ephemeral=True)
            return

        # 扣除发送方永久积分（不减月度积分）
        cursor.execute("UPDATE users SET points = points - ? WHERE user_id = ?", (amount, sender_id))
        # 增加接收方永久积分（不加月度积分，防止刷榜）
        get_or_create_user(target.id, target.name)
        cursor.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (amount, target.id))
        conn.commit()

        new_sender = sender_points - amount
        if locale.startswith('zh'):
            msg = f"✅ 成功转账 **{amount}** ⭐ 给 {target.mention}！\n💰 你的剩余积分: **{new_sender}** ⭐"
        elif locale.startswith('ja'):
            msg = f"✅ {target.mention} に **{amount}** ⭐ を送金しました！\n💰 残りポイント: **{new_sender}** ⭐"
        elif locale.startswith('fr'):
            msg = f"✅ **{amount}** ⭐ transférés à {target.mention} !\n💰 Vos points restants : **{new_sender}** ⭐"
        else:
            msg = f"✅ Transferred **{amount}** ⭐ to {target.mention}!\n💰 Your remaining points: **{new_sender}** ⭐"
        await interaction.response.send_message(msg, ephemeral=False)

    # ── 自动 Bump 任务 ──
    @tasks.loop(hours=2)
    async def auto_bump(self):
        channel = self.bot.get_channel(self.BUMP_CHANNEL_ID)
        if channel:
            try:
                embed = discord.Embed(
                    title="⏰ DISBOARD Bump 提醒",
                    description="该去 **/bump** 啦！点击输入框旁边的 `/` 选择 DISBOARD 的 `/bump` 命令来置顶服务器。",
                    color=discord.Color.green(),
                    timestamp=datetime.now()
                )
                embed.set_footer(text="每2小时提醒一次 | 由 FI0m9ySans Bot 自动发送")
                await channel.send("<@1516859801790054532>", embed=embed)
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 已发送 bump 提醒到频道 {self.BUMP_CHANNEL_ID}")
            except Exception as e:
                print(f"自动 bump 提醒失败: {e}")
        else:
            print(f"⚠️ 找不到 bump 提醒频道 ID: {self.BUMP_CHANNEL_ID}")

    @auto_bump.before_loop
    async def before_auto_bump(self):
        await self.bot.wait_until_ready()

    # ── 月度排行榜结算 ──
    @tasks.loop(minutes=30)
    async def monthly_leaderboard(self):
        now = datetime.now()
        month_key = now.strftime("%Y-%m")

        if now.day != 1:
            return

        if ShopCog._monthly_settled == month_key:
            return

        channel = self.bot.get_channel(self.MONTHLY_LEADERBOARD_CHANNEL_ID)
        if not channel:
            print(f"[月榜] ⚠️ 找不到结算频道 ID: {self.MONTHLY_LEADERBOARD_CHANNEL_ID}")
            return

        cursor.execute("SELECT user_id, username, monthly_points FROM users WHERE monthly_points > 0 ORDER BY monthly_points DESC LIMIT 10")
        rows = cursor.fetchall()

        last_month_dt = now.replace(day=1) - timedelta(days=1)
        last_month_labels = {
            'zh': last_month_dt.strftime("%Y年%m月"),
            'ja': last_month_dt.strftime("%Y年%m月"),
            'fr': last_month_dt.strftime("%B %Y"),
            'en': last_month_dt.strftime("%B %Y"),
        }

        _ml_title = {
            'zh': "🏆 积分月度排行榜结算",
            'ja': "🏆 月間ポイントランキング結果",
            'fr': "🏆 Classement mensuel des points",
            'en': "🏆 Monthly Points Leaderboard",
        }
        _ml_desc = {
            'zh': lambda m: f"**{m}** 积分排行 Top 10 揭晓！",
            'ja': lambda m: f"**{m}** のポイントランキング Top 10 発表！",
            'fr': lambda m: f"Top 10 des points de **{m}** !",
            'en': lambda m: f"**{m}** Points Top 10 Results!",
        }
        _ml_no_data = {
            'zh': "上个月没有用户获得积分。新的一月开始了，快去签到和玩游戏吧！",
            'ja': "先月はポイントを獲得したユーザーがいませんでした。新しい月が始まりました、チェックインやゲームで頑張ろう！",
            'fr': "Aucun utilisateur n'a obtenu de points le mois dernier. Un nouveau mois commence, allez vous connecter et jouer !",
            'en': "No users earned points last month. A new month has started — go check in and play games!",
        }
        _ml_rank = {'zh': "排名", 'ja': "順位", 'fr': "Rang", 'en': "Rank"}
        _ml_user = {'zh': "用户", 'ja': "ユーザー", 'fr': "Utilisateur", 'en': "User"}
        _ml_pts  = {'zh': "积分", 'ja': "ポイント", 'fr': "Points", 'en': "Points"}
        _ml_bonus_title = {'zh': "🎁 前三奖励", 'ja': "🎁 上位3名の報酬", 'fr': "🎁 Récompenses Top 3", 'en': "🎁 Top 3 Rewards"}
        _ml_bonus_line = {
            'zh': lambda medal, name, bonus: f'{medal} {name} — 奖励 **{bonus}** ⭐',
            'ja': lambda medal, name, bonus: f'{medal} {name} — 報酬 **{bonus}** ⭐',
            'fr': lambda medal, name, bonus: f'{medal} {name} — Récompense **{bonus}** ⭐',
            'en': lambda medal, name, bonus: f'{medal} {name} — Reward **{bonus}** ⭐',
        }
        _ml_footer = {
            'zh': "月度积分已重置为0（永久积分不受影响）| 新的一月继续加油！",
            'ja': "月間ポイントは0にリセットされました（永久ポイントは影響なし）| 新しい月も頑張ろう！",
            'fr': "Les points mensuels ont été réinitialisés à 0 (les points permanents ne sont pas affectés) | Bonne continuation !",
            'en': "Monthly points have been reset to 0 (permanent points unaffected) | Good luck in the new month!",
        }

        langs_to_send = ['zh', 'ja', 'fr', 'en']
        medals = {0: '🥇', 1: '🥈', 2: '🥉'}
        rewards = {0: 300, 1: 200, 2: 100}

        for lang in langs_to_send:
            last_month_str = last_month_labels[lang]
            embed = discord.Embed(
                title=_ml_title[lang],
                description=_ml_desc[lang](last_month_str),
                color=discord.Color.gold(),
                timestamp=now
            )

            if not rows:
                embed.add_field(name="📭", value=_ml_no_data[lang], inline=False)
            else:
                rank_lines = []
                user_lines = []
                pts_lines = []
                for i, (uid, uname, pts) in enumerate(rows):
                    rank_lines.append(medals.get(i, f'#{i+1}'))
                    try:
                        member = channel.guild.get_member(uid) if channel.guild else None
                        display = member.display_name if member else str(uname)
                    except:
                        display = str(uname)
                    user_lines.append(display)
                    pts_lines.append(f'**{pts}** ⭐')

                embed.add_field(name=_ml_rank[lang], value='\n'.join(rank_lines), inline=True)
                embed.add_field(name=_ml_user[lang], value='\n'.join(user_lines), inline=True)
                embed.add_field(name=_ml_pts[lang],  value='\n'.join(pts_lines),  inline=True)

                bonus_lines = []
                for i, (uid, uname, pts) in enumerate(rows[:3]):
                    bonus = rewards.get(i, 0)
                    try:
                        member = channel.guild.get_member(uid) if channel.guild else None
                        display = member.display_name if member else str(uname)
                    except:
                        display = str(uname)
                    bonus_lines.append(_ml_bonus_line[lang](medals[i], display, bonus))
                embed.add_field(name=_ml_bonus_title[lang], value='\n'.join(bonus_lines), inline=False)

            embed.set_footer(text=_ml_footer[lang])
            await channel.send(embed=embed)
            await asyncio.sleep(0.5)

        ShopCog._monthly_settled = month_key
        set_meta('monthly_settled', month_key)
        last_month = last_month_labels['zh']
        print(f"[月榜] 已发送 {last_month} 月度排行榜到频道 {self.MONTHLY_LEADERBOARD_CHANNEL_ID}")

        try:
            cursor.execute("UPDATE users SET monthly_points = 0")
            for i, (uid, uname, pts) in enumerate(rows[:3]):
                bonus = rewards.get(i, 0)
                if bonus > 0:
                    cursor.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (bonus, uid))
            conn.commit()
            print(f"[月榜] {last_month} 月度结算完成 — 前3奖励已发放到永久积分，月度积分已重置")
        except Exception as e:
            print(f"[月榜] ⚠️ 结算失败（embed已发送，不会重发）: {e}")

    @monthly_leaderboard.before_loop
    async def before_monthly_leaderboard(self):
        await self.bot.wait_until_ready()

    # ── 启动任务 ──
    def start_tasks(self):
        # 在启动任务前先从持久化存储读取月度结算状态
        # （Cog.on_ready 不会在 bot 已就绪后添加 Cog 时触发）
        ShopCog._monthly_settled = get_meta('monthly_settled', None)
        print(f"[Cog:Shop] 月度结算状态: {ShopCog._monthly_settled}")

        if not self.auto_bump.is_running():
            self.auto_bump.start()
            print("[Cog:Shop] DISBOARD 自动 bump 任务已启动")
        if not self.monthly_leaderboard.is_running():
            self.monthly_leaderboard.start()
            print("[Cog:Shop] 月度排行榜结算任务已启动")


async def setup(bot):
    cog = ShopCog(bot)
    await bot.add_cog(cog)
