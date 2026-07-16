import discord
from discord import app_commands
from discord.ext import commands
import random
import asyncio
from datetime import datetime, timedelta
import copy
import collections
import string
import sys

from utils.db import add_points, get_or_create_user, get_talents
from utils import VIRTUAL_OPPONENTS


class BigGamesCog(commands.Cog, name="BigGames"):
    """大型游戏：恶魔轮盘赌、UNO、狼人杀、路墙棋"""

    def __init__(self, bot):
        self.bot = bot



class RussianGame:
    def __init__(self, p1, p2, is_ai=False, ai_name=None, ai_avatar=None, ai_level=1):
        self.p1 = p1  # discord.Member (发起者)
        self.p2 = p2  # discord.Member 或 None (AI)
        self.is_ai = is_ai
        self.ai_name = ai_name or "DevilBot"
        self.ai_avatar = ai_avatar or "😈"
        self.ai_level = ai_level
        self.p1_hp = 3
        self.p2_hp = 3
        self.current_turn = p1  # 当前行动者
        self.magazine = []
        self.bullet_idx = 0
        self.live_count = 0
        self.blank_count = 0
        self.game_over = False
        self.winner = None
        self.loser = None
        self.round_num = 1
        self.last_result = None
        self.channel_id = None
        self.message = None  # 主消息对象，用于编辑
        self._load_magazine()

    def _load_magazine(self):
        total = random.randint(2, 5)
        self.live_count = random.randint(1, total - 1)
        self.blank_count = total - self.live_count
        self.magazine = ['live'] * self.live_count + ['blank'] * self.blank_count
        random.shuffle(self.magazine)
        self.bullet_idx = 0

    def get_current_player(self):
        return self.current_turn

    def get_opponent(self):
        return self.p2 if self.current_turn == self.p1 else self.p1

    def get_current_name(self):
        if self.current_turn == self.p1:
            return self.p1.display_name
        return f"{self.ai_avatar} {self.ai_name}" if self.is_ai else self.p2.display_name

    def get_opponent_name(self):
        if self.current_turn == self.p1:
            return f"{self.ai_avatar} {self.ai_name}" if self.is_ai else self.p2.display_name
        return self.p1.display_name

    def shoot(self, target):
        """target: 'opponent' or 'self'"""
        if self.bullet_idx >= len(self.magazine):
            self._load_magazine()
            self.round_num += 1

        bullet = self.magazine[self.bullet_idx]
        self.bullet_idx += 1
        extra_turn = False

        if bullet == 'live':
            if target == 'self':
                if self.current_turn == self.p1:
                    self.p1_hp -= 1
                else:
                    self.p2_hp -= 1
            else:  # opponent
                if self.current_turn == self.p1:
                    self.p2_hp -= 1
                else:
                    self.p1_hp -= 1
            extra_turn = False
        else:  # blank
            if target == 'self':
                extra_turn = True  # 对自己开枪空包弹，获得额外行动
            else:
                extra_turn = False

        self.last_result = {'bullet': bullet, 'target': target, 'extra': extra_turn}

        # 检查游戏结束
        if self.p1_hp <= 0:
            self.game_over = True
            self.winner = self.p2 if not self.is_ai else None
            self.loser = self.p1
        elif self.p2_hp <= 0:
            self.game_over = True
            self.winner = self.p1
            self.loser = self.p2 if not self.is_ai else None
        else:
            if not extra_turn:
                self.current_turn = self.p2 if self.current_turn == self.p1 else self.p1

        # 更新剩余子弹计数
        if bullet == 'live':
            self.live_count -= 1
        else:
            self.blank_count -= 1

        return bullet, extra_turn

    def ai_decide(self):
        """AI 决策逻辑"""
        # AI 知道弹匣内容（因为显示在界面上）
        remaining = self.magazine[self.bullet_idx:]
        if not remaining:
            return 'self'  # 重新装填前默认对自己

        live_in_mag = remaining.count('live')
        blank_in_mag = len(remaining) - live_in_mag

        # 如果有实弹，大概率对玩家开枪
        if live_in_mag > 0:
            if blank_in_mag == 0:
                return 'opponent'  # 全是实弹，必对玩家开枪
            if random.random() < 0.7 + (self.ai_level * 0.02):
                return 'opponent'
            else:
                return 'self'
        else:
            # 全是空包弹，对自己开枪再行动
            return 'self'


def get_russian_text(lang, key, **kwargs):
    """多语言文本获取"""
    texts = {
        'title': {
            'zh': '🔫 恶魔轮盘赌',
            'ja': '🔫 悪魔のルーレット',
            'fr': '🔫 Roulette du Diable',
            'en': "🔫 Devil's Roulette",
        },
        'desc': {
            'zh': '实弹致命，空包弹换回合！对自己开枪如果是空包弹，可再行动一次！',
            'ja': '実弾は致命的、空包はターン交代！自分に撃って空包ならもう一回行動！',
            'fr': 'Les vraies balles tuent, les blanches changent de tour ! Tire sur toi avec une blanche pour rejouer !',
            'en': 'Live rounds are deadly, blanks switch turns! Shoot yourself with a blank for an extra turn!',
        },
        'waiting_accept': {
            'zh': '{p2}，{p1} 向你发起了恶魔轮盘赌！点击按钮接受挑战！',
            'ja': '{p2}、{p1} が悪魔のルーレットに挑戦状を送った！ボタンをクリックして受けて立て！',
            'fr': '{p2}, {p1} te défie à la Roulette du Diable ! Clique pour accepter !',
            'en': "{p2}, {p1} challenges you to Devil's Roulette! Click to accept!",
        },
        'turn': {
            'zh': '第 {round} 轮 | 轮到 **{name}**',
            'ja': '第 {round} ラウンド | **{name}** の番',
            'fr': "Tour {round} | C'est à **{name}**",
            'en': "Round {round} | **{name}**'s turn",
        },
        'hp': {
            'zh': '❤️ HP',
            'ja': '❤️ HP',
            'fr': '❤️ PV',
            'en': '❤️ HP',
        },
        'magazine': {
            'zh': '🔫 弹匣: {live} 实弹 | {blank} 空包弹',
            'ja': '🔫 弾倉: {live} 実弾 | {blank} 空包',
            'fr': '🔫 Chargeur : {live} réelles | {blank} à blanc',
            'en': '🔫 Magazine: {live} live | {blank} blank',
        },
        'shoot_opponent': {
            'zh': '💥 对对手开枪',
            'ja': '💥 相手に撃つ',
            'fr': "💥 Tirer sur l'adversaire",
            'en': '💥 Shoot opponent',
        },
        'shoot_self': {
            'zh': '🎯 对自己开枪 (空包弹=再行动)',
            'ja': '🎯 自分に撃つ (空包=再行动)',
            'fr': '🎯 Tirer sur soi (blanche = rejouer)',
            'en': '🎯 Shoot self (blank = extra turn)',
        },
        'result_live_opponent': {
            'zh': '💥 **实弹！** {shooter} 对 {target} 开枪，造成了伤害！',
            'ja': '💥 **実弾！** {shooter} が {target} に撃ってダメージ！',
            'fr': '💥 **Vraie balle !** {shooter} tire sur {target} et inflige des dégâts !',
            'en': '💥 **LIVE ROUND!** {shooter} shoots {target} and deals damage!',
        },
        'result_live_self': {
            'zh': '💥 **实弹！** {shooter} 对自己开枪，受伤了！',
            'ja': '💥 **実弾！** {shooter} が自分に撃って怪我をした！',
            'fr': '💥 **Vraie balle !** {shooter} se tire dessus et se blesse !',
            'en': '💥 **LIVE ROUND!** {shooter} shoots themselves and gets hurt!',
        },
        'result_blank_opponent': {
            'zh': '💨 **空包弹！** {shooter} 对 {target} 开枪，但什么也没发生...',
            'ja': '💨 **空包！** {shooter} が {target} に撃ったが何も起こらなかった...',
            'fr': '💨 **À blanc !** {shooter} tire sur {target} mais rien ne se passe...',
            'en': '💨 **BLANK!** {shooter} shoots {target} but nothing happens...',
        },
        'result_blank_self': {
            'zh': '💨 **空包弹！** {shooter} 对自己开枪，安全！获得额外行动！',
            'ja': '💨 **空包！** {shooter} が自分に撃ったが安全！追加ターン！',
            'fr': '💨 **À blanc !** {shooter} se tire dessus en toute sécurité ! Tour bonus !',
            'en': '💨 **BLANK!** {shooter} shoots themselves safely! Extra turn!',
        },
        'game_over': {
            'zh': '☠️ 游戏结束！**{winner}** 胜利！**{loser}** 倒下...',
            'ja': '☠️ ゲームオーバー！**{winner}** の勝利！**{loser}** が倒れた...',
            'fr': '☠️ Fin du jeu ! **{winner}** gagne ! **{loser}** est abattu...',
            'en': '☠️ GAME OVER! **{winner}** wins! **{loser}** falls...',
        },
        'reward': {
            'zh': '🎉 你获得了 **{reward}** ⭐！当前积分: **{points}** ⭐',
            'ja': '🎉 **{reward}** ⭐を獲得！現在のポイント: **{points}** ⭐',
            'fr': '🎉 Tu as gagné **{reward}** ⭐ ! Points : **{points}** ⭐',
            'en': '🎉 You earned **{reward}** ⭐! Current points: **{points}** ⭐',
        },
        'accept': {
            'zh': '✅ 接受挑战',
            'ja': '✅ 挑戦を受ける',
            'fr': '✅ Accepter',
            'en': '✅ Accept',
        },
        'reject': {
            'zh': '❌ 拒绝',
            'ja': '❌ 拒否',
            'fr': '❌ Refuser',
            'en': '❌ Decline',
        },
        'no_room': {
            'zh': '❌ 当前频道没有正在进行的恶魔轮盘赌！',
            'ja': '❌ このチャンネルに進行中の悪魔のルーレットはない！',
            'fr': '❌ Aucune Roulette du Diable en cours dans ce salon !',
            'en': "❌ No Devil's Roulette in progress in this channel!",
        },
        'not_your_turn': {
            'zh': '❌ 现在不是轮到你行动！',
            'ja': '❌ 今はあなたの番ではない！',
            'fr': "❌ Ce n'est pas ton tour !",
            'en': "❌ It's not your turn!",
        },
        'ai_turn': {
            'zh': '🤖 {name} 正在思考...',
            'ja': '🤖 {name} が考え中...',
            'fr': '🤖 {name} réfléchit...',
            'en': '🤖 {name} is thinking...',
        },
        'already_in_game': {
            'zh': '❌ 你已经在一个进行中的游戏中了！',
            'ja': '❌ 既に進行中のゲームに参加している！',
            'fr': '❌ Tu es déjà dans une partie en cours !',
            'en': '❌ You are already in an ongoing game!',
        },
        'target_in_game': {
            'zh': '❌ 对方已经在一个进行中的游戏中了！',
            'ja': '❌ 相手は既に進行中のゲームに参加している！',
            'fr': "❌ L'adversaire est déjà dans une partie en cours !",
            'en': '❌ The opponent is already in an ongoing game!',
        },
        'channel_in_game': {
            'zh': '❌ 当前频道已有进行中的游戏！',
            'ja': '❌ このチャンネルには既に進行中のゲームがある！',
            'fr': '❌ Une partie est déjà en cours dans ce salon !',
            'en': '❌ A game is already in progress in this channel!',
        },
        'no_online_members': {
            'zh': '❌ 没有合适的在线成员可以匹配！',
            'ja': '❌ マッチングできるオンラインメンバーがいない！',
            'fr': '❌ Aucun membre en ligne disponible pour le matchmaking !',
            'en': '❌ No suitable online members for matchmaking!',
        },
        'cant_self': {
            'zh': '❌ 不能和自己对战！',
            'ja': '❌ 自分と戦えない！',
            'fr': '❌ Tu ne peux pas te battre contre toi-même !',
            'en': "❌ You can't battle yourself!",
        },
        'cant_bot': {
            'zh': '❌ 不能和机器人对战！',
            'ja': '❌ Botと戦えない！',
            'fr': '❌ Tu ne peux pas te battre contre un bot !',
            'en': "❌ You can't battle a bot!",
        },
        'reloaded': {
            'zh': '🔁 弹匣已重新装填！',
            'ja': '🔁 弾倉を再装填した！',
            'fr': '🔁 Le chargeur a été rechargé !',
            'en': '🔁 Magazine reloaded!',
        },
    }
    text = texts.get(key, {}).get(lang, texts.get(key, {}).get('en', key))
    return text.format(**kwargs)


def build_russian_embed(game, lang, result_text=None, show_buttons=True):
    """构建恶魔轮盘赌的 Embed"""
    embed = discord.Embed(
        title=get_russian_text(lang, 'title'),
        description=get_russian_text(lang, 'desc'),
        color=discord.Color.dark_red()
    )

    # HP 显示
    p1_hp_bar = '❤️' * game.p1_hp + '🖤' * (3 - game.p1_hp)
    p2_hp_bar = '❤️' * game.p2_hp + '🖤' * (3 - game.p2_hp)
    p2_name = f"{game.ai_avatar} {game.ai_name}" if game.is_ai else game.p2.display_name

    embed.add_field(name=f"{game.p1.display_name}", value=f"{p1_hp_bar} ({game.p1_hp}/3)", inline=True)
    embed.add_field(name=f"{p2_name}", value=f"{p2_hp_bar} ({game.p2_hp}/3)", inline=True)

    # 弹匣信息
    mag_text = get_russian_text(lang, 'magazine', live=game.live_count, blank=game.blank_count)
    embed.add_field(name="", value=mag_text, inline=False)

    # 回合信息
    if not game.game_over:
        turn_text = get_russian_text(lang, 'turn', round=game.round_num, name=game.get_current_name())
        embed.add_field(name="", value=turn_text, inline=False)

    # 上回合结果
    if result_text:
        embed.add_field(name="", value=result_text, inline=False)

    if game.game_over:
        embed.color = discord.Color.gold()

    return embed


russian_rooms = {}  # {channel_id: RussianGame}

class RussianAcceptView(discord.ui.View):
    """接受挑战的 View"""
    def __init__(self, game, channel_id, lang):
        super().__init__(timeout=60)
        self.game = game
        self.channel_id = channel_id
        self.lang = lang
        self.accepted = False

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.green, emoji="✅")
    async def accept_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.game.p2.id:
            await interaction.response.send_message("❌ This challenge is not for you! | 这不是给你的挑战！", ephemeral=True)
            return
        self.accepted = True
        self.stop()
        await interaction.response.defer()
        # 开始游戏
        await start_russian_game(self.game, self.channel_id, interaction.channel, self.lang)

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.red, emoji="❌")
    async def decline_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.game.p2.id:
            await interaction.response.send_message("❌ This challenge is not for you! | 这不是给你的挑战！", ephemeral=True)
            return
        self.accepted = False
        self.stop()
        await interaction.response.send_message(
            get_russian_text(self.lang, 'reject'), ephemeral=True
        )
        if self.channel_id in russian_rooms:
            del russian_rooms[self.channel_id]


