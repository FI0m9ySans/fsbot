# -*- coding: utf-8 -*-
import sys

with open('D:/FSBot/main.py', 'r', encoding='utf-8') as f:
    content = f.read()

start_marker = '@bot.tree.command(name="quoridor"'
end_marker = '\nbot.run('

start_idx = content.find(start_marker)
end_idx = content.find(end_marker)

if start_idx == -1 or end_idx == -1:
    print('ERROR: Could not find markers')
    sys.exit(1)

new_code = r'''# ---- 路墙棋 FakeMember (AI用) ----
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


@bot.tree.command(name="quoridor", description="\U0001f9f1 \u8def\u5899\u68cb / Quoridor / \u58c1\u5c06\u68cb")
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
        # ===== AI \u5bf9\u6218 =====
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
        # ===== \u6307\u5b9a\u5bf9\u624b =====
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
        # ===== 4\u4eba\u968f\u673a\u5339\u914d =====
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
        # ===== 4\u4eba\u6307\u5b9a =====
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
        # ===== \u81ea\u5b9a\u4e49\u89c4\u5219 (\u53ef\u6307\u5b9a\u5bf9\u624b\u6216AI, \u53ef\u8bbe\u7f6e\u68cb\u76d8/\u5899\u6570/\u81ea\u5b9a\u4e49\u5899) =====
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
        # ===== \u9ed8\u8ba4: \u53cc\u4eba\u968f\u673a\u5339\u914d =====
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


'''

new_content = content[:start_idx] + new_code + content[end_idx:]

with open('D:/FSBot/main.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print('Replacement successful!')
print(f'Old section: {end_idx - start_idx} chars')
print(f'New section: {len(new_code)} chars')
