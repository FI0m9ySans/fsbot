"""
cogs/redpacket.py — 红包系统 (S1 麦收季)
/redpacket create <金额> <个数> [留言] — 发红包
"""
import discord
from discord import app_commands
from discord.ext import commands, tasks
import asyncio
from datetime import datetime, timedelta

from utils.db import (
    conn, cursor, get_or_create_user, deduct_points, add_permanent_points,
    create_red_packet, claim_red_packet, get_red_packet,
    update_red_packet_message, expire_red_packets
)


class RedPacketView(discord.ui.View):
    """红包抢按钮 View"""
    def __init__(self, rp_id: int, timeout: float = 86400):
        super().__init__(timeout=timeout)
        self.rp_id = rp_id

    @discord.ui.button(label="🧧 抢红包", style=discord.ButtonStyle.danger, custom_id="redpacket_claim")
    async def claim_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        rp = get_red_packet(self.rp_id)
        if not rp:
            await interaction.response.send_message("红包数据异常，请联系管理员", ephemeral=True)
            return

        if rp['status'] == 'expired':
            await interaction.response.send_message("⏰ 红包已过期", ephemeral=True)
            return

        if rp['status'] == 'finished':
            await interaction.response.send_message("🧧 红包已被抢完！", ephemeral=True)
            return

        user_id = str(interaction.user.id)
        username = interaction.user.display_name

        success, amount, msg = claim_red_packet(self.rp_id, user_id, username)

        if not success:
            # 已经抢过
            await interaction.response.send_message(msg, ephemeral=True)
            return

        # 抢成功：加积分
        get_or_create_user(user_id, username)
        add_permanent_points(user_id, amount)

        # 更新红包消息
        rp = get_red_packet(self.rp_id)
        if rp:
            claimed = rp['claimed_by']
            embed = _build_redpacket_embed(rp)

            if rp['status'] == 'finished':
                # 红包抢完，禁用按钮
                self.claim_btn.disabled = True
                self.claim_btn.label = "🧧 已抢完"
                embed.set_footer(text=f"已被 {len(claimed)} 人抢完")

            await interaction.response.edit_message(embed=embed, view=self)
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)

    async def on_timeout(self):
        """View 超时（24h），标记按钮不可用"""
        self.claim_btn.disabled = True
        self.claim_btn.label = "🧧 已过期"


def _build_redpacket_embed(rp):
    """构建红包 Embed"""
    total = rp['total_amount']
    count = rp['count']
    remaining = rp['remaining_count']
    claimed = rp['claimed_by']
    claimed_total = sum(c['amount'] for c in claimed)
    message = rp['message']
    creator_name = rp['creator_name']

    if rp['status'] == 'finished':
        color = 0xDDDDDD
    elif rp['status'] == 'expired':
        color = 0x999999
    else:
        color = 0xFF4444  # 红包红

    embed = discord.Embed(
        title="🧧 红包" if rp['status'] == 'active' else ("🧧 红包（已抢完）" if rp['status'] == 'finished' else "🧧 红包（已过期）"),
        description=f"**{creator_name}** 发了一个红包\n{message}" if message else f"**{creator_name}** 发了一个红包",
        color=color
    )
    embed.add_field(name="金额", value=f"💰 {total} 积分", inline=True)
    embed.add_field(name="个数", value=f"📦 {count} 个", inline=True)
    embed.add_field(name="剩余", value=f"🎁 {remaining}/{count} (已抢 {claimed_total} 积分)", inline=True)

    if claimed:
        # 找出手气最佳（金额最高的）
        max_amount = max(c['amount'] for c in claimed) if claimed else 0
        claim_text = "\n".join(
            f"{'🥇' if i == 0 else '🥈' if i == 1 else '🥉' if i == 2 else '•'} **{c['username']}** — {c['amount']} 积分"
            + (" 🍀 手气最佳" if rp['status'] == 'finished' and c['amount'] == max_amount else "")
            for i, c in enumerate(claimed)
        )
        embed.add_field(name="已领取", value=claim_text, inline=False)

    if rp['status'] == 'active':
        embed.set_footer(text="点击下方按钮抢红包！24小时后过期")

    return embed