class RussianGameView(discord.ui.View):
    """游戏进行中的 View"""
    def __init__(self, game, channel_id, lang):
        super().__init__(timeout=300)
        self.game = game
        self.channel_id = channel_id
        self.lang = lang

    async def _handle_shoot(self, interaction: discord.Interaction, target: str):
        """处理开枪逻辑"""
        game = self.game
        lang = self.lang

        # 检查是否是当前回合玩家
        current = game.get_current_player()
        if current is None or interaction.user.id != current.id:
            await interaction.response.send_message(get_russian_text(lang, 'not_your_turn'), ephemeral=True)
            return

        # 执行射击
        if game.bullet_idx >= len(game.magazine):
            game._load_magazine()
            game.round_num += 1

        bullet, extra = game.shoot(target)

        shooter_name = game.get_current_name()
        target_name = game.get_opponent_name()

        if bullet == 'live':
            if target == 'opponent':
                result_text = get_russian_text(lang, 'result_live_opponent', shooter=shooter_name, target=target_name)
            else:
                result_text = get_russian_text(lang, 'result_live_self', shooter=shooter_name)
        else:
            if target == 'opponent':
                result_text = get_russian_text(lang, 'result_blank_opponent', shooter=shooter_name, target=target_name)
            else:
                result_text = get_russian_text(lang, 'result_blank_self', shooter=shooter_name)

        # 检查游戏结束
        if game.game_over:
            winner_name = game.get_current_name() if game.winner == game.p1 else game.get_opponent_name()
            loser_name = game.get_opponent_name() if game.winner == game.p1 else game.get_current_name()
            game_over_text = get_russian_text(lang, 'game_over', winner=winner_name, loser=loser_name)

            # 积分结算（仅真人玩家获得）
            if game.winner == game.p1:
                luck = get_talents(game.p1.id)[1]
                reward = int(60 * (1 + luck * 0.05))
                new_points = add_points(game.p1.id, reward)
                reward_text = get_russian_text(lang, 'reward', reward=reward, points=new_points)
            else:
                reward_text = ""

            embed = build_russian_embed(game, lang, result_text=result_text + "\n" + game_over_text + "\n" + reward_text, show_buttons=False)
            # 清除按钮
            await interaction.response.edit_message(embed=embed, view=None)
            if self.channel_id in russian_rooms:
                del russian_rooms[self.channel_id]
            return

        # 游戏继续
        embed = build_russian_embed(game, lang, result_text=result_text)
        # 如果是 AI 回合，先移除按钮（防止人类在 sleep 窗口误触），AI 行动完再加回来
        if game.is_ai and game.get_current_player() != game.p1:
            await interaction.response.edit_message(embed=embed, view=None)
            await asyncio.sleep(1.5)
            await self._ai_act(interaction)
        else:
            await interaction.response.edit_message(embed=embed, view=self)

    async def _ai_act(self, interaction: discord.Interaction):
        """AI 自动行动"""
        game = self.game
        lang = self.lang

        # 如果弹匣空了，重新装填
        if game.bullet_idx >= len(game.magazine):
            game._load_magazine()
            game.round_num += 1

        target = game.ai_decide()
        bullet, extra = game.shoot(target)

        ai_name = game.get_current_name()
        p1_name = game.p1.display_name

        if bullet == 'live':
            if target == 'opponent':
                result_text = get_russian_text(lang, 'result_live_opponent', shooter=ai_name, target=p1_name)
            else:
                result_text = get_russian_text(lang, 'result_live_self', shooter=ai_name)
        else:
            if target == 'opponent':
                result_text = get_russian_text(lang, 'result_blank_opponent', shooter=ai_name, target=p1_name)
            else:
                result_text = get_russian_text(lang, 'result_blank_self', shooter=ai_name)

        if game.game_over:
            winner_name = game.get_current_name() if game.winner else game.p1.display_name
            loser_name = game.p1.display_name if game.winner else ai_name
            game_over_text = get_russian_text(lang, 'game_over', winner=winner_name, loser=loser_name)

            if game.winner == game.p1:
                luck = get_talents(game.p1.id)[1]
                reward = int(60 * (1 + luck * 0.05))
                new_points = add_points(game.p1.id, reward)
                reward_text = get_russian_text(lang, 'reward', reward=reward, points=new_points)
            else:
                reward_text = ""

            embed = build_russian_embed(game, lang, result_text=result_text + "\n" + game_over_text + "\n" + reward_text, show_buttons=False)
            await interaction.edit_original_response(embed=embed, view=None)
            if self.channel_id in russian_rooms:
                del russian_rooms[self.channel_id]
            return

        embed = build_russian_embed(game, lang, result_text=result_text)
        await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label="Shoot Opponent", style=discord.ButtonStyle.danger, emoji="💥")
    async def shoot_opponent_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_shoot(interaction, 'opponent')

    @discord.ui.button(label="Shoot Self", style=discord.ButtonStyle.primary, emoji="🎯")
    async def shoot_self_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_shoot(interaction, 'self')


async def start_russian_game(game, channel_id, channel, lang):
    """开始游戏"""
    game.channel_id = channel_id
    russian_rooms[channel_id] = game
    embed = build_russian_embed(game, lang)
    view = RussianGameView(game, channel_id, lang)
    game.message = await channel.send(embed=embed, view=view)

    # 如果 AI 先手
    if game.is_ai and game.current_turn != game.p1:
        await asyncio.sleep(1.5)
        await view._ai_act(None)


def get_opponent_in_game(user_id):
    """检查用户是否在游戏中，返回所在频道ID"""
    for cid, game in russian_rooms.items():
        if game.p1.id == user_id or (game.p2 and game.p2.id == user_id):
            return cid
    return None


@app_commands.command(name="russian", description="恶魔轮盘赌 / Devil's Roulette / 悪魔のルーレット / Roulette du Diable")
@app_commands.describe(mode="对战模式 / Battle mode", opponent="对手 (仅 member 模式需要)")
@app_commands.choices(mode=[
    app_commands.Choice(name="🎲 随机匹配成员 / Random member", value="random"),
    app_commands.Choice(name="🤖 对战虚拟对手 / VS AI", value="ai"),
    app_commands.Choice(name="👤 指定成员对战 / VS Member", value="member"),
])
async def russian_slash(interaction: discord.Interaction, mode: app_commands.Choice[str], opponent: discord.Member = None):
    user_id = interaction.user.id
    locale = str(interaction.locale)
    lang = 'zh' if locale.startswith('zh') else ('ja' if locale.startswith('ja') else ('fr' if locale.startswith('fr') else 'en'))
    channel_id = interaction.channel_id

    # 检查当前频道是否已有游戏
    if channel_id in russian_rooms:
        await interaction.response.send_message(get_russian_text(lang, 'channel_in_game'), ephemeral=True)
        return

    # 检查自己是否已在游戏中
    if get_opponent_in_game(user_id):
        await interaction.response.send_message(get_russian_text(lang, 'already_in_game'), ephemeral=True)
        return

    if mode.value == 'random':
        # 随机匹配在线成员
        members = [m for m in interaction.guild.members if not m.bot and m.status != discord.Status.offline and m.id != user_id]
        if not members:
            await interaction.response.send_message(get_russian_text(lang, 'no_online_members'), ephemeral=True)
            return
        target = random.choice(members)
        # 检查目标是否在游戏中
        if get_opponent_in_game(target.id):
            await interaction.response.send_message(get_russian_text(lang, 'target_in_game'), ephemeral=True)
            return

        game = RussianGame(interaction.user, target, is_ai=False)
        await interaction.response.send_message(
            get_russian_text(lang, 'waiting_accept', p1=interaction.user.mention, p2=target.mention),
            view=RussianAcceptView(game, channel_id, lang)
        )

    elif mode.value == 'ai':
        # 对战虚拟对手
        opp = random.choice(VIRTUAL_OPPONENTS)
        game = RussianGame(
            interaction.user, None, is_ai=True,
            ai_name=opp['name'], ai_avatar=opp['avatar'],
            ai_level=random.randint(1, 10)
        )
        await interaction.response.send_message("🎮 游戏开始！", ephemeral=True)
        await start_russian_game(game, channel_id, interaction.channel, lang)

    elif mode.value == 'member':
        if not opponent:
            await interaction.response.send_message("❌ 请选择对手！| Please select an opponent! | 相手を選んでください！| Sélectionne un adversaire !", ephemeral=True)
            return
        if opponent.bot:
            await interaction.response.send_message(get_russian_text(lang, 'cant_bot'), ephemeral=True)
            return
        if opponent.id == user_id:
            await interaction.response.send_message(get_russian_text(lang, 'cant_self'), ephemeral=True)
            return
        if get_opponent_in_game(opponent.id):
            await interaction.response.send_message(get_russian_text(lang, 'target_in_game'), ephemeral=True)
            return

        game = RussianGame(interaction.user, opponent, is_ai=False)
        await interaction.response.send_message(
            get_russian_text(lang, 'waiting_accept', p1=interaction.user.mention, p2=opponent.mention),
            view=RussianAcceptView(game, channel_id, lang)
        )


@app_commands.command(name="russianstop", description="强制结束当前频道的恶魔轮盘赌 / Force stop roulette")
async def russian_stop_slash(interaction: discord.Interaction):
    channel_id = interaction.channel_id
    if channel_id in russian_rooms:
        del russian_rooms[channel_id]
        await interaction.response.send_message("✅ 游戏已强制结束。/ Game force-stopped.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ 当前频道没有进行中的游戏。/ No ongoing game in this channel.", ephemeral=True)

UNO_COLORS = ['🔴', '🟢', '🔵', '🟡']
UNO_NUMBERS = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '+2', '⊘', '↺']
UNO_SPECIAL = ['⬛+4', '⬛变色']

uno_rooms = {}  # {channel_id: UNOGame}

class UNOGame:
    def __init__(self, players):
        self.players = players  # [discord.Member, ...]
        self.hands = {p.id: [] for p in players}
        self.deck = []
        self.discard = []
        self.current_idx = 0
        self.direction = 1
        self.game_over = False
        self.winner = None
        self.current_color = None  # 当前生效的颜色(变色牌后由玩家选择)
        self._build_deck()
        self._deal()

    def _build_deck(self):
        for color in UNO_COLORS:
            for num in UNO_NUMBERS:
                self.deck.append(f"{color}{num}")
                if num != '0':
                    self.deck.append(f"{color}{num}")
        for special in UNO_SPECIAL:
            for _ in range(4):
                self.deck.append(special)
        random.shuffle(self.deck)

    def _deal(self):
        for p in self.players:
            for _ in range(7):
                self.hands[p.id].append(self.deck.pop())
        # 确保第一张弃牌堆牌不是特殊牌
        first = self.deck.pop()
        while '⬛' in first or '+2' in first or '⊘' in first or '↺' in first:
            self.deck.insert(0, first)
            first = self.deck.pop()
        self.discard.append(first)
        self.current_color = first[:2]  # 记录初始颜色

    def current_player(self):
        return self.players[self.current_idx]

    def draw_card(self, player_id, count=1):
        for _ in range(count):
            if not self.deck:
                # 重新洗牌
                top = self.discard.pop()
                self.deck = self.discard[:]
                self.discard = [top]
                random.shuffle(self.deck)
            if self.deck:
                self.hands[player_id].append(self.deck.pop())

    def get_current_color(self):
        """获取当前生效颜色"""
        top = self.discard[-1]
        if '⬛' in top:
            return self.current_color  # 变色牌后使用玩家选的颜色
        return top[:2]

    def can_play(self, card, top):
        """判断牌是否能出"""
        if '⬛' in card:
            return True  # 万能牌随时可出
        cur_color = self.get_current_color()
        # 颜色匹配
        if card[:2] == cur_color:
            return True
        # 数字/符号匹配
        if len(card) > 2 and len(top) > 2 and card[2:] == top[2:]:
            return True
        return False

    def play_card(self, player_id, card_idx, chosen_color=None):
        """出牌。chosen_color 用于变色牌/+4牌。"""
        hand = self.hands[player_id]
        if card_idx < 0 or card_idx >= len(hand):
            return False, 'invalid_idx'
        card = hand[card_idx]
        top = self.discard[-1]
        if not self.can_play(card, top):
            return False, 'cannot_play'

        hand.pop(card_idx)
        self.discard.append(card)

        # 处理变色牌
        if '⬛变色' in card:
            if chosen_color:
                self.current_color = chosen_color
            else:
                self.current_color = UNO_COLORS[0]  # 默认红
        elif '⬛+4' in card:
            if chosen_color:
                self.current_color = chosen_color
            else:
                self.current_color = UNO_COLORS[0]
        else:
            self.current_color = card[:2]

        if not hand:
            self.game_over = True
            self.winner = player_id
            return True, 'win'

        # 处理特殊牌效果
        if '+2' in card:
            self._next_player()
            self.draw_card(self.current_player().id, 2)
        elif '+4' in card:
            self._next_player()
            self.draw_card(self.current_player().id, 4)
        elif '⊘' in card:
            self._next_player()  # 跳过下一家
        elif '↺' in card:
            self.direction *= -1

        self._next_player()
        return True, 'ok'

    def _next_player(self):
        self.current_idx = (self.current_idx + self.direction) % len(self.players)


