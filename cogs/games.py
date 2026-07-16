import discord
from discord import app_commands
from discord.ext import commands
import random
import asyncio
import sys

from utils.db import add_points, get_or_create_user, get_talents
from utils import VIRTUAL_OPPONENTS


class GamesCog(commands.Cog, name="Games"):
    """小游戏集合：猜拳、猜数、骰子、对战、摇奖机、成语接龙、扫雷"""

    def __init__(self, bot):
        self.bot = bot



@app_commands.command(name="games", description="查看可玩的小游戏 / View mini games / ミニゲーム / Mini-jeux")
async def games_slash(interaction: discord.Interaction):
    locale = str(interaction.locale)
    if locale.startswith('zh'):
        title = "🎮 小游戏列表"
        desc = "完成游戏任务赚取积分！"
        games = [
            ("/rps", "石头剪刀布 — 赢 +20⭐ | 平 +5⭐"),
            ("/guess", "猜数字 — 猜中 +50⭐ | 一次猜中 +100⭐"),
            ("/dice", "掷骰子 — 赢 +20⭐ | 平 +5⭐"),
        ]
    elif locale.startswith('ja'):
        title = "🎮 ミニゲーム一覧"
        desc = "ゲームをクリアしてポイントを獲得しよう！"
        games = [
            ("/rps", "じゃんけん — 勝ち +20⭐ | 引き分け +5⭐"),
            ("/guess", "数字当て — 正解 +50⭐ | 一発正解 +100⭐"),
            ("/dice", "サイコロ — 勝ち +20⭐ | 引き分け +5⭐"),
        ]
    elif locale.startswith('fr'):
        title = "🎮 Liste des mini-jeux"
        desc = "Complète des missions de jeu pour gagner des points !"
        games = [
            ("/rps", "Pierre Feuille Ciseaux — Victoire +20⭐ | Égalité +5⭐"),
            ("/guess", "Devinez le nombre — Correct +50⭐ | Du premier coup +100⭐"),
            ("/dice", "Dés — Victoire +20⭐ | Égalité +5⭐"),
        ]
    else:
        title = "🎮 Mini Games"
        desc = "Complete game missions to earn points!"
        games = [
            ("/rps", "Rock Paper Scissors — Win +20⭐ | Draw +5⭐"),
            ("/guess", "Number Guessing — Correct +50⭐ | First try +100⭐"),
            ("/dice", "Dice Roll — Win +20⭐ | Draw +5⭐"),
        ]

    embed = discord.Embed(title=title, description=desc, color=discord.Color.teal())
    for cmd, desc_text in games:
        embed.add_field(name=cmd, value=desc_text, inline=False)
    embed.set_footer(text="Good luck! 祝你好运！頑張って！Bonne chance！")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@app_commands.command(name="rps", description="石头剪刀布 / Rock Paper Scissors / じゃんけん / Pierre Feuille Ciseaux")
@app_commands.choices(choice=[
    app_commands.Choice(name="石头 / Rock / グー / Pierre", value="rock"),
    app_commands.Choice(name="剪刀 / Scissors / チョキ / Ciseaux", value="scissors"),
    app_commands.Choice(name="布 / Paper / パー / Feuille", value="paper"),
])
async def rps_slash(interaction: discord.Interaction, choice: app_commands.Choice[str]):
    bot_choice = random.choice(['rock', 'scissors', 'paper'])
    user_choice = choice.value

    beats = {'rock': 'scissors', 'scissors': 'paper', 'paper': 'rock'}
    names = {
        'rock': {'zh': '石头', 'en': 'Rock', 'ja': 'グー', 'fr': 'Pierre'},
        'scissors': {'zh': '剪刀', 'en': 'Scissors', 'ja': 'チョキ', 'fr': 'Ciseaux'},
        'paper': {'zh': '布', 'en': 'Paper', 'ja': 'パー', 'fr': 'Feuille'},
    }

    locale = str(interaction.locale)
    lang = 'zh' if locale.startswith('zh') else ('ja' if locale.startswith('ja') else ('fr' if locale.startswith('fr') else 'en'))
    user_name = names[user_choice][lang]
    bot_name = names[bot_choice][lang]

    if user_choice == bot_choice:
        result = 'draw'
        reward = 5
    elif beats[user_choice] == bot_choice:
        result = 'win'
        reward = 20
    else:
        result = 'lose'
        reward = 0

    if result == 'win':
        new_points = add_points(interaction.user.id, reward)
        if lang == 'zh':
            msg = f"你出了 **{user_name}**，Bot 出了 **{bot_name}**。\n🎉 你赢了！+**{reward}** ⭐ | 当前积分: **{new_points}** ⭐"
        elif lang == 'ja':
            msg = f"あなたは **{user_name}**、Bot は **{bot_name}**。\n🎉 勝ち！+**{reward}** ⭐ | 現在のポイント: **{new_points}** ⭐"
        elif lang == 'fr':
            msg = f"Tu as joué **{user_name}**, le Bot a joué **{bot_name}**。\n🎉 Victoire ! +**{reward}** ⭐ | Points actuels : **{new_points}** ⭐"
        else:
            msg = f"You played **{user_name}**, Bot played **{bot_name}**。\n🎉 You win! +**{reward}** ⭐ | Current points: **{new_points}** ⭐"
    elif result == 'draw':
        new_points = add_points(interaction.user.id, reward)
        if lang == 'zh':
            msg = f"你出了 **{user_name}**，Bot 也出了 **{bot_name}**。\n🤝 平局！+**{reward}** ⭐ | 当前积分: **{new_points}** ⭐"
        elif lang == 'ja':
            msg = f"あなたは **{user_name}**、Bot も **{bot_name}**。\n🤝 引き分け！+**{reward}** ⭐ | 現在のポイント: **{new_points}** ⭐"
        elif lang == 'fr':
            msg = f"Tu as joué **{user_name}**, le Bot a aussi joué **{bot_name}**。\n🤝 Égalité ! +**{reward}** ⭐ | Points actuels : **{new_points}** ⭐"
        else:
            msg = f"You played **{user_name}**, Bot also played **{bot_name}**。\n🤝 Draw! +**{reward}** ⭐ | Current points: **{new_points}** ⭐"
    else:
        if lang == 'zh':
            msg = f"你出了 **{user_name}**，Bot 出了 **{bot_name}**。\n😢 你输了！再接再厉！"
        elif lang == 'ja':
            msg = f"あなたは **{user_name}**、Bot は **{bot_name}**。\n😢 負けた！また挑戦してね！"
        elif lang == 'fr':
            msg = f"Tu as joué **{user_name}**, le Bot a joué **{bot_name}**。\n😢 Perdu ! Réessaie !"
        else:
            msg = f"You played **{user_name}**, Bot played **{bot_name}**。\n😢 You lose! Try again!"

    await interaction.response.send_message(msg, ephemeral=True)