class RedPacketCog(commands.Cog, name="RedPacket"):
    """红包系统"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.expire_check.start()

    def cog_unload(self):
        self.expire_check.cancel()

    @tasks.loop(minutes=5)
    async def expire_check(self):
        """每5分钟检查过期红包并退款"""
        try:
            refunds = expire_red_packets()
            for rp_id, creator_id, remaining in refunds:
                # 退款到创建者永久积分
                add_permanent_points(creator_id, remaining)
                # 尝试更新 Discord 消息
                rp = get_red_packet(rp_id)
                if rp and rp['channel_id'] and rp['message_id']:
                    try:
                        channel = self.bot.get_channel(int(rp['channel_id']))
                        if channel:
                            msg = await channel.fetch_message(int(rp['message_id']))
                            embed = _build_redpacket_embed(rp)
                            await msg.edit(embed=embed, view=None)
                    except Exception:
                        pass
                print(f"[RedPacket] 红包 #{rp_id} 已过期，退款 {remaining} 积分给 {creator_id}")
        except Exception as e:
            print(f"[RedPacket] 过期检查异常: {e}")

    @expire_check.before_loop
    async def before_expire_check(self):
        await self.bot.wait_until_ready()

    # ═══════════════════════════════════════════
    # /redpacket create
    # ═══════════════════════════════════════════
    @app_commands.command(name="redpacket", description="发红包 / Create a red packet / 赤い封筒を作成 / Créer une enveloppe rouge")
    @app_commands.describe(
        total_amount="红包总金额（积分）/ Total amount / 合計金額 / Montant total",
        count="红包个数 / Number of packets / 個数 / Nombre",
        message="红包留言（可选）/ Message / メッセージ / Message"
    )
    async def redpacket_create(
        self,
        interaction: discord.Interaction,
        total_amount: int,
        count: int,
        message: str = ""
    ):
        user_id = str(interaction.user.id)
        username = interaction.user.display_name

        # 校验
        if total_amount < count:
            await interaction.response.send_message("红包总金额不能小于红包个数！（每个红包至少 1 积分）", ephemeral=True)
            return
        if count < 1:
            await interaction.response.send_message("红包个数至少为 1", ephemeral=True)
            return
        if count > 100:
            await interaction.response.send_message("红包个数最多 100 个", ephemeral=True)
            return
        if total_amount > 100000:
            await interaction.response.send_message("红包总金额不能超过 100,000 积分", ephemeral=True)
            return

        # 检查余额
        get_or_create_user(user_id, username)
        cursor.execute("SELECT points FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        balance = row[0] if row else 0

        if balance < total_amount:
            await interaction.response.send_message(
                f"积分不足！你的余额：{balance} 积分，需要：{total_amount} 积分",
                ephemeral=True
            )
            return

        # 扣积分
        ok, new_balance = deduct_points(user_id, total_amount)
        if not ok:
            await interaction.response.send_message("扣款失败，请稍后再试", ephemeral=True)
            return

        # 创建红包
        rp_id = create_red_packet(user_id, username, total_amount, count, message)
        rp = get_red_packet(rp_id)

        # 发送红包消息（先 deferred 再 followup，确保消息在频道中）
        embed = _build_redpacket_embed(rp)
        view = RedPacketView(rp_id)

        await interaction.response.send_message(embed=embed, view=view)

        # 获取发送的消息 ID 存入数据库
        msg = await interaction.original_response()
        update_red_packet_message(rp_id, interaction.channel_id, msg.id)

        print(f"[RedPacket] {username} 发了一个 {total_amount} 积分的红包（{count}个）, ID #{rp_id}")


async def setup(bot):
    await bot.add_cog(RedPacketCog(bot))