def _uno_text(key, lang='en', **kw):
    """UNO 多语言文本"""
    t = {
        'turn': {
            'zh': '**{name}** 的回合 | 手牌: {count} 张',
            'ja': '**{name}** の番 | 手札: {count} 枚',
            'fr': 'Tour de **{name}** | Main : {count} cartes',
            'en': "**{name}**'s turn | Hand: {count} cards",
        },
        'not_your_turn': {
            'zh': '❌ 还没轮到你！', 'ja': '❌ あなたの番ではありません！',
            'fr': "❌ Ce n'est pas votre tour !", 'en': '❌ Not your turn!',
        },
        'cannot_play': {
            'zh': '❌ 这张牌不能出！', 'ja': '❌ このカードは出せません！',
            'fr': '❌ Cette carte ne peut pas être jouée !', 'en': '❌ Cannot play this card!',
        },
        'drew_card': {
            'zh': '🃏 你抽了一张牌: {card}', 'ja': '🃏 カードを引いた: {card}',
            'fr': '🃏 Vous piochez : {card}', 'en': '🃏 You drew: {card}',
        },
        'drew_cards': {
            'zh': '🃏 {name} 被罚抽 {count} 张牌！', 'ja': '🃏 {name} が{count}枚引いた！',
            'fr': '🃏 {name} pioche {count} cartes !', 'en': '🃏 {name} drew {count} cards!',
        },
        'skip': {
            'zh': '⊘ {name} 被跳过！', 'ja': '⊘ {name} はスキップ！',
            'fr': '⊘ {name} est sauté !', 'en': '⊘ {name} is skipped!',
        },
        'reverse': {
            'zh': '↺ 方向反转！', 'ja': '↺ 方向反転！',
            'fr': '↺ Sens inversé !', 'en': '↺ Direction reversed!',
        },
        'color_changed': {
            'zh': '🎨 颜色变为 {color}', 'ja': '🎨 色が{color}に変更',
            'fr': '🎨 Couleur changée en {color}', 'en': '🎨 Color changed to {color}',
        },
        'win': {
            'zh': '🎉 **{name}** 出完所有牌！UNO胜利！+**{reward}** ⭐ | 当前: **{points}** ⭐',
            'ja': '🎉 **{name}** が全てのカードを出した！UNO勝利！+**{reward}** ⭐ | 現在: **{points}** ⭐',
            'fr': '🎉 **{name}** a joué toutes ses cartes ! Victoire UNO ! +**{reward}** ⭐ | Actuel : **{points}** ⭐',
            'en': '🎉 **{name}** played all cards! UNO victory! +**{reward}** ⭐ | Current: **{points}** ⭐',
        },
        'lose': {
            'zh': '😢 **{name}** 获胜了！你输了！',
            'ja': '😢 **{name}** が勝った！あなたの負け！',
            'fr': '😢 **{name}** a gagné ! Tu as perdu !',
            'en': '😢 **{name}** wins! You lose!',
        },
        'btn_draw': {
            'zh': '🃏 抽牌', 'ja': '🃏 引く', 'fr': '🃏 Piocher', 'en': '🃏 Draw',
        },
        'sel_color': {
            'zh': '选择颜色', 'ja': '色を選択', 'fr': 'Choisir couleur', 'en': 'Select Color',
        },
        'btn_confirm': {
            'zh': '✅ 确认出牌', 'ja': '✅ 出す', 'fr': '✅ Jouer', 'en': '✅ Play Card',
        },
        'btn_cancel': {
            'zh': '取消', 'ja': 'キャンセル', 'fr': 'Annuler', 'en': 'Cancel',
        },
        'top_card': {
            'zh': '顶牌', 'ja': '場札', 'fr': 'Carte du dessus', 'en': 'Top Card',
        },
        'direction': {
            'zh': '方向', 'ja': '方向', 'fr': 'Sens', 'en': 'Direction',
        },
        'dir_cw': {'zh': '顺时针', 'ja': '時計回り', 'fr': 'Horaire', 'en': 'Clockwise'},
        'dir_ccw': {'zh': '逆时针', 'ja': '反時計', 'fr': 'Anti-horaire', 'en': 'Counter-CW'},
        'your_hand': {
            'zh': '你的手牌 (点击出牌)', 'ja': 'あなたの手札 (クリックして出す)',
            'fr': 'Votre main (cliquez pour jouer)', 'en': 'Your hand (click to play)',
        },
        'choose_color_first': {
            'zh': '⚠️ 请先选择颜色！', 'ja': '⚠️ 先に色を選んでください！',
            'fr': "⚠️ Choisissez une couleur d'abord !", 'en': '⚠️ Choose a color first!',
        },
        'no_playable': {
            'zh': '⊘ 你没有可出的牌，请抽牌！', 'ja': '⊘ 出せるカードがない、引いてください！',
            'fr': '⊘ Aucune carte jouable, piochez !', 'en': '⊘ No playable cards, draw!',
        },
    }
    d = t.get(key)
    if d is None:
        return key
    if isinstance(d, dict):
        text = d.get(lang, d.get('en', key))
    else:
        text = d
    if isinstance(text, str):
        return text.format(**kw)
    return text


class UNOView(discord.ui.View):
    def __init__(self, game, channel_id, lang):
        super().__init__(timeout=300)
        self.game = game
        self.channel_id = channel_id
        self.lang = lang
        self.color_select_mode = False
        self._pending_card_idx = None
        self._chosen_color = None
        self._build_buttons()

    def _build_buttons(self):
        self.clear_items()
        if self.color_select_mode:
            self._build_color_ui()
        else:
            self._build_hand_ui()

    def _build_hand_ui(self):
        """构建手牌按钮界面"""
        current = self.game.current_player()
        pid = current.id
        hand = self.game.hands[pid]
        top = self.game.discard[-1]

        row = 0
        col_in_row = 0
        for idx, card in enumerate(hand[:20]):
            can_play = self.game.can_play(card, top)
            label = card if len(card) <= 10 else card[:10]
            if can_play:
                btn = discord.ui.Button(
                    label=label, style=discord.ButtonStyle.primary, row=row,
                    custom_id=f"uno_card_{idx}"
                )
            else:
                btn = discord.ui.Button(
                    label=label, style=discord.ButtonStyle.secondary, row=row,
                    custom_id=f"uno_card_{idx}"
                )
            btn.callback = self._make_play_callback(idx)
            self.add_item(btn)
            col_in_row += 1
            if col_in_row >= 5:
                col_in_row = 0
                row += 1

        draw_row = min(row + 1, 4)
        btn_draw = discord.ui.Button(
            label=_uno_text('btn_draw', self.lang), style=discord.ButtonStyle.success,
            row=draw_row, custom_id="uno_draw"
        )
        btn_draw.callback = self._draw_callback
        self.add_item(btn_draw)

    def _build_color_ui(self):
        """构建颜色选择界面"""
        color_styles = {}
        for color in UNO_COLORS:
            if '红' in color or '\U0001f534' in color:
                color_styles[color] = discord.ButtonStyle.danger
            elif '绿' in color or '\U0001f7e2' in color:
                color_styles[color] = discord.ButtonStyle.success
            elif '蓝' in color or '\U0001f535' in color:
                color_styles[color] = discord.ButtonStyle.primary
            else:
                color_styles[color] = discord.ButtonStyle.warning

        for ci, color in enumerate(UNO_COLORS):
            btn = discord.ui.Button(
                label=color, style=color_styles[color], row=0,
                custom_id=f"uno_color_{ci}"
            )
            btn.callback = self._make_color_callback(color)
            self.add_item(btn)

        btn_confirm = discord.ui.Button(
            label=_uno_text('btn_confirm', self.lang), style=discord.ButtonStyle.success, row=1
        )
        btn_confirm.callback = self._confirm_color_callback
        self.add_item(btn_confirm)

        btn_cancel = discord.ui.Button(
            label=_uno_text('btn_cancel', self.lang), style=discord.ButtonStyle.secondary, row=1
        )
        btn_cancel.callback = self._cancel_color_callback
        self.add_item(btn_cancel)

    def _make_play_callback(self, card_idx):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.game.current_player().id:
                await interaction.response.send_message(_uno_text('not_your_turn', self.lang), ephemeral=True)
                return

            hand = self.game.hands[interaction.user.id]
            if card_idx >= len(hand):
                await interaction.response.send_message(_uno_text('cannot_play', self.lang), ephemeral=True)
                return

            card = hand[card_idx]
            top = self.game.discard[-1]
            if not self.game.can_play(card, top):
                await interaction.response.send_message(_uno_text('cannot_play', self.lang), ephemeral=True)
                return

            if '\u2b1b' in card:
                self._pending_card_idx = card_idx
                self._chosen_color = None
                self.color_select_mode = True
                self._build_buttons()
                await interaction.response.edit_message(view=self)
                return

            success, result = self.game.play_card(interaction.user.id, card_idx)
            if not success:
                await interaction.response.send_message(_uno_text('cannot_play', self.lang), ephemeral=True)
                return

            if self.game.game_over:
                await self._handle_win(interaction)
                return

            await self._update_board(interaction, extra_msg=self._get_action_msg(card, interaction.user))
        return callback

    def _get_action_msg(self, card, player):
        """生成特殊牌效果的提示消息"""
        if '+2' in card:
            return _uno_text('drew_cards', self.lang, name=self.game.current_player().display_name, count=2)
        elif '+4' in card:
            return _uno_text('drew_cards', self.lang, name=self.game.current_player().display_name, count=4)
        elif '\u2298' in card:
            return _uno_text('skip', self.lang, name=self.game.current_player().display_name)
        elif '\u21ba' in card:
            return _uno_text('reverse', self.lang)
        elif '\u2b1b' in card:
            return _uno_text('color_changed', self.lang, color=self.game.current_color)
        return None

    def _make_color_callback(self, color):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.game.current_player().id:
                await interaction.response.send_message(_uno_text('not_your_turn', self.lang), ephemeral=True)
                return
            self._chosen_color = color
            await interaction.response.defer()
        return callback

    async def _confirm_color_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.game.current_player().id:
            await interaction.response.send_message(_uno_text('not_your_turn', self.lang), ephemeral=True)
            return

        if self._chosen_color is None:
            await interaction.response.send_message(_uno_text('choose_color_first', self.lang), ephemeral=True)
            return

        if self._pending_card_idx is None:
            return

        card_idx = self._pending_card_idx
        success, result = self.game.play_card(interaction.user.id, card_idx, self._chosen_color)
        if not success:
            await interaction.response.send_message(_uno_text('cannot_play', self.lang), ephemeral=True)
            return

        self.color_select_mode = False
        self._pending_card_idx = None

        if self.game.game_over:
            await self._handle_win(interaction)
            return

        extra = _uno_text('color_changed', self.lang, color=self._chosen_color)
        card = self.game.discard[-1]
        action_msg = self._get_action_msg(card, interaction.user)
        if action_msg:
            extra = extra + '\n' + action_msg
        await self._update_board(interaction, extra_msg=extra)

    async def _cancel_color_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.game.current_player().id:
            await interaction.response.send_message(_uno_text('not_your_turn', self.lang), ephemeral=True)
            return
        self.color_select_mode = False
        self._pending_card_idx = None
        self._chosen_color = None
        self._build_buttons()
        await interaction.response.edit_message(view=self)

    async def _draw_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.game.current_player().id:
            await interaction.response.send_message(_uno_text('not_your_turn', self.lang), ephemeral=True)
            return

        pid = interaction.user.id
        self.game.draw_card(pid, 1)
        drawn = self.game.hands[pid][-1]

        self.game._next_player()

        extra = _uno_text('drew_card', self.lang, card=drawn)
        await self._update_board(interaction, extra_msg=extra)

    async def _handle_win(self, interaction: discord.Interaction):
        """处理胜利"""
        winner = None
        for p in self.game.players:
            if p.id == self.game.winner:
                winner = p
                break
        if not winner:
            return

        reward = 30
        luck = get_talents(winner.id)[1]
        reward = int(reward * (1 + luck * 0.05))
        new_points = add_points(winner.id, reward)

        win_msg = _uno_text('win', self.lang, name=winner.display_name, reward=reward, points=new_points)
        lose_msg = _uno_text('lose', self.lang, name=winner.display_name)

        embed = self._build_embed(extra_msg=lose_msg)
        await interaction.response.edit_message(content=win_msg, embed=embed, view=None)

        if self.channel_id in uno_rooms:
            del uno_rooms[self.channel_id]

    def _build_embed(self, extra_msg=None):
        """构建游戏状态 embed"""
        current = self.game.current_player()
        top = self.game.discard[-1]
        cur_color = self.game.get_current_color()
        dir_text = _uno_text('dir_cw' if self.game.direction == 1 else 'dir_ccw', self.lang)

        embed = discord.Embed(title="\U0001f0cf UNO", color=discord.Color.yellow())
        embed.description = f"{self.game.players[0].display_name} vs {self.game.players[1].display_name}"

        embed.add_field(name=_uno_text('top_card', self.lang), value=f"{top} ({cur_color})", inline=True)
        embed.add_field(name=_uno_text('direction', self.lang), value=dir_text, inline=True)

        turn_text = _uno_text('turn', self.lang, name=current.display_name,
                              count=len(self.game.hands[current.id]))
        embed.add_field(name="\u200b", value=turn_text, inline=False)

        hand_info = ""
        for p in self.game.players:
            count = len(self.game.hands[p.id])
            marker = "\U0001f446" if p.id == current.id else ""
            hand_info += f"{p.display_name}: {count} \u5f20 {marker}\n"
        embed.add_field(name="\U0001f4cb", value=hand_info.strip(), inline=False)

        if extra_msg:
            embed.add_field(name="\U0001f4e2", value=extra_msg, inline=False)

        if self.color_select_mode:
            embed.add_field(name=_uno_text('sel_color', self.lang), value="\U0001f447", inline=False)

        return embed

    async def _update_board(self, interaction: discord.Interaction, extra_msg=None):
        """更新游戏面板"""
        self._build_buttons()
        embed = self._build_embed(extra_msg)
        turn_text = _uno_text('turn', self.lang, name=self.game.current_player().display_name,
                              count=len(self.game.hands[self.game.current_player().id]))
        await interaction.response.edit_message(content=turn_text, embed=embed, view=self)


@app_commands.command(name="uno", description="\U0001f0cf UNO Card Game / UNO\u5361\u724c\u6e38\u620f / UNO\u30ab\u30fc\u30c9\u30b2\u30fc\u30e0 / Jeu UNO")
@app_commands.describe(opponent="\u5bf9\u624b / Opponent / \u76f8\u624b / Adversaire")
async def uno_slash(interaction: discord.Interaction, opponent: discord.Member):
    await interaction.response.defer(ephemeral=False)
    channel_id = interaction.channel_id
    locale = str(interaction.locale)
    lang = 'zh' if locale.startswith('zh') else ('ja' if locale.startswith('ja') else ('fr' if locale.startswith('fr') else 'en'))

    if opponent.bot or opponent.id == interaction.user.id:
        msg = "\u274c Invalid opponent! | \u65e0\u6548\u5bf9\u624b\uff01| \u7121\u52b9\u306a\u76f8\u624b\uff01| Adversaire invalide !"
        await interaction.followup.send(msg, ephemeral=True)
        return

    if channel_id in uno_rooms:
        msg = "\u274c \u5f53\u524d\u9891\u9053\u5df2\u6709UNO\u6e38\u620f\uff01| UNO game already in progress! | \u3053\u306e\u30c1\u30e3\u30f3\u30cd\u30eb\u306b\u306f\u65e2\u306bUNO\u304c\u3042\u308b\uff01| Une partie UNO est d\u00e9j\u00e0 en cours !"
        await interaction.followup.send(msg, ephemeral=True)
        return

    game = UNOGame([interaction.user, opponent])
    uno_rooms[channel_id] = game

    view = UNOView(game, channel_id, lang)
    embed = view._build_embed()
    turn_text = _uno_text('turn', lang, name=game.current_player().display_name,
                          count=len(game.hands[game.current_player().id]))
    await interaction.followup.send(content=turn_text, embed=embed, view=view)

WEREWOLF_ROOMS = {}  # {channel_id: WerewolfGame}