active_guess_games = {}  # {user_id: target_number}

@app_commands.command(name="guess", description="猜数字游戏 / Number guessing game / 数字当て / Devinez le nombre")
@app_commands.describe(number="输入1-100之间的数字 / Enter 1-100 / 1-100を入力 / Entrez 1-100")
async def guess_slash(interaction: discord.Interaction, number: int):
    user_id = interaction.user.id
    locale = str(interaction.locale)
    lang = 'zh' if locale.startswith('zh') else ('ja' if locale.startswith('ja') else ('fr' if locale.startswith('fr') else 'en'))

    if number < 1 or number > 100:
        if lang == 'zh':
            msg = "❌ 数字必须在 **1-100** 之间！"
        elif lang == 'ja':
            msg = "❌ **1-100** の間で入力してください！"
        elif lang == 'fr':
            msg = "❌ Le nombre doit être entre **1 et 100** !"
        else:
            msg = "❌ Number must be between **1 and 100**!"
        await interaction.response.send_message(msg, ephemeral=True)
        return

    if user_id not in active_guess_games:
        active_guess_games[user_id] = random.randint(1, 100)
        target = active_guess_games[user_id]
        is_first = True
    else:
        target = active_guess_games[user_id]
        is_first = False

    if number == target:
        if is_first:
            reward = 100
            if lang == 'zh':
                msg = f"🎉 一次猜中！答案是 **{target}**！+**{reward}** ⭐"
            elif lang == 'ja':
                msg = f"🎉 一発正解！答えは **{target}**！+**{reward}** ⭐"
            elif lang == 'fr':
                msg = f"🎉 Du premier coup ! La réponse était **{target}** ! +**{reward}** ⭐"
            else:
                msg = f"🎉 First try! The answer was **{target}**! +**{reward}** ⭐"
        else:
            reward = 50
            if lang == 'zh':
                msg = f"🎉 猜对了！答案是 **{target}**！+**{reward}** ⭐"
            elif lang == 'ja':
                msg = f"🎉 正解！答えは **{target}**！+**{reward}** ⭐"
            elif lang == 'fr':
                msg = f"🎉 Correct ! La réponse était **{target}** ! +**{reward}** ⭐"
            else:
                msg = f"🎉 Correct! The answer was **{target}**! +**{reward}** ⭐"
        new_points = add_points(user_id, reward)
        msg += f" | 当前积分: **{new_points}** ⭐"
        del active_guess_games[user_id]
    elif number < target:
        if lang == 'zh':
            msg = f"📈 **{number}** 太小了！再大一点！"
        elif lang == 'ja':
            msg = f"📈 **{number}** は小さいです！もっと大きく！"
        elif lang == 'fr':
            msg = f"📈 **{number}** est trop petit ! Plus grand !"
        else:
            msg = f"📈 **{number}** is too small! Go higher!"
    else:
        if lang == 'zh':
            msg = f"📉 **{number}** 太大了！再小一点！"
        elif lang == 'ja':
            msg = f"📉 **{number}** は大きいです！もっと小さく！"
        elif lang == 'fr':
            msg = f"📉 **{number}** est trop grand ! Plus petit !"
        else:
            msg = f"📉 **{number}** is too big! Go lower!"

    await interaction.response.send_message(msg, ephemeral=True)