def _ww_text(key, lang='en', **kw):
    """狼人杀多语言文本"""
    t = {
        # 角色名
        'role_werewolf': {'zh': '🐺 狼人', 'ja': '🐺 人狼', 'fr': '🐺 Loup-garou', 'en': '🐺 Werewolf'},
        'role_seer': {'zh': '🔮 预言家', 'ja': '🔮 預言者', 'fr': '🔮 Voyant', 'en': '🔮 Seer'},
        'role_witch': {'zh': '🧪 女巫', 'ja': '🧪 魔女', 'fr': '🧪 Sorcière', 'en': '🧪 Witch'},
        'role_villager': {'zh': '👤 平民', 'ja': '👤 村人', 'fr': '👤 Villageois', 'en': '👤 Villager'},
        # 游戏阶段
        'game_start': {
            'zh': '🐺 **狼人杀开始！** | 第 {day} 天\n玩家: {players}',
            'ja': '🐺 **人狼ゲーム開始！** | {day}日目\nプレイヤー: {players}',
            'fr': '🐺 **Le Loup-Garou commence !** | Jour {day}\nJoueurs : {players}',
            'en': '🐺 **Werewolf starts!** | Day {day}\nPlayers: {players}',
        },
        'dm_your_role': {
            'zh': '🎭 你的角色是: **{role}**',
            'ja': '🎭 あなたの役職: **{role}**',
            'fr': '🎭 Votre role : **{role}**',
            'en': '🎭 Your role: **{role}**',
        },
        'dm_werewolf_team': {
            'zh': '🐺 你的狼人队友是: {teammates}',
            'ja': '🐺 人狼の味方: {teammates}',
            'fr': '🐺 Vos allies loups-garous : {teammates}',
            'en': '🐺 Your werewolf teammates: {teammates}',
        },
        'night_title': {
            'zh': '🌙 第 {day} 夜 - 夜幕降临',
            'ja': '🌙 第{day}夜 - 夜が来た',
            'fr': '🌙 Nuit {day} - La nuit tombe',
            'en': '🌙 Night {day} - Night falls',
        },
        'night_desc': {
            'zh': '所有人请查看私信进行夜间行动...',
            'ja': 'DMで夜の行動を行ってください...',
            'fr': 'Verifiez vos MP pour les actions nocturnes...',
            'en': 'Check your DMs for night actions...',
        },
        # 夜晚行动 DM
        'wolf_action_title': {
            'zh': '🔪 狼人行动 - 选择今晚要杀的人',
            'ja': '🔪 人狼の行動 - 殺す対象を選んでください',
            'fr': '🔪 Action du loup - Choisissez votre victime',
            'en': '🔪 Werewolf Action - Choose your victim',
        },
        'seer_action_title': {
            'zh': '🔮 预言家行动 - 选择要查验的人',
            'ja': '🔮 預言者の行動 - 調べる対象を選んでください',
            'fr': '🔮 Action du voyant - Choisissez qui verifier',
            'en': '🔮 Seer Action - Choose who to check',
        },
        'witch_action_title': {
            'zh': '🧪 女巫行动',
            'ja': '🧪 魔女の行動',
            'fr': '🧪 Action de la sorcière',
            'en': '🧪 Witch Action',
        },
        'witch_killed_info': {
            'zh': '💀 今夜被狼人袭击的是: **{name}**\n你要使用解药救他/她吗？',
            'ja': '💀 今夜襲われたのは: **{name}**\n解毒剤を使って助けますか？',
            'fr': '💀 La victime est : **{name}**\nVoulez-vous la sauver ?',
            'en': '💀 Tonight\'s victim: **{name}**\nDo you want to save them?',
        },
        'witch_no_kill': {
            'zh': '🌙 今夜平安无事，没有人被袭击。',
            'ja': '🌙 今夜は誰も襲われませんでした。',
            'fr': '🌙 Personne n\'a été attaqué cette nuit.',
            'en': '🌙 No one was attacked tonight.',
        },
        'btn_save': {'zh': '💊 使用解药', 'ja': '💊 解毒剤を使う', 'fr': '💊 Sauver', 'en': '💊 Save'},
        'btn_poison': {'zh': '☠️ 使用毒药', 'ja': '☠️ 毒を使う', 'fr': '☠️ Empoisonner', 'en': '☠️ Poison'},
        'btn_skip': {'zh': '⏭️ 跳过', 'ja': '⏭️ スキップ', 'fr': '⏭️ Passer', 'en': '⏭️ Skip'},
        'btn_cancel': {'zh': '↩️ 返回', 'ja': '↩️ 戻る', 'fr': '↩️ Retour', 'en': '↩️ Back'},
        'poison_select': {
            'zh': '☠️ 选择要毒杀的人',
            'ja': '☠️ 毒殺する対象を選んでください',
            'fr': '☠️ Choisissez qui empoisonner',
            'en': '☠️ Choose who to poison',
        },
        'action_done': {
            'zh': '✅ 行动已完成！',
            'ja': '✅ 行動完了！',
            'fr': '✅ Action effectuée !',
            'en': '✅ Action completed!',
        },
        'seer_result': {
            'zh': '🔮 查验结果: **{name}** 的身份是 **{role}**',
            'ja': '🔮 結果: **{name}** の役職は **{role}**',
            'fr': '🔮 Résultat : **{name}** est **{role}**',
            'en': '🔍 Result: **{name}** is **{role}**',
        },
        'not_your_action': {
            'zh': '❌ 这不是你的行动！',
            'ja': '❌ あなたの行動ではありません！',
            'fr': '❌ Ce n\'est pas votre action !',
            'en': '❌ This is not your action!',
        },
        'already_acted': {
            'zh': '❌ 你已经行动过了！',
            'ja': '❅ 既に行動済みです！',
            'fr': '❌ Vous avez déjà agi !',
            'en': '❌ You already acted!',
        },
        # 白天阶段
        'day_title': {
            'zh': '☀️ 第 {day} 天 - 天亮了',
            'ja': '☀️ 第{day}日 - 朝になりました',
            'fr': '☀️ Jour {day} - Le jour se lève',
            'en': '☀️ Day {day} - Dawn breaks',
        },
        'night_result_none': {
            'zh': '🌙 昨夜平安无事，无人死亡。',
            'ja': '🌙 昨夜は誰も死にませんでした。',
            'fr': '🌙 Personne n\'est mort cette nuit.',
            'en': '🌙 No one died last night.',
        },
        'night_result_dead': {
            'zh': '💀 昨夜 **{names}** 被杀害了...',
            'ja': '💀 昨夜 **{names}** が殺されました...',
            'fr': '💀 Cette nuit, **{names}** est/sont mort(s)...',
            'en': '💀 Last night, **{names}** was/were killed...',
        },
        'vote_title': {
            'zh': '🗳️ 投票阶段 - 选择你要处决的嫌疑人',
            'ja': '🗳️ 投票 - 処刑する容疑者を選んでください',
            'fr': '🗳️ Vote - Choisissez qui eliminer',
            'en': '🗳️ Voting - Choose who to eliminate',
        },
        'vote_desc': {
            'zh': '点击下方按钮投票 | 已投票: {voted}/{total}',
            'ja': '下のボタンで投票 | 投票済み: {voted}/{total}',
            'fr': 'Cliquez pour voter | Votes : {voted}/{total}',
            'en': 'Click a button to vote | Voted: {voted}/{total}',
        },
        'vote_done': {
            'zh': '✅ 你投给了 **{name}**',
            'ja': '✅ **{name}** に投票しました',
            'fr': '✅ Vous avez vote contre **{name}**',
            'en': '✅ You voted for **{name}**',
        },
        'vote_result': {
            'zh': '⚖️ 投票结果:\n{results}\n\n**{name}** 被处决了！',
            'ja': '⚖️ 投票結果:\n{results}\n\n**{name}** が処刑されました！',
            'fr': '⚖️ Résultats:\n{results}\n\n**{name}** est éliminé(e) !',
            'en': '⚖️ Vote results:\n{results}\n\n**{name}** is eliminated!',
        },
        'vote_tie': {
            'zh': '⚖️ 投票结果:\n{results}\n\n平票！无人被处决。',
            'ja': '⚖️ 投票結果:\n{results}\n\n同票！処刑なし。',
            'fr': '⚖️ Résultats:\n{results}\n\nÉgalité ! Personne n\'est éliminé.',
            'en': '⚖️ Vote results:\n{results}\n\nTied! No one is eliminated.',
        },
        'vote_no_votes': {
            'zh': '⚖️ 无人投票，无人被处决。',
            'ja': '⚖️ 投票なし。処刑なし。',
            'fr': '⚖️ Pas de vote. Personne éliminé.',
            'en': '⚖️ No votes cast. No one eliminated.',
        },
        'your_role_was': {
            'zh': '🎭 {name} 的身份是: **{role}**',
            'ja': '🎭 {name} の役職: **{role}**',
            'fr': '🎭 {name} était **{role}**',
            'en': '🎭 {name} was **{role}**',
        },
        # 胜利
        'win_villagers': {
            'zh': '🎉 **好人阵营胜利！** 所有狼人已被消灭！',
            'ja': '🎉 **村人陣営の勝利！** 全ての人狼を排除しました！',
            'fr': '🎉 **Victoire des villageois !** Tous les loups-garous sont éliminés !',
            'en': '🎉 **Villagers win!** All werewolves eliminated!',
        },
        'win_werewolves': {
            'zh': '🐺 **狼人阵营胜利！** 狼人数量已达到或超过好人！',
            'ja': '🐺 **人狼陣営の勝利！** 人狼が村人と同数以上になりました！',
            'fr': '🐺 **Les loups-garous gagnent !** Ils sont aussi nombreux que les villageois !',
            'en': '🐺 **Werewolves win!** They equal or outnumber the villagers!',
        },
        'game_over_roles': {
            'zh': '📋 角色公布', 'ja': '📋 役職公開', 'fr': '📋 Roles révélés', 'en': '📋 Roles Revealed',
        },
        'win_reward': {
            'zh': '⭐ 胜方玩家各获得 **{reward}** 积分！',
            'ja': '⭐ 勝者チームは各 **{reward}** ポイント獲得！',
            'fr': '⭐ L\'équipe gagnante gagne **{reward}** points chacun !',
            'en': '⭐ Winning team members earn **{reward}** points each!',
        },
        'btn_vote_prefix': {'zh': '投', 'ja': '投票', 'fr': 'Vote', 'en': 'Vote'},
        'not_enough_players': {
            'zh': '❌ 在线成员不足4人，无法开始狼人杀！',
            'ja': '❌ オンラインメンバーが足りない！',
            'fr': '❌ Pas assez de membres en ligne !',
            'en': '❌ Not enough online members!',
        },
        'game_in_progress': {
            'zh': '❌ 当前频道已有狼人杀游戏！',
            'ja': '❌ このチャンネルには既に人狼がある！',
            'fr': '❌ Une partie est déjà en cours !',
            'en': '❌ A game is already in progress!',
        },
    }
    d = t.get(key)
    if d is None:
        return key
    if isinstance(d, dict):
        text = d.get(lang, d.get('en', key))
    else:
        text = d
    if isinstance(text, str):
        return text.format(**kw)
    return text


class WerewolfGame:
    """狼人杀游戏引擎"""

    def __init__(self, players):
        self.players = players  # [discord.Member, ...]
        self.roles = {}         # {player_id: 'werewolf'/'seer'/'witch'/'villager'}
        self.alive = {p.id: True for p in players}
        self.phase = 'night'    # 'night' or 'day'
        self.day_num = 1
        self.votes = {}         # {voter_id: target_id}
        self.game_over = False
        self.winner = None      # 'villagers' or 'werewolves'
        # 夜间行动
        self.werewolf_target = None      # 狼人击杀目标
        self._wolf_votes = {}            # {wolf_id: target_id} 多狼投票
        self.seer_target = None          # 预言家查验目标
        self.seer_result = None          # 查验结果
        self.witch_save_used = False     # 女巫是否使用解药
        self.witch_poison_target = None  # 女巫毒杀目标
        self.witch_has_save = True       # 女巫还有解药
        self.witch_has_poison = True     # 女巫还有毒药
        self.night_deaths = []           # 夜间死亡列表 [player_id, ...]
        # 行动标记
        self._acted = set()  # 已行动的玩家ID
        self._assign_roles()

    def _assign_roles(self):
        n = len(self.players)
        if n >= 7:
            role_list = ['werewolf', 'werewolf', 'seer', 'witch', 'villager', 'villager', 'villager']
        elif n >= 6:
            role_list = ['werewolf', 'werewolf', 'seer', 'witch', 'villager', 'villager']
        elif n >= 5:
            role_list = ['werewolf', 'seer', 'witch', 'villager', 'villager']
        else:
            role_list = ['werewolf', 'seer', 'villager', 'villager']
        random.shuffle(role_list)
        for i, p in enumerate(self.players):
            self.roles[p.id] = role_list[i % len(role_list)]

    def get_player(self, pid):
        for p in self.players:
            if p.id == pid:
                return p
        return None

    def get_alive_players(self):
        return [p for p in self.players if self.alive.get(p.id, False)]

    def get_werewolves(self):
        return [p for p in self.players if self.roles.get(p.id) == 'werewolf' and self.alive.get(p.id, False)]

    def get_role_name(self, role, lang='zh'):
        key_map = {
            'werewolf': 'role_werewolf',
            'seer': 'role_seer',
            'witch': 'role_witch',
            'villager': 'role_villager',
        }
        return _ww_text(key_map.get(role, 'role_villager'), lang)

    def check_win(self):
        alive_wolves = len(self.get_werewolves())
        alive_non_wolves = len([p for p in self.get_alive_players() if self.roles.get(p.id) != 'werewolf'])
        if alive_wolves == 0:
            self.game_over = True
            self.winner = 'villagers'
            return True
        if alive_wolves >= alive_non_wolves:
            self.game_over = True
            self.winner = 'werewolves'
            return True
        return False

    def reset_night(self):
        self.werewolf_target = None
        self._wolf_votes = {}
        self.seer_target = None
        self.seer_result = None
        self.witch_save_used = False
        self.witch_poison_target = None
        self.night_deaths = []
        self._acted = set()

    def resolve_wolf_votes(self):
        """统计狼人投票，多数决"""
        if not self._wolf_votes:
            self.werewolf_target = None
            return
        vote_count = {}
        for target_id in self._wolf_votes.values():
            vote_count[target_id] = vote_count.get(target_id, 0) + 1
        max_votes = max(vote_count.values())
        tied = [pid for pid, c in vote_count.items() if c == max_votes]
        self.werewolf_target = tied[0]  # 平票取第一个

    def resolve_night(self):
        """结算夜间行动，返回死亡玩家ID列表"""
        deaths = []
        # 狼人击杀
        if self.werewolf_target is not None:
            killed = self.werewolf_target
            if self.witch_save_used and self.witch_has_save:
                self.witch_has_save = False
            else:
                if self.alive.get(killed, False):
                    self.alive[killed] = False
                    deaths.append(killed)
        # 女巫毒杀
        if self.witch_poison_target is not None and self.witch_has_poison:
            target = self.witch_poison_target
            if self.alive.get(target, False):
                self.alive[target] = False
                if target not in deaths:
                    deaths.append(target)
            self.witch_has_poison = False
        self.night_deaths = deaths
        return deaths

    def reset_votes(self):
        self.votes = {}
        self._acted = set()

    def resolve_votes(self):
        """结算投票，返回被处决的玩家ID（或None表示平票/无人投票）"""
        if not self.votes:
            return None, {}
        vote_count = {}
        for target_id in self.votes.values():
            vote_count[target_id] = vote_count.get(target_id, 0) + 1
        max_votes = max(vote_count.values())
        tied = [pid for pid, c in vote_count.items() if c == max_votes]
        if len(tied) == 1:
            eliminated = tied[0]
            self.alive[eliminated] = False
            return eliminated, vote_count
        return None, vote_count  # 平票