@app_commands.command(name="dice", description="掷骰子 / Roll dice / サイコロ / Lancer les dés")
async def dice_slash(interaction: discord.Interaction):
    user_roll = random.randint(1, 6)
    bot_roll = random.randint(1, 6)
    user_id = interaction.user.id
    locale = str(interaction.locale)
    lang = 'zh' if locale.startswith('zh') else ('ja' if locale.startswith('ja') else ('fr' if locale.startswith('fr') else 'en'))

    if user_roll > bot_roll:
        reward = 20
        new_points = add_points(user_id, reward)
        if lang == 'zh':
            msg = f"🎲 你掷出了 **{user_roll}**，Bot 掷出了 **{bot_roll}**。\n🎉 你赢了！+**{reward}** ⭐ | 当前积分: **{new_points}** ⭐"
        elif lang == 'ja':
            msg = f"🎲 あなたは **{user_roll}**、Bot は **{bot_roll}**。\n🎉 勝ち！+**{reward}** ⭐ | 現在のポイント: **{new_points}** ⭐"
        elif lang == 'fr':
            msg = f"🎲 Tu as fait **{user_roll}**, le Bot a fait **{bot_roll}**。\n🎉 Victoire ! +**{reward}** ⭐ | Points actuels : **{new_points}** ⭐"
        else:
            msg = f"🎲 You rolled **{user_roll}**, Bot rolled **{bot_roll}**。\n🎉 You win! +**{reward}** ⭐ | Current points: **{new_points}** ⭐"
    elif user_roll < bot_roll:
        if lang == 'zh':
            msg = f"🎲 你掷出了 **{user_roll}**，Bot 掷出了 **{bot_roll}**。\n😢 你输了！再接再厉！"
        elif lang == 'ja':
            msg = f"🎲 あなたは **{user_roll}**、Bot は **{bot_roll}**。\n😢 負けた！また挑戦してね！"
        elif lang == 'fr':
            msg = f"🎲 Tu as fait **{user_roll}**, le Bot a fait **{bot_roll}**。\n😢 Perdu ! Réessaie !"
        else:
            msg = f"🎲 You rolled **{user_roll}**, Bot rolled **{bot_roll}**。\n😢 You lose! Try again!"
    else:
        reward = 5
        new_points = add_points(user_id, reward)
        if lang == 'zh':
            msg = f"🎲 你掷出了 **{user_roll}**，Bot 也掷出了 **{bot_roll}**。\n🤝 平局！+**{reward}** ⭐ | 当前积分: **{new_points}** ⭐"
        elif lang == 'ja':
            msg = f"🎲 あなたは **{user_roll}**、Bot も **{bot_roll}**。\n🤝 引き分け！+**{reward}** ⭐ | 現在のポイント: **{new_points}** ⭐"
        elif lang == 'fr':
            msg = f"🎲 Tu as fait **{user_roll}**, le Bot a aussi fait **{bot_roll}**。\n🤝 Égalité ! +**{reward}** ⭐ | Points actuels : **{new_points}** ⭐"
        else:
            msg = f"🎲 You rolled **{user_roll}**, Bot also rolled **{bot_roll}**。\n🤝 Draw! +**{reward}** ⭐ | Current points: **{new_points}** ⭐"

    await interaction.response.send_message(msg, ephemeral=True)

@app_commands.command(name="battle", description="伪联机对战 / Pseudo PvP / 疑似オンライン対戦 / Combat pseudo-multijoueur")
@app_commands.describe(difficulty="选择难度 / Select difficulty")
@app_commands.choices(difficulty=[
    app_commands.Choice(name="简单 / Easy / 簡単 / Facile", value="easy"),
    app_commands.Choice(name="普通 / Normal / 普通 / Normal", value="normal"),
    app_commands.Choice(name="困难 / Hard / 難しい / Difficile", value="hard"),
])
async def battle_slash(interaction: discord.Interaction, difficulty: app_commands.Choice[str]):
    user_id = interaction.user.id
    user = get_or_create_user(user_id, interaction.user.name)
    user_level = user[5] if len(user) > 5 else 0

    locale = str(interaction.locale)
    lang = 'zh' if locale.startswith('zh') else ('ja' if locale.startswith('ja') else ('fr' if locale.startswith('fr') else 'en'))

    # 选择对手
    opp = random.choice(VIRTUAL_OPPONENTS)
    opp_level = random.randint(1, max(5, user_level + 5))

    # 难度调整
    diff_mod = {'easy': 0.7, 'normal': 1.0, 'hard': 1.4}
    mod = diff_mod.get(difficulty.value, 1.0)
    opp_power = int(opp['power'] * mod)

    # 对决：骰子 + 等级/战力加成 + 力量天赋
    power = get_talents(user_id)[0]
    player_roll = random.randint(1, 100) + (user_level * 2) + (power * 2)
    opp_roll = random.randint(1, 100) + opp_power

    if player_roll > opp_roll:
        result = 'win'
        base_reward = {'easy': 15, 'normal': 30, 'hard': 60}
        luck = get_talents(user_id)[1]
        reward = int(base_reward.get(difficulty.value, 30) * (1 + luck * 0.05))
        new_points = add_points(user_id, reward)
    elif player_roll < opp_roll:
        result = 'lose'
        reward = 0
        new_points = user[2]
    else:
        result = 'draw'
        reward = 5
        new_points = add_points(user_id, reward)

    # 构建 Embed
    if lang == 'zh':
        title = "⚔️ 伪联机对战"
        your_power = f"你的战力: {player_roll} (骰子 + Love等级加成)"
        opp_text = f"对手战力: {opp_roll} (骰子 + 对手强度)"
        diff_names = {'easy': '简单', 'normal': '普通', 'hard': '困难'}
    elif lang == 'ja':
        title = "⚔️ 疑似オンライン対戦"
        your_power = f"あなたの戦力: {player_roll} (ダイス + Loveレベルボーナス)"
        opp_text = f"相手の戦力: {opp_roll} (ダイス + 相手の強さ)"
        diff_names = {'easy': '簡単', 'normal': '普通', 'hard': '難しい'}
    elif lang == 'fr':
        title = "⚔️ Combat pseudo-multijoueur"
        your_power = f"Ta puissance : {player_roll} (dé + bonus niveau Love)"
        opp_text = f"Puissance adverse : {opp_roll} (dé + force adverse)"
        diff_names = {'easy': 'Facile', 'normal': 'Normal', 'hard': 'Difficile'}
    else:
        title = "⚔️ Pseudo PvP Battle"
        your_power = f"Your power: {player_roll} (dice + Love level bonus)"
        opp_text = f"Opponent power: {opp_roll} (dice + opponent strength)"
        diff_names = {'easy': 'Easy', 'normal': 'Normal', 'hard': 'Hard'}

    embed = discord.Embed(title=title, color=discord.Color.red())
    embed.add_field(name=f"{interaction.user.display_name} (Lv.{user_level})", value=your_power, inline=True)
    embed.add_field(name=f"{opp['avatar']} {opp['name']} (Lv.{opp_level})", value=opp_text, inline=True)
    embed.add_field(name="Difficulty" if lang=='en' else ("難易度" if lang=='ja' else ("Difficulté" if lang=='fr' else "难度")), value=diff_names.get(difficulty.value, difficulty.value), inline=False)

    if result == 'win':
        if lang == 'zh':
            embed.add_field(name="🎉 结果", value=f"你赢了！+**{reward}** ⭐ | 当前积分: **{new_points}** ⭐", inline=False)
        elif lang == 'ja':
            embed.add_field(name="🎉 結果", value=f"勝ち！+**{reward}** ⭐ | 現在のポイント: **{new_points}** ⭐", inline=False)
        elif lang == 'fr':
            embed.add_field(name="🎉 Résultat", value=f"Victoire ! +**{reward}** ⭐ | Points actuels : **{new_points}** ⭐", inline=False)
        else:
            embed.add_field(name="🎉 Result", value=f"You win! +**{reward}** ⭐ | Current points: **{new_points}** ⭐", inline=False)
    elif result == 'lose':
        if lang == 'zh':
            embed.add_field(name="😢 结果", value="你输了！再接再厉！", inline=False)
        elif lang == 'ja':
            embed.add_field(name="😢 結果", value="負けた！また挑戦してね！", inline=False)
        elif lang == 'fr':
            embed.add_field(name="😢 Résultat", value="Perdu ! Réessaie !", inline=False)
        else:
            embed.add_field(name="😢 Result", value="You lose! Try again!", inline=False)
    else:
        if lang == 'zh':
            embed.add_field(name="🤝 结果", value=f"平局！+**{reward}** ⭐ | 当前积分: **{new_points}** ⭐", inline=False)
        elif lang == 'ja':
            embed.add_field(name="🤝 結果", value=f"引き分け！+**{reward}** ⭐ | 現在のポイント: **{new_points}** ⭐", inline=False)
        elif lang == 'fr':
            embed.add_field(name="🤝 Résultat", value=f"Égalité ! +**{reward}** ⭐ | Points actuels : **{new_points}** ⭐", inline=False)
        else:
            embed.add_field(name="🤝 Result", value=f"Draw! +**{reward}** ⭐ | Current points: **{new_points}** ⭐", inline=False)

    embed.set_footer(text="Tip: Higher Love level gives more bonus! | Love等级越高战力加成越大！")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@app_commands.command(name="battle2", description="与服务器成员对战 / Battle a server member / メンバー対戦 / Combattre un membre")