class WerewolfActionView(discord.ui.View):
    """夜晚行动DM界面 - 通用型，支持werewolf/seer/witch"""

    def __init__(self, game, player, lang, role, event, killed_by_wolf=None):
        super().__init__(timeout=90)
        self.game = game
        self.player = player
        self.lang = lang
        self.role = role
        self.event = event
        self.killed_by_wolf = killed_by_wolf  # 狼人击杀目标(给女巫用)
        self._witch_state = 'menu'  # 'menu' or 'poison'
        self._build()

    def _build(self):
        self.clear_items()
        if self.role == 'werewolf':
            self._build_wolf_ui()
        elif self.role == 'seer':
            self._build_seer_ui()
        elif self.role == 'witch':
            self._build_witch_ui()

    def _build_wolf_ui(self):
        targets = [p for p in self.game.get_alive_players()
                   if p.id != self.player.id
                   and self.game.roles.get(p.id) != 'werewolf']
        row = 0
        col = 0
        for t in targets[:20]:
            btn = discord.ui.Button(
                label=t.display_name[:20],
                style=discord.ButtonStyle.danger,
                row=row, custom_id=f"ww_wolf_{t.id}"
            )
            btn.callback = self._make_target_callback(t.id, 'wolf')
            self.add_item(btn)
            col += 1
            if col >= 5:
                col = 0
                row += 1
        btn_skip = discord.ui.Button(
            label=_ww_text('btn_skip', self.lang),
            style=discord.ButtonStyle.secondary, row=min(row + 1, 4)
        )
        btn_skip.callback = self._skip_callback
        self.add_item(btn_skip)

    def _build_seer_ui(self):
        targets = [p for p in self.game.get_alive_players() if p.id != self.player.id]
        row = 0
        col = 0
        for t in targets[:20]:
            btn = discord.ui.Button(
                label=t.display_name[:20],
                style=discord.ButtonStyle.primary,
                row=row, custom_id=f"ww_seer_{t.id}"
            )
            btn.callback = self._make_target_callback(t.id, 'seer')
            self.add_item(btn)
            col += 1
            if col >= 5:
                col = 0
                row += 1
        btn_skip = discord.ui.Button(
            label=_ww_text('btn_skip', self.lang),
            style=discord.ButtonStyle.secondary, row=min(row + 1, 4)
        )
        btn_skip.callback = self._skip_callback
        self.add_item(btn_skip)

    def _build_witch_ui(self):
        if self._witch_state == 'menu':
            # 解药按钮
            if self.killed_by_wolf is not None and self.game.witch_has_save:
                killed_name = self.game.get_player(self.killed_by_wolf)
                killed_name = killed_name.display_name if killed_name else '?'
                btn_save = discord.ui.Button(
                    label=_ww_text('btn_save', self.lang) + f' {killed_name}',
                    style=discord.ButtonStyle.success, row=0
                )
                btn_save.callback = self._witch_save_callback
                self.add_item(btn_save)
            # 毒药按钮
            if self.game.witch_has_poison:
                btn_poison = discord.ui.Button(
                    label=_ww_text('btn_poison', self.lang),
                    style=discord.ButtonStyle.danger, row=0
                )
                btn_poison.callback = self._witch_poison_callback
                self.add_item(btn_poison)
            # 跳过
            btn_skip = discord.ui.Button(
                label=_ww_text('btn_skip', self.lang),
                style=discord.ButtonStyle.secondary, row=0
            )
            btn_skip.callback = self._skip_callback
            self.add_item(btn_skip)
        elif self._witch_state == 'poison':
            targets = [p for p in self.game.get_alive_players() if p.id != self.player.id]
            row = 0
            col = 0
            for t in targets[:20]:
                btn = discord.ui.Button(
                    label=t.display_name[:20],
                    style=discord.ButtonStyle.danger,
                    row=row, custom_id=f"ww_witch_p_{t.id}"
                )
                btn.callback = self._make_target_callback(t.id, 'witch_poison')
                self.add_item(btn)
                col += 1
                if col >= 5:
                    col = 0
                    row += 1
            btn_back = discord.ui.Button(
                label=_ww_text('btn_cancel', self.lang),
                style=discord.ButtonStyle.secondary, row=min(row + 1, 4)
            )
            btn_back.callback = self._witch_back_callback
            self.add_item(btn_back)

    def _make_target_callback(self, target_id, action_type):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.player.id:
                await interaction.response.send_message(
                    _ww_text('not_your_action', self.lang), ephemeral=True)
                return
            if self.player.id in self.game._acted:
                await interaction.response.send_message(
                    _ww_text('already_acted', self.lang), ephemeral=True)
                return
            self.game._acted.add(self.player.id)

            if action_type == 'wolf':
                self.game._wolf_votes[self.player.id] = target_id
                await interaction.response.edit_message(
                    content=_ww_text('action_done', self.lang), view=None)
                self.event.set()
            elif action_type == 'seer':
                self.game.seer_target = target_id
                target_role = self.game.roles.get(target_id, 'villager')
                self.game.seer_result = target_role
                role_name = self.game.get_role_name(target_role, self.lang)
                target_name = self.game.get_player(target_id)
                target_name = target_name.display_name if target_name else '?'
                await interaction.response.edit_message(
                    content=_ww_text('seer_result', self.lang,
                                     name=target_name, role=role_name),
                    view=None)
                self.event.set()
            elif action_type == 'witch_poison':
                self.game.witch_poison_target = target_id
                await interaction.response.edit_message(
                    content=_ww_text('action_done', self.lang), view=None)
                self.event.set()
        return callback

    async def _witch_save_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.player.id:
            await interaction.response.send_message(
                _ww_text('not_your_action', self.lang), ephemeral=True)
            return
        if self.player.id in self.game._acted:
            await interaction.response.send_message(
                _ww_text('already_acted', self.lang), ephemeral=True)
            return
        self.game._acted.add(self.player.id)
        self.game.witch_save_used = True
        await interaction.response.edit_message(
            content=_ww_text('action_done', self.lang), view=None)
        self.event.set()

    async def _witch_poison_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.player.id:
            await interaction.response.send_message(
                _ww_text('not_your_action', self.lang), ephemeral=True)
            return
        if self.player.id in self.game._acted:
            await interaction.response.send_message(
                _ww_text('already_acted', self.lang), ephemeral=True)
            return
        # 进入毒药选择界面
        self._witch_state = 'poison'
        self._build()
        await interaction.response.edit_message(
            content=_ww_text('poison_select', self.lang), view=self)

    async def _witch_back_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.player.id:
            await interaction.response.send_message(
                _ww_text('not_your_action', self.lang), ephemeral=True)
            return
        self._witch_state = 'menu'
        self._build()
        content = self._get_witch_content()
        await interaction.response.edit_message(content=content, view=self)

    async def _skip_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.player.id:
            await interaction.response.send_message(
                _ww_text('not_your_action', self.lang), ephemeral=True)
            return
        if self.player.id in self.game._acted:
            await interaction.response.send_message(
                _ww_text('already_acted', self.lang), ephemeral=True)
            return
        self.game._acted.add(self.player.id)
        await interaction.response.edit_message(
            content=_ww_text('action_done', self.lang), view=None)
        self.event.set()

    def _get_witch_content(self):
        if self.killed_by_wolf is not None:
            killed_name = self.game.get_player(self.killed_by_wolf)
            killed_name = killed_name.display_name if killed_name else '?'
            return _ww_text('witch_killed_info', self.lang, name=killed_name)
        return _ww_text('witch_no_kill', self.lang)

    def get_initial_content(self):
        if self.role == 'werewolf':
            return _ww_text('wolf_action_title', self.lang)
        elif self.role == 'seer':
            return _ww_text('seer_action_title', self.lang)
        elif self.role == 'witch':
            return self._get_witch_content()


class WerewolfVoteView(discord.ui.View):
    """白天投票界面"""

    def __init__(self, game, lang, event):
        super().__init__(timeout=120)
        self.game = game
        self.lang = lang
        self.event = event
        self._build()

    def _build(self):
        self.clear_items()
        alive = self.game.get_alive_players()
        row = 0
        col = 0
        for p in alive[:20]:
            btn = discord.ui.Button(
                label=p.display_name[:20],
                style=discord.ButtonStyle.secondary,
                row=row, custom_id=f"ww_vote_{p.id}"
            )
            btn.callback = self._make_vote_callback(p.id)
            self.add_item(btn)
            col += 1
            if col >= 5:
                col = 0
                row += 1

    def _make_vote_callback(self, target_id):
        async def callback(interaction: discord.Interaction):
            voter_id = interaction.user.id
            # 检查是否是存活的玩家
            alive_ids = [p.id for p in self.game.get_alive_players()]
            if voter_id not in alive_ids:
                await interaction.response.send_message(
                    _ww_text('not_your_action', self.lang), ephemeral=True)
                return
            if voter_id in self.game._acted:
                await interaction.response.send_message(
                    _ww_text('already_acted', self.lang), ephemeral=True)
                return
            self.game._acted.add(voter_id)
            self.game.votes[voter_id] = target_id
            target_name = self.game.get_player(target_id)
            target_name = target_name.display_name if target_name else '?'
            await interaction.response.send_message(
                _ww_text('vote_done', self.lang, name=target_name), ephemeral=True)
            # 检查是否所有人都投了票
            if len(self.game.votes) >= len(alive_ids):
                self.event.set()
        return callback


async def run_werewolf_game(game, channel, lang):
    """狼人杀主游戏循环"""
    try:
        while not game.game_over:
            game.phase = 'night'
            game.reset_night()

            night_embed = discord.Embed(
                title=_ww_text('night_title', lang, day=game.day_num),
                description=_ww_text('night_desc', lang),
                color=discord.Color.dark_purple()
            )
            await channel.send(embed=night_embed)

            # --- 第一步: 狼人 + 预言家 (并行) ---
            night_events = []

            # 狼人行动
            wolves = game.get_werewolves()
            if wolves:
                wolf_event = asyncio.Event()
                night_events.append(wolf_event)
                for wolf in wolves:
                    try:
                        view = WerewolfActionView(game, wolf, lang, 'werewolf', wolf_event)
                        content = view.get_initial_content()
                        await wolf.send(content=content, view=view)
                    except discord.Forbidden:
                        # DM发送失败,自动跳过
                        if wolf.id not in game._acted:
                            game._acted.add(wolf.id)
                # 如果所有狼人DM都发送失败,自动完成
                if all(w.id in game._acted for w in wolves):
                    wolf_event.set()

            # 预言家行动
            seer = [p for p in game.get_alive_players()
                    if game.roles.get(p.id) == 'seer']
            if seer:
                seer_event = asyncio.Event()
                night_events.append(seer_event)
                try:
                    view = WerewolfActionView(game, seer[0], lang, 'seer', seer_event)
                    content = view.get_initial_content()
                    await seer[0].send(content=content, view=view)
                except discord.Forbidden:
                    if seer[0].id not in game._acted:
                        game._acted.add(seer[0].id)
                    seer_event.set()
            # 如果没有狼人和预言家需要行动
            if not night_events:
                # 直接到女巫阶段
                pass
            else:
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*[e.wait() for e in night_events]),
                        timeout=90
                    )
                except asyncio.TimeoutError:
                    pass

            # 结算狼人投票
            game.resolve_wolf_votes()

            # --- 第二步: 女巫 (在狼人之后) ---
            witch = [p for p in game.get_alive_players()
                     if game.roles.get(p.id) == 'witch']
            if witch and (game.witch_has_save or game.witch_has_poison):
                witch_event = asyncio.Event()
                killed = game.werewolf_target
                try:
                    view = WerewolfActionView(
                        game, witch[0], lang, 'witch', witch_event,
                        killed_by_wolf=killed
                    )
                    content = view.get_initial_content()
                    await witch[0].send(content=content, view=view)
                    try:
                        await asyncio.wait_for(witch_event.wait(), timeout=60)
                    except asyncio.TimeoutError:
                        pass
                except discord.Forbidden:
                    pass

            # 结算夜晚
            deaths = game.resolve_night()

            # 检查胜利
            if game.check_win():
                await _ww_send_game_over(channel, game, lang)
                break

            game.phase = 'day'

            day_embed = discord.Embed(
                title=_ww_text('day_title', lang, day=game.day_num),
                color=discord.Color.gold()
            )
            if deaths:
                dead_names = ', '.join(
                    game.get_player(d).display_name if game.get_player(d) else '?'
                    for d in deaths
                )
                day_embed.description = _ww_text('night_result_dead', lang, names=dead_names)
                for d in deaths:
                    p = game.get_player(d)
                    if p:
                        role_name = game.get_role_name(game.roles.get(d, 'villager'), lang)
                        day_embed.add_field(
                            name='\u200b',
                            value=_ww_text('your_role_was', lang, name=p.display_name, role=role_name),
                            inline=False
                        )
            else:
                day_embed.description = _ww_text('night_result_none', lang)
            await channel.send(embed=day_embed)

            # 检查胜利 (白天死亡可能触发)
            if game.check_win():
                await _ww_send_game_over(channel, game, lang)
                break

            # --- 投票阶段 ---
            game.reset_votes()
            vote_event = asyncio.Event()
            vote_view = WerewolfVoteView(game, lang, vote_event)

            alive_count = len(game.get_alive_players())
            vote_embed = discord.Embed(
                title=_ww_text('vote_title', lang),
                description=_ww_text('vote_desc', lang, voted=0, total=alive_count),
                color=discord.Color.orange()
            )
            vote_msg = await channel.send(embed=vote_embed, view=vote_view)

            try:
                await asyncio.wait_for(vote_event.wait(), timeout=120)
            except asyncio.TimeoutError:
                pass

            # 结算投票
            eliminated, vote_count = game.resolve_votes()

            # 构建投票结果
            results_text = '\n'.join(
                f'{game.get_player(tid).display_name if game.get_player(tid) else "?"}: {cnt} 票'
                for tid, cnt in sorted(vote_count.items(), key=lambda x: -x[1])
            ) if vote_count else ''

            if eliminated is not None:
                elim_name = game.get_player(eliminated)
                elim_name = elim_name.display_name if elim_name else '?'
                result_text = _ww_text('vote_result', lang, results=results_text, name=elim_name)
                elim_role = game.get_role_name(game.roles.get(eliminated, 'villager'), lang)
                result_text += '\n' + _ww_text('your_role_was', lang, name=elim_name, role=elim_role)
            elif vote_count:
                result_text = _ww_text('vote_tie', lang, results=results_text)
            else:
                result_text = _ww_text('vote_no_votes', lang)

            result_embed = discord.Embed(
                title='\u2696\ufe0f',
                description=result_text,
                color=discord.Color.blue()
            )
            await channel.send(embed=result_embed)

            # 检查胜利
            if game.check_win():
                await _ww_send_game_over(channel, game, lang)
                break

            game.day_num += 1

    except Exception as e:
        await channel.send(f'❌ Game error: {e}')
    finally:
        if channel.id in WEREWOLF_ROOMS:
            del WEREWOLF_ROOMS[channel.id]