@app_commands.describe(member="选择对手 / Select opponent / 相手を選択 / Sélectionner adversaire")
async def battle2_slash(interaction: discord.Interaction, member: discord.Member):
    if member.bot:
        await interaction.response.send_message("❌ 不能和机器人对战！| Can't battle a bot! | Botと戦えません！| Pas de combat contre un bot !", ephemeral=True)
        return
    if member.id == interaction.user.id:
        await interaction.response.send_message("❌ 不能和自己对战！| Can't battle yourself! | 自分と戦えません！| Pas de combat contre toi-même !", ephemeral=True)
        return

    user_id = interaction.user.id
    user = get_or_create_user(user_id, interaction.user.name)
    opp_user = get_or_create_user(member.id, member.name)

    user_level = user[5] if len(user) > 5 else 0
    opp_level = opp_user[5] if len(opp_user) > 5 else 0
    user_power = get_talents(user_id)[0]
    opp_power = get_talents(member.id)[0]

    locale = str(interaction.locale)
    lang = 'zh' if locale.startswith('zh') else ('ja' if locale.startswith('ja') else ('fr' if locale.startswith('fr') else 'en'))

    player_roll = random.randint(1, 100) + (user_level * 2) + (user_power * 2)
    opp_roll = random.randint(1, 100) + (opp_level * 2) + (opp_power * 2)

    if player_roll > opp_roll:
        result = 'win'
        luck = get_talents(user_id)[1]
        reward = int(40 * (1 + luck * 0.05))
        new_points = add_points(user_id, reward)
    elif player_roll < opp_roll:
        result = 'lose'
        reward = 0
        new_points = user[2]
    else:
        result = 'draw'
        reward = 10
        new_points = add_points(user_id, reward)

    if lang == 'zh':
        title = "⚔️ 服务器成员对战"
    elif lang == 'ja':
        title = "⚔️ メンバー対戦"
    elif lang == 'fr':
        title = "⚔️ Combat membre"
    else:
        title = "⚔️ Member Battle"

    embed = discord.Embed(title=title, color=discord.Color.dark_red())
    embed.add_field(name=f"{interaction.user.display_name} (Lv.{user_level})", value=f"战力: {player_roll}", inline=True)
    embed.add_field(name=f"{member.display_name} (Lv.{opp_level})", value=f"战力: {opp_roll}", inline=True)

    if result == 'win':
        if lang == 'zh':
            embed.add_field(name="🎉 结果", value=f"你赢了！+**{reward}** ⭐ | 当前积分: **{new_points}** ⭐", inline=False)
        elif lang == 'ja':
            embed.add_field(name="🎉 結果", value=f"勝ち！+**{reward}** ⭐ | 現在のポイント: **{new_points}** ⭐", inline=False)
        elif lang == 'fr':
            embed.add_field(name="🎉 Résultat", value=f"Victoire ! +**{reward}** ⭐ | Points : **{new_points}** ⭐", inline=False)
        else:
            embed.add_field(name="🎉 Result", value=f"You win! +**{reward}** ⭐ | Points: **{new_points}** ⭐", inline=False)
    elif result == 'lose':
        if lang == 'zh':
            embed.add_field(name="😢 结果", value="你输了！再接再厉！", inline=False)
        elif lang == 'ja':
            embed.add_field(name="😢 結果", value="負けた！また挑戦してね！", inline=False)
        elif lang == 'fr':
            embed.add_field(name="😢 Résultat", value="Perdu ! Réessaie !", inline=False)
        else:
            embed.add_field(name="😢 Result", value="You lose! Try again!", inline=False)
    else:
        if lang == 'zh':
            embed.add_field(name="🤝 结果", value=f"平局！+**{reward}** ⭐ | 当前积分: **{new_points}** ⭐", inline=False)
        elif lang == 'ja':
            embed.add_field(name="🤝 結果", value=f"引き分け！+**{reward}** ⭐ | 現在のポイント: **{new_points}** ⭐", inline=False)
        elif lang == 'fr':
            embed.add_field(name="🤝 Résultat", value=f"Égalité ! +**{reward}** ⭐ | Points : **{new_points}** ⭐", inline=False)
        else:
            embed.add_field(name="🤝 Result", value=f"Draw! +**{reward}** ⭐ | Points: **{new_points}** ⭐", inline=False)

    embed.set_footer(text="Tip: Level up and upgrade talents to become stronger!")
    await interaction.response.send_message(embed=embed, ephemeral=True)

SLOT_SYMBOLS = ['🍒', '🍋', '🍇', '⭐', '💎', '7️⃣']
SLOT_WEIGHTS = [30, 25, 20, 15, 8, 2]