async def _ww_send_game_over(channel, game, lang):
    """发送游戏结束消息"""
    if game.winner == 'villagers':
        win_embed = discord.Embed(
            title=_ww_text('win_villagers', lang),
            color=discord.Color.green()
        )
    else:
        win_embed = discord.Embed(
            title=_ww_text('win_werewolves', lang),
            color=discord.Color.red()
        )

    # 公布所有角色
    roles_text = '\n'.join(
        f'{p.display_name}: {game.get_role_name(game.roles.get(p.id, "villager"), lang)}'
        f' {"" if game.alive.get(p.id, False) else "☠️"}'
        for p in game.players
    )
    win_embed.add_field(
        name=_ww_text('game_over_roles', lang),
        value=roles_text,
        inline=False
    )

    # 发放奖励
    reward = 50
    if game.winner == 'villagers':
        winners = [p for p in game.players if game.roles.get(p.id) != 'werewolf']
    else:
        winners = game.get_werewolves() + [
            p for p in game.players
            if game.roles.get(p.id) == 'werewolf' and not game.alive.get(p.id, False)
        ]
    # 发放积分
    for p in winners:
        try:
            luck = get_talents(p.id)[1]
            final_reward = int(reward * (1 + luck * 0.05))
            new_points = add_points(p.id, final_reward)
        except:
            pass

    win_embed.add_field(
        name='\u200b',
        value=_ww_text('win_reward', lang, reward=reward),
        inline=False
    )
    await channel.send(embed=win_embed)


@app_commands.command(name="werewolf", description="🐺 狼人杀 / Werewolf / 人狼 / Loup-Garou")
async def werewolf_slash(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=False)
    channel_id = interaction.channel_id
    locale = str(interaction.locale)
    lang = 'zh' if locale.startswith('zh') else ('ja' if locale.startswith('ja') else ('fr' if locale.startswith('fr') else 'en'))

    if channel_id in WEREWOLF_ROOMS:
        await interaction.followup.send(_ww_text('game_in_progress', lang), ephemeral=True)
        return

    members = [m for m in interaction.guild.members
               if not m.bot and m.status != discord.Status.offline
               and m.id != interaction.user.id]
    if len(members) < 3:
        await interaction.followup.send(_ww_text('not_enough_players', lang), ephemeral=True)
        return

    players = [interaction.user] + random.sample(members, min(3, len(members)))
    game = WerewolfGame(players)
    WEREWOLF_ROOMS[channel_id] = game

    # 私信发角色
    for p in players:
        role = game.roles.get(p.id, 'villager')
        role_name = game.get_role_name(role, lang)
        try:
            dm_content = _ww_text('dm_your_role', lang, role=role_name)
            # 如果是狼人,告知队友
            if role == 'werewolf':
                teammates = [wp for wp in players
                             if wp.id != p.id and game.roles.get(wp.id) == 'werewolf']
                if teammates:
                    tm_names = ', '.join(wp.display_name for wp in teammates)
                    dm_content += '\n' + _ww_text('dm_werewolf_team', lang, teammates=tm_names)
            await p.send(dm_content)
        except discord.Forbidden:
            pass

    # 发送游戏开始消息
    players_str = ', '.join(p.display_name for p in players)
    start_embed = discord.Embed(
        title=_ww_text('game_start', lang, day=game.day_num, players=players_str),
        color=discord.Color.purple()
    )
    start_embed.add_field(
        name='\u200b',
        value=_ww_text('night_title', lang, day=game.day_num) + '\n' + _ww_text('night_desc', lang),
        inline=False
    )
    await interaction.followup.send(embed=start_embed)

    # 启动游戏主循环
    channel = interaction.channel
    asyncio.create_task(run_werewolf_game(game, channel, lang))


QUORIDOR_ROOMS = {}  # {channel_id: QuoridorGame}

class QuoridorGame:
    """路墙棋游戏引擎"""
    def __init__(self, players, board_size=9, walls_per_player=10, custom_walls=None):
        self.board_size = board_size
        self.players = players  # [discord.Member, ...]
        self.num_players = len(players)
        self.walls_per_player = walls_per_player
        self.remaining_walls = {p.id: walls_per_player for p in players}
        
        # 玩家位置 (row, col)
        if self.num_players == 2:
            mid = board_size // 2
            self.positions = {
                players[0].id: (0, mid),      # 上方出发
                players[1].id: (board_size - 1, mid),  # 下方出发
            }
            self.goals = {
                players[0].id: ('r', board_size - 1),  # 到达底部
                players[1].id: ('r', 0),                # 到达顶部
            }
        elif self.num_players == 4:
            mid = board_size // 2
            self.positions = {
                players[0].id: (0, mid),              # 上方出发，目标到底部
                players[1].id: (board_size - 1, mid), # 下方出发，目标到顶部
                players[2].id: (mid, 0),              # 左方出发，目标到右侧
                players[3].id: (mid, board_size - 1), # 右方出发，目标到左侧
            }
            self.goals = {
                players[0].id: ('r', board_size - 1),  # 到达底部行
                players[1].id: ('r', 0),                # 到达顶部行
                players[2].id: ('c', board_size - 1),   # 到达右侧列
                players[3].id: ('c', 0),                 # 到达左侧列
            }
        else:
            mid = board_size // 2
            self.positions = {
                players[0].id: (0, mid),
                players[1].id: (board_size - 1, mid),
            }
            self.goals = {
                players[0].id: ('r', board_size - 1),
                players[1].id: ('r', 0),
            }
        
        self.current_idx = 0
        self.game_over = False
        self.winner = None
        self.walls = set()  # {(r, c, 'h'/'v')} 墙的位置和方向
        self.custom_walls = custom_walls or []
        for w in self.custom_walls:
            self.walls.add(tuple(w))
        
        # AI 模式
        self.is_ai = False
        self.ai_player_idx = None

    def current_player(self):
        return self.players[self.current_idx]

    def _next_turn(self):
        self.current_idx = (self.current_idx + 1) % self.num_players

    def _is_valid_wall(self, r, c, direction):
        """检查墙的位置是否合法"""
        if r < 0 or c < 0 or r >= self.board_size - 1 or c >= self.board_size - 1:
            return False
        if (r, c, direction) in self.walls:
            return False
        # 检查重叠（墙是2格长，需检查同方向邻接重叠和交叉）
        if direction == 'h':
            # 同方向部分重叠：墙(r,c)跨越列c和c+1，墙(r,c-1)跨越列c-1和c -> 共享列c
            if (r, c - 1, 'h') in self.walls or (r, c + 1, 'h') in self.walls:
                return False
            # 交叉：同一位置不能同时有水平和竖直墙
            if (r, c, 'v') in self.walls:
                return False
        else:  # 'v'
            if (r - 1, c, 'v') in self.walls or (r + 1, c, 'v') in self.walls:
                return False
            if (r, c, 'h') in self.walls:
                return False

        # 检查是否阻断所有路径
        temp_walls = self.walls | {(r, c, direction)}
        for pid in self.positions:
            if not self._has_path(pid, temp_walls):
                return False
        return True

    def _has_path(self, player_id, walls=None):
        """BFS 检查玩家是否还有路径到达目标"""
        if walls is None:
            walls = self.walls
        start = self.positions[player_id]
        goal_axis, goal_val = self.goals[player_id]
        visited = set()
        queue = [start]
        visited.add(start)

        while queue:
            r, c = queue.pop(0)
            if goal_axis == 'r' and r == goal_val:
                return True
            if goal_axis == 'c' and c == goal_val:
                return True
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nr, nc = r + dr, c + dc
                if 0 <= nr < self.board_size and 0 <= nc < self.board_size and (nr, nc) not in visited:
                    if not self._is_blocked(r, c, nr, nc, walls):
                        visited.add((nr, nc))
                        queue.append((nr, nc))
        return False

    def _is_blocked(self, r1, c1, r2, c2, walls=None):
        """检查两个相邻格子之间是否被墙挡住"""
        if walls is None:
            walls = self.walls
        dr = r2 - r1
        dc = c2 - c1

        if dr == 1:  # 向下移动，检查水平墙
            blocked = (r1, c1, 'h') in walls
            if c1 > 0:
                blocked = blocked or (r1, c1 - 1, 'h') in walls
            return blocked
        elif dr == -1:  # 向上移动，检查水平墙
            blocked = (r2, c2, 'h') in walls
            if c2 > 0:
                blocked = blocked or (r2, c2 - 1, 'h') in walls
            return blocked
        elif dc == 1:  # 向右移动，检查竖直墙
            blocked = (r1, c1, 'v') in walls
            if r1 > 0:
                blocked = blocked or (r1 - 1, c1, 'v') in walls
            return blocked
        elif dc == -1:  # 向左移动，检查竖直墙
            blocked = (r2, c2, 'v') in walls
            if r2 > 0:
                blocked = blocked or (r2 - 1, c2, 'v') in walls
            return blocked
        return True

    def get_valid_moves(self, player_id):
        """获取玩家所有合法移动"""
        r, c = self.positions[player_id]
        moves = []
        for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]:
            nr, nc = r + dr, c + dc
            if 0 <= nr < self.board_size and 0 <= nc < self.board_size:
                if not self._is_blocked(r, c, nr, nc):
                    # 检查是否有其他玩家
                    occupied = False
                    for pid, pos in self.positions.items():
                        if pid != player_id and pos == (nr, nc):
                            occupied = True
                            # 可以跳过对方
                            jr, jc = nr + dr, nc + dc
                            if 0 <= jr < self.board_size and 0 <= jc < self.board_size and not self._is_blocked(nr, nc, jr, jc):
                                moves.append((jr, jc))
                            break
                    if not occupied:
                        moves.append((nr, nc))
        return moves

    def move_player(self, player_id, new_r, new_c):
        """移动玩家"""
        if player_id != self.current_player().id:
            return False
        if (new_r, new_c) not in self.get_valid_moves(player_id):
            return False
        self.positions[player_id] = (new_r, new_c)
        goal_axis, goal_val = self.goals[player_id]
        reached = (goal_axis == 'r' and new_r == goal_val) or (goal_axis == 'c' and new_c == goal_val)
        if reached:
            self.game_over = True
            self.winner = player_id
            return True
        self._next_turn()
        return True

    def place_wall(self, player_id, r, c, direction):
        """放置墙"""
        if player_id != self.current_player().id:
            return False
        if self.remaining_walls[player_id] <= 0:
            return False
        if not self._is_valid_wall(r, c, direction):
            return False
        self.walls.add((r, c, direction))
        self.remaining_walls[player_id] -= 1
        self._next_turn()
        return True

    def ai_move(self):
        """AI 策略：优先靠近目标，有概率放墙阻挡对手"""
        ai_pid = self.players[self.ai_player_idx].id

        # 计算对手的最短路径长度
        opponent_pid = None
        for p in self.players:
            if p.id != ai_pid:
                opponent_pid = p.id
                break

        opp_path = self._find_shortest_path(opponent_pid) if opponent_pid else None
        opp_dist = len(opp_path) - 1 if opp_path else 999

        my_path = self._find_shortest_path(ai_pid)
        my_dist = len(my_path) - 1 if my_path else 999

        # 如果对手比我们更接近目标且有墙，尝试放墙阻挡
        if (opp_dist <= my_dist and self.remaining_walls[ai_pid] > 0
                and random.random() < 0.35 and opponent_pid):
            # 找对手路径上的一步，尝试在前面放墙
            if opp_path and len(opp_path) >= 2:
                r0, c0 = opp_path[0]
                r1, c1 = opp_path[1]
                dr, dc = r1 - r0, c1 - c0
                # 根据对手移动方向放置墙
                wall_placed = False
                if dr != 0:  # 对手竖直移动，放水平墙
                    wr = min(r0, r1)
                    for wc in [c0, c0 - 1, c0 + 1]:
                        if self._is_valid_wall(wr, wc, 'h'):
                            self.walls.add((wr, wc, 'h'))
                            self.remaining_walls[ai_pid] -= 1
                            self._next_turn()
                            wall_placed = True
                            return 'wall', (wr, wc, 'h')
                        if not wall_placed:
                            break
                elif dc != 0:  # 对手水平移动，放竖直墙
                    wc = min(c0, c1)
                    for wr in [r0, r0 - 1, r0 + 1]:
                        if self._is_valid_wall(wr, wc, 'v'):
                            self.walls.add((wr, wc, 'v'))
                            self.remaining_walls[ai_pid] -= 1
                            self._next_turn()
                            wall_placed = True
                            return 'wall', (wr, wc, 'v')
                        if not wall_placed:
                            break

        # 移动
        if my_path and len(my_path) > 1:
            next_step = my_path[1]
            self.positions[ai_pid] = next_step
            goal_axis, goal_val = self.goals[ai_pid]
            reached = (goal_axis == 'r' and next_step[0] == goal_val) or (goal_axis == 'c' and next_step[1] == goal_val)
            if reached:
                self.game_over = True
                self.winner = ai_pid
                return 'win', next_step
            self._next_turn()
            return 'move', next_step
        return 'pass', None

    def _find_shortest_path(self, player_id):
        """BFS 找最短路径"""
        start = self.positions[player_id]
        goal_axis, goal_val = self.goals[player_id]
        visited = {start: None}
        queue = [start]

        while queue:
            r, c = queue.pop(0)
            if (goal_axis == 'r' and r == goal_val) or (goal_axis == 'c' and c == goal_val):
                # 重建路径
                path = []
                cur = (r, c)
                while cur is not None:
                    path.append(cur)
                    cur = visited[cur]
                return path[::-1]
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nr, nc = r + dr, c + dc
                if 0 <= nr < self.board_size and 0 <= nc < self.board_size:
                    if (nr, nc) not in visited and not self._is_blocked(r, c, nr, nc):
                        # 不能踩其他玩家
                        occupied = any(pos == (nr, nc) for pid, pos in self.positions.items() if pid != player_id)
                        if not occupied:
                            visited[(nr, nc)] = (r, c)
                            queue.append((nr, nc))
        return None

    def render_board(self, lang='zh'):
        """渲染棋盘为文本"""
        size = self.board_size
        grid = [['⬜' for _ in range(size)] for _ in range(size)]

        # 标记玩家
        symbols = ['🔴', '🔵', '🟢', '🟡']
        for i, p in enumerate(self.players):
            if p.id in self.positions:
                r, c = self.positions[p.id]
                grid[r][c] = symbols[i % len(symbols)]

        lines = []
        for r in range(size):
            row_str = ''
            for c in range(size):
                row_str += grid[r][c]
                # 检查右边是否有竖墙
                if c < size - 1:
                    has_vwall = (r, c, 'v') in self.walls
                    if r > 0:
                        has_vwall = has_vwall or (r - 1, c, 'v') in self.walls
                    row_str += '│' if has_vwall else ' '
            lines.append(row_str)
            # 检查下边是否有横墙
            if r < size - 1:
                wall_line = ''
                for c in range(size):
                    has_hwall = (r, c, 'h') in self.walls
                    if c > 0:
                        has_hwall = has_hwall or (r, c - 1, 'h') in self.walls
                    wall_line += '─ ' if has_hwall else '  '
                lines.append(wall_line)

        return '```\n' + '\n'.join(lines) + '\n```'


def _q_text(key, lang='en', **kw):
    """路墙棋多语言文本"""
    t = {
        'turn': {
            'zh': '**{name}** 的回合 | 剩余墙: {walls}',
            'ja': '**{name}** の番 | 残り壁: {walls}',
            'fr': 'Tour de **{name}** | Murs restants : {walls}',
            'en': "**{name}**'s turn | Walls left: {walls}",
        },
        'not_your_turn': {
            'zh': '❌ 还没轮到你！', 'ja': '❌ あなたの番ではありません！',
            'fr': "❌ Ce n'est pas votre tour !", 'en': '❌ Not your turn!',
        },
        'invalid_move': {
            'zh': '❌ 非法移动！', 'ja': '❌ 無効な移動！',
            'fr': '❌ Mouvement invalide !', 'en': '❌ Invalid move!',
        },
        'no_walls': {
            'zh': '❌ 你没有墙了！', 'ja': '❌ 壁がありません！',
            'fr': '❌ Aucun mur restant !', 'en': '❌ No walls left!',
        },
        'invalid_wall': {
            'zh': '❌ 无法在此放置墙！', 'ja': '❌ ここに壁を置けません！',
            'fr': '❌ Impossible de placer un mur ici !', 'en': '❌ Cannot place wall here!',
        },
        'win': {
            'zh': '🎉 **{name}** 到达终点！获胜！+**{reward}** ⭐ | 当前: **{points}** ⭐',
            'ja': '🎉 **{name}** がゴールに到着！勝利！+**{reward}** ⭐ | 現在: **{points}** ⭐',
            'fr': '🎉 **{name}** atteint l\'arrivée ! Victoire ! +**{reward}** ⭐ | Actuel : **{points}** ⭐',
            'en': '🎉 **{name}** reaches the goal! Victory! +**{reward}** ⭐ | Current: **{points}** ⭐',
        },
        'lose_ai': {
            'zh': '😢 **{name}** 到达终点！你输了！',
            'ja': '😢 **{name}** がゴールに到着！あなたの負け！',
            'fr': '😢 **{name}** atteint l\'arrivée ! Tu as perdu !',
            'en': '😢 **{name}** reaches the goal! You lose!',
        },
        'ai_wall': {
            'zh': '🧱 AI 放置了一面墙！', 'ja': '🧱 AIが壁を置いた！',
            'fr': '🧱 L\'IA a placé un mur !', 'en': '🧱 AI placed a wall!',
        },
        'btn_move': {
            'zh': '移动', 'ja': '移動', 'fr': 'Bouger', 'en': 'Move',
        },
        'btn_wall': {
            'zh': '放墙', 'ja': '壁を置く', 'fr': 'Mur', 'en': 'Wall',
        },
        'btn_cancel': {
            'zh': '取消', 'ja': 'キャンセル', 'fr': 'Annuler', 'en': 'Cancel',
        },
        'sel_row': {
            'zh': '选择行', 'ja': '行を選択', 'fr': 'Ligne', 'en': 'Row',
        },
        'sel_col': {
            'zh': '选择列', 'ja': '列を選択', 'fr': 'Colonne', 'en': 'Column',
        },
        'sel_dir': {
            'zh': '选择方向', 'ja': '方向を選択', 'fr': 'Direction', 'en': 'Direction',
        },
        'dir_h': {
            'zh': '横向 (━)', 'ja': '水平 (━)', 'fr': 'Horizontal (━)', 'en': 'Horizontal (━)',
        },
        'dir_v': {
            'zh': '竖向 (┃)', 'ja': '垂直 (┃)', 'fr': 'Vertical (┃)', 'en': 'Vertical (┃)',
        },
        'place_wall': {
            'zh': '🏗️ 放置墙', 'ja': '🏗️ 壁を置く', 'fr': '🏗️ Placer mur', 'en': '🏗️ Place Wall',
        },
        'dir_labels': {
            'zh': ['⬆️ 上', '⬇️ 下', '⬅️ 左', '➡️ 右'],
            'ja': ['⬆️ 上', '⬇️ 下', '⬅️ 左', '⬆️ 右'],
            'fr': ['⬆️ Haut', '⬇️ Bas', '⬅️ Gauche', '➡️ Droite'],
            'en': ['⬆️ Up', '⬇️ Down', '⬅️ Left', '➡️ Right'],
        },
        'jump_prefix': {
            'zh': '跳', 'ja': '跳', 'fr': 'Saut', 'en': 'Jump',
        },
    }
    d = t.get(key)
    if d is None:
        return key
    if isinstance(d, dict):
        text = d.get(lang, d.get('en', key))
    else:
        text = d
    if isinstance(text, str):
        return text.format(**kw)
    return text


class QuoridorView(discord.ui.View):
    def __init__(self, game, channel_id, lang):
        super().__init__(timeout=600)
        self.game = game
        self.channel_id = channel_id
        self.lang = lang
        self.wall_mode = False  # 是否在放墙模式
        self._wall_row = None
        self._wall_col = None
        self._wall_dir = None
        self._build_buttons()

    def _build_buttons(self):
        self.clear_items()
        if self.wall_mode:
            self._build_wall_ui()
        else:
            self._build_move_ui()

    def _build_move_ui(self):
        """构建移动按钮界面"""
        current = self.game.current_player()
        pid = current.id
        moves = self.game.get_valid_moves(pid)
        r, c = self.game.positions[pid]

        # 计算每个移动的方向
        dir_moves = {}  # direction_index -> (nr, nc)
        for nr, nc in moves:
            dr, dc = nr - r, nc - c
            if dr == -1:
                dir_moves[0] = (nr, nc)  # 上
            elif dr == 1:
                dir_moves[1] = (nr, nc)  # 下
            elif dc == -1:
                dir_moves[2] = (nr, nc)  # 左
            elif dc == 1:
                dir_moves[3] = (nr, nc)  # 右

        dir_labels = _q_text('dir_labels', self.lang)
        row0 = []
        row1 = []
        # 上
        if 0 in dir_moves:
            nr, nc = dir_moves[0]
            is_jump = abs(nr - r) > 1
            label = dir_labels[0] + (f'({_q_text("jump_prefix", self.lang)})' if is_jump else '')
            btn = discord.ui.Button(label=label, style=discord.ButtonStyle.primary, row=0)
            btn.callback = self._make_move_callback(nr, nc)
            row0.append(btn)
        # 下
        if 1 in dir_moves:
            nr, nc = dir_moves[1]
            is_jump = abs(nr - r) > 1
            label = dir_labels[1] + (f'({_q_text("jump_prefix", self.lang)})' if is_jump else '')
            btn = discord.ui.Button(label=label, style=discord.ButtonStyle.primary, row=1)
            btn.callback = self._make_move_callback(nr, nc)
            row1.append(btn)

        for btn in row0:
            self.add_item(btn)
        for btn in row1:
            self.add_item(btn)

        # 放墙按钮
        if self.game.remaining_walls.get(pid, 0) > 0:
            btn_wall = discord.ui.Button(
                label=_q_text('btn_wall', self.lang), style=discord.ButtonStyle.success, row=2
            )
            btn_wall.callback = self._enter_wall_mode
            self.add_item(btn_wall)

    def _build_wall_ui(self):
        """构建放墙界面：行/列/方向下拉 + 确认/取消"""
        size = self.game.board_size
        # 行下拉
        row_opts = [
            discord.SelectOption(label=f'{_q_text("sel_row", self.lang)} {i}', value=str(i))
            for i in range(size - 1)
        ]
        sel_row = discord.ui.Select(placeholder=_q_text('sel_row', self.lang), options=row_opts, row=0)
        sel_row.callback = self._sel_row_callback
        self.add_item(sel_row)

        # 列下拉
        col_opts = [
            discord.SelectOption(label=f'{_q_text("sel_col", self.lang)} {i}', value=str(i))
            for i in range(size - 1)
        ]
        sel_col = discord.ui.Select(placeholder=_q_text('sel_col', self.lang), options=col_opts, row=1)
        sel_col.callback = self._sel_col_callback
        self.add_item(sel_col)

        # 方向下拉
        dir_opts = [
            discord.SelectOption(label=_q_text('dir_h', self.lang), value='h'),
            discord.SelectOption(label=_q_text('dir_v', self.lang), value='v'),
        ]
        sel_dir = discord.ui.Select(placeholder=_q_text('sel_dir', self.lang), options=dir_opts, row=2)
        sel_dir.callback = self._sel_dir_callback
        self.add_item(sel_dir)

        # 确认按钮
        btn_place = discord.ui.Button(label=_q_text('place_wall', self.lang), style=discord.ButtonStyle.success, row=3)
        btn_place.callback = self._place_wall_callback
        self.add_item(btn_place)

        # 取消按钮
        btn_cancel = discord.ui.Button(label=_q_text('btn_cancel', self.lang), style=discord.ButtonStyle.secondary, row=3)
        btn_cancel.callback = self._cancel_wall_mode
        self.add_item(btn_cancel)

    async def _sel_row_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.game.current_player().id:
            await interaction.response.send_message(_q_text('not_your_turn', self.lang), ephemeral=True)
            return
        self._wall_row = int(interaction.data['values'][0])
        await interaction.response.defer()

    async def _sel_col_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.game.current_player().id:
            await interaction.response.send_message(_q_text('not_your_turn', self.lang), ephemeral=True)
            return
        self._wall_col = int(interaction.data['values'][0])
        await interaction.response.defer()

    async def _sel_dir_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.game.current_player().id:
            await interaction.response.send_message(_q_text('not_your_turn', self.lang), ephemeral=True)
            return
        self._wall_dir = interaction.data['values'][0]
        await interaction.response.defer()

    async def _enter_wall_mode(self, interaction: discord.Interaction):
        if interaction.user.id != self.game.current_player().id:
            await interaction.response.send_message(_q_text('not_your_turn', self.lang), ephemeral=True)
            return
        self._wall_row = None
        self._wall_col = None
        self._wall_dir = None
        self.wall_mode = True
        self._build_buttons()
        await interaction.response.edit_message(view=self)

    async def _cancel_wall_mode(self, interaction: discord.Interaction):
        if interaction.user.id != self.game.current_player().id:
            await interaction.response.send_message(_q_text('not_your_turn', self.lang), ephemeral=True)
            return
        self.wall_mode = False
        self._build_buttons()
        await interaction.response.edit_message(view=self)

    async def _place_wall_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.game.current_player().id:
            await interaction.response.send_message(_q_text('not_your_turn', self.lang), ephemeral=True)
            return

        wr = getattr(self, '_wall_row', None)
        wc = getattr(self, '_wall_col', None)
        wd = getattr(self, '_wall_dir', None)

        if wr is None or wc is None or wd is None:
            await interaction.response.send_message(
                _q_text('invalid_wall', self.lang), ephemeral=True
            )
            return

        pid = interaction.user.id
        if self.game.remaining_walls.get(pid, 0) <= 0:
            await interaction.response.send_message(_q_text('no_walls', self.lang), ephemeral=True)
            return

        result = self.game.place_wall(pid, wr, wc, wd)
        if not result:
            await interaction.response.send_message(_q_text('invalid_wall', self.lang), ephemeral=True)
            return

        self.wall_mode = False

        if self.game.game_over:
            await self._handle_win(interaction)
            return

        # AI 回合
        if await self._maybe_ai_turn(interaction):
            return

        await self._update_board(interaction)

    def _make_move_callback(self, r, c):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.game.current_player().id:
                await interaction.response.send_message(_q_text('not_your_turn', self.lang), ephemeral=True)
                return

            result = self.game.move_player(interaction.user.id, r, c)
            if not result:
                await interaction.response.send_message(_q_text('invalid_move', self.lang), ephemeral=True)
                return

            if self.game.game_over:
                await self._handle_win(interaction)
                return

            # AI 回合
            if await self._maybe_ai_turn(interaction):
                return

            await self._update_board(interaction)
        return callback

    async def _handle_win(self, interaction: discord.Interaction):
        """处理玩家获胜"""
        winner = None
        for p in self.game.players:
            if p.id == self.game.winner:
                winner = p
                break
        if not winner:
            return

        reward = 40
        is_ai_winner = (self.game.is_ai and self.game.ai_player_idx is not None
                        and winner.id == self.game.players[self.game.ai_player_idx].id)
        if is_ai_winner:
            # AI 获胜
            msg = _q_text('lose_ai', self.lang, name=winner.display_name)
            await interaction.response.edit_message(content=msg, view=None)
        else:
            luck = get_talents(winner.id)[1]
            reward = int(reward * (1 + luck * 0.05))
            new_points = add_points(winner.id, reward)
            msg = _q_text('win', self.lang, name=winner.display_name, reward=reward, points=new_points)
            await interaction.response.edit_message(content=msg, view=None)

        if self.channel_id in QUORIDOR_ROOMS:
            del QUORIDOR_ROOMS[self.channel_id]

    async def _maybe_ai_turn(self, interaction: discord.Interaction):
        """如果轮到AI则执行AI回合，返回True表示AI已行动"""
        if not self.game.is_ai:
            return False
        if self.game.current_player().id != self.game.players[self.game.ai_player_idx].id:
            return False

        await asyncio.sleep(1)
        action, pos = self.game.ai_move()

        if self.game.game_over:
            ai_player = self.game.players[self.game.ai_player_idx]
            msg = _q_text('lose_ai', self.lang, name=ai_player.display_name)
            await interaction.edit_original_response(content=msg, view=None)
            if self.channel_id in QUORIDOR_ROOMS:
                del QUORIDOR_ROOMS[self.channel_id]
            return True

        if action == 'wall':
            # AI放了墙，通知一下
            await interaction.edit_original_response(content=_q_text('ai_wall', self.lang), view=None)
            await asyncio.sleep(0.8)

        await self._update_board(interaction)
        return True

    async def _update_board(self, interaction: discord.Interaction):
        self.wall_mode = False
        self._build_buttons()
        board_text = self.game.render_board(self.lang)
        current = self.game.current_player()
        wall_info = self.game.remaining_walls.get(current.id, 0)
        turn_msg = _q_text('turn', self.lang, name=current.display_name, walls=wall_info)
        content = turn_msg + '\n' + board_text
        await interaction.edit_original_response(content=content, view=self)