@app_commands.command(name="slot", description="🎰 摇奖机 / Slot Machine / スロット / Machine à sous")
async def slot_slash(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    user_id = interaction.user.id
    locale = str(interaction.locale)
    lang = 'zh' if locale.startswith('zh') else ('ja' if locale.startswith('ja') else ('fr' if locale.startswith('fr') else 'en'))

    # 动画效果
    msg = await interaction.followup.send("🎰 Spinning...", ephemeral=True)
    for _ in range(3):
        temp = ' | '.join(random.choices(SLOT_SYMBOLS, k=3))
        await msg.edit(content=f"🎰 [{temp}]")
        await asyncio.sleep(0.5)

    result = random.choices(SLOT_SYMBOLS, weights=SLOT_WEIGHTS, k=3)
    display = ' | '.join(result)

    # 判定奖励
    if result[0] == result[1] == result[2]:
        if result[0] == '7️⃣':
            reward = 200
        elif result[0] == '💎':
            reward = 100
        elif result[0] == '⭐':
            reward = 50
        else:
            reward = 30
        luck = get_talents(user_id)[1]
        reward = int(reward * (1 + luck * 0.05))
        new_points = add_points(user_id, reward)
        if lang == 'zh':
            text = f"🎰 [{display}]\n🎉 JACKPOT！+**{reward}** ⭐ | 当前: **{new_points}** ⭐"
        elif lang == 'ja':
            text = f"🎰 [{display}]\n🎉 ジャックポット！+**{reward}** ⭐ | 現在: **{new_points}** ⭐"
        elif lang == 'fr':
            text = f"🎰 [{display}]\n🎉 JACKPOT ! +**{reward}** ⭐ | Actuel : **{new_points}** ⭐"
        else:
            text = f"🎰 [{display}]\n🎉 JACKPOT! +**{reward}** ⭐ | Current: **{new_points}** ⭐"
    elif result[0] == result[1] or result[1] == result[2] or result[0] == result[2]:
        reward = 10
        luck = get_talents(user_id)[1]
        reward = int(reward * (1 + luck * 0.05))
        new_points = add_points(user_id, reward)
        if lang == 'zh':
            text = f"🎰 [{display}]\n✨ 匹配2个！+**{reward}** ⭐ | 当前: **{new_points}** ⭐"
        elif lang == 'ja':
            text = f"🎰 [{display}]\n✨ 2つマッチ！+**{reward}** ⭐ | 現在: **{new_points}** ⭐"
        elif lang == 'fr':
            text = f"🎰 [{display}]\n✨ 2 identiques ! +**{reward}** ⭐ | Actuel : **{new_points}** ⭐"
        else:
            text = f"🎰 [{display}]\n✨ 2 match! +**{reward}** ⭐ | Current: **{new_points}** ⭐"
    else:
        if lang == 'zh':
            text = f"🎰 [{display}]\n😢 没有匹配，再接再厉！"
        elif lang == 'ja':
            text = f"🎰 [{display}]\n😢 マッチなし、また挑戦してね！"
        elif lang == 'fr':
            text = f"🎰 [{display}]\n😢 Pas de match, réessaie !"
        else:
            text = f"🎰 [{display}]\n😢 No match, try again!"

    await msg.edit(content=text)


IDIOM_LIST = [
    "一心一意","意气风发","发扬光大","大公无私","私心杂念",
    "念念不忘","忘恩负义","义不容辞","辞旧迎新","新陈代谢",
    "谢天谢地","地久天长","长驱直入","入木三分","分秒必争",
    "争分夺秒","秒不可言","言简意赅","赅博渊深","深入浅出",
    "出生入死","死而复生","生龙活虎","虎头蛇尾","尾大不掉",
    "掉以轻心","心直口快","快马加鞭","鞭长莫及","及锋而试",
    "试才录用","用武之地","地久天长","长年累月","月明星稀",
    "稀世之宝","宝刀不老","老马识途","途穷日暮","暮气沉沉",
    "沉鱼落雁","雁过留声","声东击西","西装革履","履霜坚冰",
    "冰清玉洁","洁身自好","好高骛远","远走高飞","飞黄腾达",
    "达官贵人","人杰地灵","灵丹妙药","药到病除","除暴安良",
    "良辰美景","景星庆云","云开见日","日新月异","异口同声",
    "声嘶力竭","竭尽全力","力争上游","游刃有余","余音绕梁",
    "梁上君子","子虚乌有","有目共睹","睹物思人","人面兽心",
    "心花怒放","放虎归山","山穷水尽","尽善尽美","美中不足",
    "足智多谋","谋事在人","人山人海","海阔天空","空前绝后",
    "后发制人","人声鼎沸","沸沸扬扬","扬眉吐气","气吞山河",
    "河清海晏","晏然自若","若隐若现","现身说法","法外施恩",
    "恩重如山","山清水秀","秀外慧中","中流砥柱","柱石之臣",
]

# 建立首尾索引
idiom_by_first = {}
for idiom in IDIOM_LIST:
    first = idiom[0]
    if first not in idiom_by_first:
        idiom_by_first[first] = []
    idiom_by_first[first].append(idiom)

active_idiom_games = {}  # {channel_id: {'last': 成语, 'used': set()}}

@app_commands.command(name="idiom", description="成语接龙 / Chinese Idiom Chain / 四字熟語")
async def idiom_slash(interaction: discord.Interaction, idiom: str = None):
    await interaction.response.defer(ephemeral=True)
    channel_id = interaction.channel_id
    locale = str(interaction.locale)
    lang = 'zh' if locale.startswith('zh') else ('ja' if locale.startswith('ja') else ('fr' if locale.startswith('fr') else 'en'))

    if idiom:
        # 玩家接龙
        if channel_id not in active_idiom_games:
            if lang == 'zh':
                await interaction.followup.send("❌ 当前频道没有进行中的成语接龙！发送 `/idiom` 开始新游戏。", ephemeral=True)
            else:
                await interaction.followup.send("❌ No active idiom chain! Use `/idiom` to start.", ephemeral=True)
            return

        game = active_idiom_games[channel_id]
        last = game['last']
        used = game['used']

        # 检查是否是4个字
        if len(idiom) != 4:
            if lang == 'zh':
                await interaction.followup.send("❌ 请输入一个 **4字成语**！", ephemeral=True)
            else:
                await interaction.followup.send("❌ Please enter a **4-character idiom**!", ephemeral=True)
            return

        # 检查首字是否匹配
        if idiom[0] != last[-1]:
            if lang == 'zh':
                await interaction.followup.send(f"❌ 成语必须以 **{last[-1]}** 开头！上一个成语是：**{last}**", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ Idiom must start with **{last[-1]}**! Last: **{last}**", ephemeral=True)
            return

        # 检查是否已用过
        if idiom in used:
            if lang == 'zh':
                await interaction.followup.send("❌ 这个成语已经用过了！", ephemeral=True)
            else:
                await interaction.followup.send("❌ This idiom has already been used!", ephemeral=True)
            return

        # 检查是否在成语库中（简化：允许不在库中的，只要符合规则）
        used.add(idiom)

        # Bot 接下一个
        next_first = idiom[-1]
        candidates = [i for i in idiom_by_first.get(next_first, []) if i not in used]

        if candidates:
            bot_idiom = random.choice(candidates)
            used.add(bot_idiom)
            game['last'] = bot_idiom
            if lang == 'zh':
                await interaction.followup.send(
                    f"✅ **{interaction.user.display_name}**: {idiom}\n"
                    f"🤖 **Bot**: {bot_idiom}\n"
                    f"📌 请接以 **{bot_idiom[-1]}** 开头的成语！",
                    ephemeral=False
                )
            else:
                await interaction.followup.send(
                    f"✅ **{interaction.user.display_name}**: {idiom}\n"
                    f"🤖 **Bot**: {bot_idiom}\n"
                    f"📌 Next idiom must start with **{bot_idiom[-1]}**!",
                    ephemeral=False
                )
        else:
            # Bot 接不上，玩家获胜
            reward = 30
            luck = get_talents(interaction.user.id)[1]
            reward = int(reward * (1 + luck * 0.05))
            new_points = add_points(interaction.user.id, reward)
            del active_idiom_games[channel_id]
            if lang == 'zh':
                await interaction.followup.send(
                    f"🎉 **{interaction.user.display_name}** 获胜！Bot 接不上来了！\n"
                    f"+**{reward}** ⭐ | 当前积分: **{new_points}** ⭐",
                    ephemeral=False
                )
            else:
                await interaction.followup.send(
                    f"🎉 **{interaction.user.display_name}** wins! Bot can't continue!\n"
                    f"+**{reward}** ⭐ | Points: **{new_points}** ⭐",
                    ephemeral=False
                )
    else:
        # 开始新游戏
        start = random.choice(IDIOM_LIST)
        active_idiom_games[channel_id] = {'last': start, 'used': {start}}
        if lang == 'zh':
            await interaction.followup.send(
                f"🎮 成语接龙开始！\n"
                f"🤖 **Bot**: {start}\n"
                f"📌 请接以 **{start[-1]}** 开头的成语！使用 `/idiom 你的成语`",
                ephemeral=False
            )
        else:
            await interaction.followup.send(
                f"🎮 Idiom chain started!\n"
                f"🤖 **Bot**: {start}\n"
                f"📌 Next idiom must start with **{start[-1]}**! Use `/idiom your_idiom`",
                ephemeral=False
            )


MINESWEEPER_GAMES = {}  # {channel_id: MinesweeperGame}

class MinesweeperGame:
    def __init__(self, size=5, mines=5):
        self.size = size
        self.mines = mines
        self.board = [[0 for _ in range(size)] for _ in range(size)]
        self.revealed = [[False for _ in range(size)] for _ in range(size)]
        self.flagged = [[False for _ in range(size)] for _ in range(size)]
        self.game_over = False
        self.won = False
        self._place_mines()
        self._calc_numbers()

    def _place_mines(self):
        positions = random.sample(range(self.size * self.size), self.mines)
        for pos in positions:
            r, c = divmod(pos, self.size)
            self.board[r][c] = -1

    def _calc_numbers(self):
        for r in range(self.size):
            for c in range(self.size):
                if self.board[r][c] == -1:
                    continue
                count = 0
                for dr in [-1, 0, 1]:
                    for dc in [-1, 0, 1]:
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < self.size and 0 <= nc < self.size and self.board[nr][nc] == -1:
                            count += 1
                self.board[r][c] = count

    def reveal(self, r, c):
        if self.revealed[r][c] or self.flagged[r][c]:
            return None
        self.revealed[r][c] = True
        if self.board[r][c] == -1:
            self.game_over = True
            return 'mine'
        if self.board[r][c] == 0:
            # 自动揭开周围
            for dr in [-1, 0, 1]:
                for dc in [-1, 0, 1]:
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < self.size and 0 <= nc < self.size and not self.revealed[nr][nc]:
                        self.reveal(nr, nc)
        # 检查胜利
        revealed_count = sum(sum(1 for c in row if c) for row in self.revealed)
        if revealed_count == self.size * self.size - self.mines:
            self.game_over = True
            self.won = True
        return 'safe'

    def toggle_flag(self, r, c):
        if not self.revealed[r][c]:
            self.flagged[r][c] = not self.flagged[r][c]

    def to_embed(self, lang='zh'):
        if lang == 'zh':
            title = "💣 扫雷"
            desc = "点击按钮揭开方块！避开地雷！"
        elif lang == 'ja':
            title = "💣 マインスイーパー"
            desc = "ボタンをクリックして開こう！地雷を避けて！"
        elif lang == 'fr':
            title = "💣 Démineur"
            desc = "Clique pour révéler ! Évite les mines !"
        else:
            title = "💣 Minesweeper"
            desc = "Click to reveal! Avoid mines!"

        embed = discord.Embed(title=title, description=desc, color=discord.Color.dark_green())
        # 用文本表示当前状态
        grid = []
        for r in range(self.size):
            row = []
            for c in range(self.size):
                if self.revealed[r][c]:
                    if self.board[r][c] == -1:
                        row.append('💥')
                    elif self.board[r][c] == 0:
                        row.append('⬜')
                    else:
                        row.append(str(self.board[r][c]))
                elif self.flagged[r][c]:
                    row.append('🚩')
                else:
                    row.append('⬛')
            grid.append(' '.join(row))
        embed.add_field(name="Grid", value='```\n' + '\n'.join(grid) + '\n```', inline=False)
        return embed


class MinesweeperView(discord.ui.View):
    def __init__(self, game, channel_id, lang):
        super().__init__(timeout=300)
        self.game = game
        self.channel_id = channel_id
        self.lang = lang
        self._build_buttons()

    def _build_buttons(self):
        for r in range(self.game.size):
            row_buttons = []
            for c in range(self.game.size):
                btn = discord.ui.Button(
                    label=f"{r},{c}",
                    style=discord.ButtonStyle.secondary,
                    custom_id=f"ms_{r}_{c}",
                    row=r
                )
                btn.callback = self._make_callback(r, c)
                self.add_item(btn)

    def _make_callback(self, r, c):
        async def callback(interaction: discord.Interaction):
            if self.game.game_over:
                await interaction.response.send_message("❌ Game over! | 游戏已结束！", ephemeral=True)
                return

            result = self.game.reveal(r, c)
            if result == 'mine':
                embed = self.game.to_embed(self.lang)
                if self.lang == 'zh':
                    embed.add_field(name="💥", value="你踩到地雷了！游戏结束！", inline=False)
                elif self.lang == 'ja':
                    embed.add_field(name="💥", value="地雷を踏んだ！ゲームオーバー！", inline=False)
                elif self.lang == 'fr':
                    embed.add_field(name="💥", value="Tu as touché une mine ! Fin du jeu !", inline=False)
                else:
                    embed.add_field(name="💥", value="You hit a mine! Game over!", inline=False)
                await interaction.response.edit_message(embed=embed, view=None)
                if self.channel_id in MINESWEEPER_GAMES:
                    del MINESWEEPER_GAMES[self.channel_id]
            elif self.game.won:
                reward = 50
                luck = get_talents(interaction.user.id)[1]
                reward = int(reward * (1 + luck * 0.05))
                new_points = add_points(interaction.user.id, reward)
                embed = self.game.to_embed(self.lang)
                if self.lang == 'zh':
                    embed.add_field(name="🎉", value=f"恭喜通关！+**{reward}** ⭐ | 当前: **{new_points}** ⭐", inline=False)
                elif self.lang == 'ja':
                    embed.add_field(name="🎉", value=f"クリア！+**{reward}** ⭐ | 現在: **{new_points}** ⭐", inline=False)
                elif self.lang == 'fr':
                    embed.add_field(name="🎉", value=f"Terminé ! +**{reward}** ⭐ | Actuel : **{new_points}** ⭐", inline=False)
                else:
                    embed.add_field(name="🎉", value=f"Cleared! +**{reward}** ⭐ | Current: **{new_points}** ⭐", inline=False)
                await interaction.response.edit_message(embed=embed, view=None)
                if self.channel_id in MINESWEEPER_GAMES:
                    del MINESWEEPER_GAMES[self.channel_id]
            else:
                embed = self.game.to_embed(self.lang)
                await interaction.response.edit_message(embed=embed, view=self)
        return callback


@app_commands.command(name="minesweeper", description="💣 扫雷 / Minesweeper / マインスイーパー / Démineur")
async def minesweeper_slash(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=False)
    channel_id = interaction.channel_id
    locale = str(interaction.locale)
    lang = 'zh' if locale.startswith('zh') else ('ja' if locale.startswith('ja') else ('fr' if locale.startswith('fr') else 'en'))

    if channel_id in MINESWEEPER_GAMES:
        msg = "❌ 当前频道已有扫雷游戏！| Minesweeper already in progress! | このチャンネルには既にマインスイーパーがある！| Une partie de Démineur est déjà en cours !"
        await interaction.followup.send(msg, ephemeral=True)
        return

    game = MinesweeperGame(size=5, mines=5)
    MINESWEEPER_GAMES[channel_id] = game
    embed = game.to_embed(lang)
    view = MinesweeperView(game, channel_id, lang)
    await interaction.followup.send(embed=embed, view=view)


async def setup(bot):
    # 注册模块级 app commands
    module = sys.modules[__name__]
    for obj in vars(module).values():
        if isinstance(obj, app_commands.Command):
            bot.tree.add_command(obj)
    await bot.add_cog(GamesCog(bot))