# ---- 路墙棋 FakeMember (AI用) ----
class QuoridorFakeMember:
    def __init__(self, name, id_num):
        self.id = id_num
        self.name = name
        self.display_name = name


def _q_start_msg(lang, p1_name, p2_name, board_size, extra=''):
    """路墙棋开始消息"""
    msgs = {
        'zh': f'\U0001f9f1 \u8def\u5899\u68cb\u5f00\u59cb\uff01**{p1_name}** vs **{p2_name}**\n\u68cb\u76d8: {board_size}x{board_size}{extra}',
        'ja': f'\u0001f9f1 \u8def\u5899\u68cb\u958b\u59cb\uff01**{p1_name}** vs **{p2_name}**\n\u30dc\u30fc\u30c9: {board_size}x{board_size}{extra}',
        'fr': f'\u0001f9f1 Quoridor commence ! **{p1_name}** vs **{p2_name}**\nPlateau : {board_size}x{board_size}{extra}',
        'en': f'\u0001f9f1 Quoridor starts! **{p1_name}** vs **{p2_name}**\nBoard: {board_size}x{board_size}{extra}',
    }
    return msgs.get(lang, msgs['en'])


def _q_start_msg_4p(lang, names, board_size, extra=''):
    """4\u4eba\u8def\u5899\u68cb\u5f00\u59cb\u6d88\u606f"""
    names_str = ' vs '.join(f'**{n}**' for n in names)
    msgs = {
        'zh': f'\u0001f9f1 4\u4eba\u8def\u5899\u68cb\u5f00\u59cb\uff01{names_str}\n\u68cb\u76d8: {board_size}x{board_size}{extra}',
        'ja': f'\u0001f9f1 4\u4eba\u8def\u5899\u68cb\u958b\u59cb\uff01{names_str}\n\u30dc\u30fc\u30c9: {board_size}x{board_size}{extra}',
        'fr': f'\u0001f9f1 Quoridor 4 joueurs ! {names_str}\nPlateau : {board_size}x{board_size}{extra}',
        'en': f'\u0001f9f1 4-Player Quoridor starts! {names_str}\nBoard: {board_size}x{board_size}{extra}',
    }
    return msgs.get(lang, msgs['en'])


@app_commands.command(name="quoridor", description="\U0001f9f1 \u8def\u5899\u68cb / Quoridor / \u58c1\u5c06\u68cb")
@app_commands.describe(
    mode="\u6e38\u620f\u6a21\u5f0f (\u9ed8\u8ba4: \u53cc\u4eba\u968f\u673a\u5339\u914d) / Game mode (default: random PvP)",
    opponent="\u6307\u5b9a\u5bf9\u624b (PvP\u6a21\u5f0f) / Opponent",
    opponent2="4\u4eba\u6a21\u5f0f\u7b2c3\u4f4d\u73a9\u5bb6 / 3rd player (4P mode)",
    opponent3="4\u4eba\u6a21\u5f0f\u7b2c4\u4f4d\u73a9\u5bb6 / 4th player (4P mode)",
    board_size="\u68cb\u76d8\u5927\u5c0f 5-14 (\u9ed8\u8ba4 9) / Board size 5-14 (default 9)",
    walls_per_player="\u6bcf\u4eba\u5899\u6570 (\u9ed8\u8ba4 10) / Walls per player (default 10)",
    custom_walls="\u81ea\u5b9a\u4e49\u5899 \u683c\u5f0f: r,c,h;r,c,v / Custom walls format: r,c,h;r,c,v",
)
@app_commands.choices(mode=[
    app_commands.Choice(name="\u666e\u901a\u6a21\u5f0f - \u53cc\u4eba\u968f\u673a\u5339\u914d / Normal (Random PvP)", value="normal"),
    app_commands.Choice(name="\U0001f916 \u5bf9\u6218\u4eba\u673a / VS AI", value="ai"),
    app_commands.Choice(name="\U0001f465 \u6307\u5b9a\u5bf9\u624b / VS Member", value="pvp"),
    app_commands.Choice(name="\U0001f465 4\u4eba\u968f\u673a\u5339\u914d / 4P Random", value="4p_random"),
    app_commands.Choice(name="\U0001f465 4\u4eba\u6307\u5b9a / 4P Custom", value="4p_custom"),
    app_commands.Choice(name="\u2699\ufe0f \u81ea\u5b9a\u4e49\u89c4\u5219 / Custom Rules", value="custom"),
])
async def quoridor_slash(
    interaction: discord.Interaction,
    mode: app_commands.Choice[str] = None,
    opponent: discord.Member = None,
    opponent2: discord.Member = None,
    opponent3: discord.Member = None,
    board_size: int = 9,
    walls_per_player: int = 10,
    custom_walls: str = None,
):
    await interaction.response.defer(ephemeral=False)
    channel_id = interaction.channel_id
    locale = str(interaction.locale)
    lang = 'zh' if locale.startswith('zh') else ('ja' if locale.startswith('ja') else ('fr' if locale.startswith('fr') else 'en'))

    # \u9ed8\u8ba4\u6a21\u5f0f = \u53cc\u4eba\u968f\u673a\u5339\u914d
    mode_val = mode.value if mode else 'normal'

    if channel_id in QUORIDOR_ROOMS:
        msgs = {
            'zh': '\u274c \u5f53\u524d\u9891\u9053\u5df2\u6709\u8def\u5899\u68cb\u6e38\u620f\uff01',
            'ja': '\u274c \u3053\u306e\u30c1\u30e3\u30f3\u30cd\u30eb\u306b\u306f\u65e2\u306b\u8def\u5899\u68cb\u304c\u3042\u308b\uff01',
            'fr': '\u274c Une partie de Quoridor est d\u00e9j\u00e0 en cours !',
            'en': '\u274c A Quoridor game is already in progress!',
        }
        await interaction.followup.send(msgs.get(lang, msgs['en']), ephemeral=True)
        return

    # \u68cb\u76d8\u5927\u5c0f\u9650\u5236 5-14
    if board_size < 5 or board_size > 14:
        board_size = 9
    # \u5899\u6570\u9650\u5236
    if walls_per_player < 1 or walls_per_player > 30:
        walls_per_player = 10

    # \u89e3\u6790\u81ea\u5b9a\u4e49\u5899
    parsed_custom_walls = []
    if custom_walls:
        for part in custom_walls.split(';'):
            part = part.strip()
            if not part:
                continue
            try:
                vals = part.split(',')
                if len(vals) == 3:
                    wr, wc, wd = int(vals[0]), int(vals[1]), vals[2].strip().lower()
                    if wd in ('h', 'v') and 0 <= wr < board_size - 1 and 0 <= wc < board_size - 1:
                        parsed_custom_walls.append((wr, wc, wd))
            except (ValueError, IndexError):
                pass

    extra = f' | \u5899\u6570: {walls_per_player}' if walls_per_player != 10 else ''
    if parsed_custom_walls:
        extra += f' | \u81ea\u5b9a\u4e49\u5899: {len(parsed_custom_walls)}'

    if mode_val == 'ai':
        ai_name = random.choice(['QuoridorMaster', 'WallBuilder', 'PathFinder', 'MazeRunner', 'BlockMaster'])
        ai_member = QuoridorFakeMember(ai_name, 999999999 + random.randint(0, 899999))
        game = QuoridorGame([interaction.user, ai_member], board_size=board_size,
                            walls_per_player=walls_per_player, custom_walls=parsed_custom_walls)
        game.is_ai = True
        game.ai_player_idx = 1
        QUORIDOR_ROOMS[channel_id] = game
        board_text = game.render_board(lang)
        start_msg = _q_start_msg(lang, interaction.user.display_name, ai_name, board_size, extra)
        view = QuoridorView(game, channel_id, lang)
        await interaction.followup.send(start_msg + '\n' + board_text, view=view)

    elif mode_val == 'pvp':
        if not opponent or opponent.bot or opponent.id == interaction.user.id:
            msgs = {
                'zh': '\u274c \u65e0\u6548\u5bf9\u624b\uff01', 'ja': '\u274c \u7121\u52b9\u306a\u76f8\u624b\uff01',
                'fr': '\u274c Adversaire invalide !', 'en': '\u274c Invalid opponent!',
            }
            await interaction.followup.send(msgs.get(lang, msgs['en']), ephemeral=True)
            return
        game = QuoridorGame([interaction.user, opponent], board_size=board_size,
                            walls_per_player=walls_per_player, custom_walls=parsed_custom_walls)
        QUORIDOR_ROOMS[channel_id] = game
        board_text = game.render_board(lang)
        start_msg = _q_start_msg(lang, interaction.user.display_name, opponent.display_name, board_size, extra)
        view = QuoridorView(game, channel_id, lang)
        await interaction.followup.send(start_msg + '\n' + board_text, view=view)

    elif mode_val == '4p_random':
        members = [m for m in interaction.guild.members
                    if not m.bot and m.status != discord.Status.offline and m.id != interaction.user.id]
        if len(members) < 3:
            msgs = {
                'zh': '\u274c \u5728\u7ebf\u6210\u5458\u4e0d\u8db3\uff08\u9700\u89813\u4eba\u4ee5\u4e0a\uff09\uff01',
                'ja': '\u274c \u30aa\u30f3\u30e9\u30a4\u30f3\u30e1\u30f3\u30d0\u30fc\u304c\u8db3\u308a\u306a\u3044\uff083\u4eba\u4ee5\u4e0a\u5fc5\u8981\uff09\uff01',
                'fr': '\u274c Pas assez de membres en ligne (3 minimum) !',
                'en': '\u274c Not enough online members (need 3+)!',
            }
            await interaction.followup.send(msgs.get(lang, msgs['en']), ephemeral=True)
            return
        import random as _rng
        targets = _rng.sample(members, 3)
        players = [interaction.user] + targets
        game = QuoridorGame(players, board_size=board_size,
                            walls_per_player=walls_per_player, custom_walls=parsed_custom_walls)
        QUORIDOR_ROOMS[channel_id] = game
        board_text = game.render_board(lang)
        names = [p.display_name for p in players]
        start_msg = _q_start_msg_4p(lang, names, board_size, extra)
        view = QuoridorView(game, channel_id, lang)
        await interaction.followup.send(start_msg + '\n' + board_text, view=view)

    elif mode_val == '4p_custom':
        opps = [o for o in [opponent, opponent2, opponent3] if o and not o.bot and o.id != interaction.user.id]
        # \u53bb\u91cd
        seen = {interaction.user.id}
        unique_opps = []
        for o in opps:
            if o.id not in seen:
                seen.add(o.id)
                unique_opps.append(o)
        if len(unique_opps) < 3:
            msgs = {
                'zh': '\u274c \u9700\u8981\u6307\u5b9a3\u540d\u4e0d\u540c\u7684\u5bf9\u624b\uff01',
                'ja': '\u274c 3\u540d\u306e\u7570\u306a\u308b\u76f8\u624b\u3092\u6307\u5b9a\u3057\u3066\u304f\u3060\u3055\u3044\uff01',
                'fr': '\u274c Sp\u00e9cifiez 3 adversaires diff\u00e9rents !',
                'en': '\u274c Need 3 different opponents!',
            }
            await interaction.followup.send(msgs.get(lang, msgs['en']), ephemeral=True)
            return
        players = [interaction.user] + unique_opps[:3]
        game = QuoridorGame(players, board_size=board_size,
                            walls_per_player=walls_per_player, custom_walls=parsed_custom_walls)
        QUORIDOR_ROOMS[channel_id] = game
        board_text = game.render_board(lang)
        names = [p.display_name for p in players]
        start_msg = _q_start_msg_4p(lang, names, board_size, extra)
        view = QuoridorView(game, channel_id, lang)
        await interaction.followup.send(start_msg + '\n' + board_text, view=view)

    elif mode_val == 'custom':
        if opponent and not opponent.bot and opponent.id != interaction.user.id:
            # \u6307\u5b9a\u4e86\u5bf9\u624b -> \u53cc\u4ebaPvP
            game = QuoridorGame([interaction.user, opponent], board_size=board_size,
                                walls_per_player=walls_per_player, custom_walls=parsed_custom_walls)
            p2_name = opponent.display_name
        else:
            # \u672a\u6307\u5b9a\u5bf9\u624b -> AI
            ai_name = random.choice(['QuoridorMaster', 'WallBuilder', 'PathFinder', 'MazeRunner', 'BlockMaster'])
            ai_member = QuoridorFakeMember(ai_name, 999999999 + random.randint(0, 899999))
            game = QuoridorGame([interaction.user, ai_member], board_size=board_size,
                                walls_per_player=walls_per_player, custom_walls=parsed_custom_walls)
            game.is_ai = True
            game.ai_player_idx = 1
            p2_name = ai_name
        QUORIDOR_ROOMS[channel_id] = game
        board_text = game.render_board(lang)
        start_msg = _q_start_msg(lang, interaction.user.display_name, p2_name, board_size, extra)
        view = QuoridorView(game, channel_id, lang)
        await interaction.followup.send(start_msg + '\n' + board_text, view=view)

    else:
        members = [m for m in interaction.guild.members
                    if not m.bot and m.status != discord.Status.offline and m.id != interaction.user.id]
        if not members:
            msgs = {
                'zh': '\u274c \u6ca1\u6709\u5728\u7ebf\u6210\u5458\uff01',
                'ja': '\u274c \u30aa\u30f3\u30e9\u30a4\u30f3\u30e1\u30f3\u30d0\u30fc\u304c\u3044\u306a\u3044\uff01',
                'fr': '\u274c Aucun membre en ligne !',
                'en': '\u274c No online members!',
            }
            await interaction.followup.send(msgs.get(lang, msgs['en']), ephemeral=True)
            return
        target = random.choice(members)
        game = QuoridorGame([interaction.user, target], board_size=board_size,
                            walls_per_player=walls_per_player, custom_walls=parsed_custom_walls)
        QUORIDOR_ROOMS[channel_id] = game
        board_text = game.render_board(lang)
        start_msg = _q_start_msg(lang, interaction.user.display_name, target.display_name, board_size, extra)
        view = QuoridorView(game, channel_id, lang)
        await interaction.followup.send(start_msg + '\n' + board_text, view=view)


async def setup(bot):
    # 注册模块级 app commands
    module = sys.modules[__name__]
    for obj in vars(module).values():
        if isinstance(obj, app_commands.Command):
            bot.tree.add_command(obj)
    await bot.add_cog(BigGamesCog(bot))
