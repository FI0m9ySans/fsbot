"""
FSBot 棋牌游戏模块
包含: 重力四子棋、五子棋、围棋、跳棋、斗兽棋、飞行棋、中国象棋、国际象棋
"""
import discord
import asyncio
import random
import re
import copy

# ═══════════════════════════════════════
#  全局状态
# ═══════════════════════════════════════

active_games = {}  # {channel_id: game_view}

# ═══════════════════════════════════════
#  辅助函数
# ═══════════════════════════════════════

def parse_pos(s):
    """'A1' -> (row=0, col=0)  row=0 是底部"""
    s = s.strip().upper()
    if len(s) < 2 or not s[0].isalpha() or not s[1:].isdigit():
        return None
    col = ord(s[0]) - 65
    row = int(s[1:]) - 1
    if col < 0 or row < 0:
        return None
    return (row, col)

def parse_move(s):
    """'B3-C4' -> ((2,1),(3,3))"""
    s = s.strip().upper().replace(' ', '').replace('→', '-').replace(',', '-')
    # 支持 e2e4 格式
    if len(s) == 4 and s[0].isalpha() and s[1].isdigit() and s[2].isalpha() and s[3].isdigit():
        f = parse_pos(s[:2])
        t = parse_pos(s[2:])
        if f and t:
            return (f, t)
    parts = s.split('-')
    if len(parts) == 2:
        f = parse_pos(parts[0])
        t = parse_pos(parts[1])
        if f and t:
            return (f, t)
    return None

def progress_bar(pos, total=50, width=15):
    filled = int(pos / total * width) if total > 0 else 0
    return '█' * filled + '░' * (width - filled)

# ═══════════════════════════════════════
#  挑战视图
# ═══════════════════════════════════════

class ChallengeView(discord.ui.View):
    def __init__(self, challenger, opponent, game_name, start_cb):
        super().__init__(timeout=60)
        self.challenger = challenger
        self.opponent = opponent
        self.game_name = game_name
        self.start_cb = start_cb

    @discord.ui.button(label="接受挑战", style=discord.ButtonStyle.success, emoji="✅")
    async def accept(self, interaction, button):
        if interaction.user.id != self.opponent.id:
            await interaction.response.send_message("只有被挑战者才能接受！", ephemeral=True)
            return
        for c in self.children:
            c.disabled = True
        await interaction.response.edit_message(view=self)
        await self.start_cb(interaction)

    @discord.ui.button(label="拒绝", style=discord.ButtonStyle.danger, emoji="❌")
    async def decline(self, interaction, button):
        if interaction.user.id != self.opponent.id:
            await interaction.response.send_message("只有被挑战者才能拒绝！", ephemeral=True)
            return
        for c in self.children:
            c.disabled = True
        await interaction.response.edit_message(
            content=f"❌ {self.opponent.display_name} 拒绝了 {self.game_name} 挑战。", embed=None, view=self)

    async def on_timeout(self):
        for c in self.children:
            c.disabled = True

# ═══════════════════════════════════════
#  通用走棋弹窗 & 视图
# ═══════════════════════════════════════

class MoveModal(discord.ui.Modal):
    def __init__(self, game, view_ref):
        super().__init__(title=f"走棋 - {game.GAME_NAME}")
        self.game = game
        self.view_ref = view_ref
        self.move_input = discord.ui.TextInput(
            label="输入走法", placeholder=game.MOVE_HINT, required=True, max_length=30)
        self.add_item(self.move_input)

    async def on_submit(self, interaction):
        move_str = self.move_input.value.strip()
        success, err = self.game.make_move(move_str)
        if not success:
            await interaction.response.send_message(f"无效走法: {err}", ephemeral=True)
            return
        self.game.check_winner()
        if self.game.winner:
            await self.view_ref.end_game(interaction)
        else:
            self.game.switch()
            await interaction.response.edit_message(embed=self.game.get_embed(), view=self.view_ref)

class GameView(discord.ui.View):
    """通用游戏视图（走棋按钮 + 认输按钮）"""
    def __init__(self, game, channel, points_cb=None):
        super().__init__(timeout=300)
        self.game = game
        self.channel = channel
        self.points_cb = points_cb
        self.message = None

    @discord.ui.button(label="走棋", style=discord.ButtonStyle.primary, emoji="📥")
    async def move_btn(self, interaction, button):
        if interaction.user.id != self.game.current.id:
            await interaction.response.send_message("还没轮到你！", ephemeral=True)
            return
        await interaction.response.send_modal(MoveModal(self.game, self))

    @discord.ui.button(label="认输", style=discord.ButtonStyle.danger, emoji="🏳️")
    async def resign_btn(self, interaction, button):
        if interaction.user.id not in (self.game.p1.id, self.game.p2.id):
            await interaction.response.send_message("你不是本局玩家！", ephemeral=True)
            return
        self.game.winner = self.game.p2 if interaction.user.id == self.game.p1.id else self.game.p1
        await self.end_game(interaction)

    async def end_game(self, interaction):
        for c in self.children:
            c.disabled = True
        embed = self.game.get_embed()
        try:
            if interaction.response.is_done():
                await interaction.followup.edit_message(self.message.id, embed=embed, view=self)
            else:
                await interaction.response.edit_message(embed=embed, view=self)
        except:
            pass
        if self.points_cb and self.game.winner and self.game.winner != "draw":
            await self.points_cb(self.game.winner.id)
        if self.channel.id in active_games:
            del active_games[self.channel.id]

    async def on_timeout(self):
        for c in self.children:
            c.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except:
                pass
        if self.channel.id in active_games:
            del active_games[self.channel.id]


# ═══════════════════════════════════════
#  1. 重力四子棋 (Connect Four)
# ═══════════════════════════════════════

class Connect4Game:
    GAME_NAME = "重力四子棋"
    MOVE_HINT = "点击下方列按钮"
    COLS = 7
    ROWS = 6

    def __init__(self, p1, p2):
        self.p1 = p1
        self.p2 = p2
        self.current = p1
        self.winner = None
        self.board = [[0]*self.COLS for _ in range(self.ROWS)]

    def switch(self):
        self.current = self.p2 if self.current == self.p1 else self.p1

    def drop_piece(self, col):
        col -= 1
        if col < 0 or col >= self.COLS:
            return False, "列号 1-7"
        for r in range(self.ROWS):
            if self.board[r][col] == 0:
                player = 1 if self.current == self.p1 else 2
                self.board[r][col] = player
                return True, ""
        return False, "该列已满"

    def make_move(self, move_str):
        try:
            col = int(move_str.strip())
        except ValueError:
            return False, "请输入列号 1-7"
        return self.drop_piece(col)

    def check_winner(self):
        for r in range(self.ROWS):
            for c in range(self.COLS):
                p = self.board[r][c]
                if p == 0:
                    continue
                for dr, dc in [(0,1),(1,0),(1,1),(1,-1)]:
                    if 0 <= r+3*dr < self.ROWS and 0 <= c+3*dc < self.COLS:
                        if all(self.board[r+i*dr][c+i*dc] == p for i in range(4)):
                            self.winner = self.p1 if p == 1 else self.p2
                            return
        if all(self.board[r][c] != 0 for r in range(self.ROWS) for c in range(self.COLS)):
            self.winner = "draw"

    def get_board_str(self):
        pieces = {0: '⚪', 1: '🔴', 2: '🟡'}
        header = ' '.join(str(i+1) for i in range(self.COLS))
        lines = [header]
        for r in range(self.ROWS-1, -1, -1):
            lines.append(' '.join(pieces[self.board[r][c]] for c in range(self.COLS)))
        return '```\n' + '\n'.join(lines) + '\n```'

    def get_embed(self):
        embed = discord.Embed(title="🔴🟡 重力四子棋", color=discord.Color.blue())
        if self.winner:
            if self.winner == "draw":
                embed.description = f"**平局！**\n\n{self.get_board_str()}"
            else:
                embed.description = f"🏆 **{self.winner.display_name}** 获胜！\n\n{self.get_board_str()}"
            embed.color = discord.Color.gold()
        else:
            sym = "🔴" if self.current == self.p1 else "🟡"
            embed.description = f"{sym} **{self.current.display_name}** 的回合 — 选择列号\n\n{self.get_board_str()}"
        embed.add_field(name="对战", value=f"🔴 {self.p1.display_name} vs 🟡 {self.p2.display_name}")
        return embed


class Connect4View(discord.ui.View):
    def __init__(self, game, channel, points_cb=None):
        super().__init__(timeout=300)
        self.game = game
        self.channel = channel
        self.points_cb = points_cb
        self.message = None
        for i in range(7):
            btn = discord.ui.Button(label=str(i+1), style=discord.ButtonStyle.primary, row=i//5)
            btn.callback = self._make_col_cb(i+1)
            self.add_item(btn)
        resign = discord.ui.Button(label="认输", style=discord.ButtonStyle.danger, row=1, emoji="🏳️")
        resign.callback = self._resign_cb
        self.add_item(resign)

    def _make_col_cb(self, col):
        async def cb(interaction):
            if interaction.user.id != self.game.current.id:
                await interaction.response.send_message("还没轮到你！", ephemeral=True)
                return
            success, err = self.game.drop_piece(col)
            if not success:
                await interaction.response.send_message(f"无效: {err}", ephemeral=True)
                return
            self.game.check_winner()
            if self.game.winner:
                await self._end(interaction)
            else:
                self.game.switch()
                await interaction.response.edit_message(embed=self.game.get_embed(), view=self)
        return cb

    async def _resign_cb(self, interaction):
        if interaction.user.id not in (self.game.p1.id, self.game.p2.id):
            await interaction.response.send_message("你不是本局玩家！", ephemeral=True)
            return
        self.game.winner = self.game.p2 if interaction.user.id == self.game.p1.id else self.game.p1
        await self._end(interaction)

    async def _end(self, interaction):
        for c in self.children:
            c.disabled = True
        embed = self.game.get_embed()
        try:
            await interaction.response.edit_message(embed=embed, view=self)
        except:
            pass
        if self.points_cb and self.game.winner and self.game.winner != "draw":
            await self.points_cb(self.game.winner.id)
        if self.channel.id in active_games:
            del active_games[self.channel.id]

    async def on_timeout(self):
        for c in self.children:
            c.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except:
                pass
        if self.channel.id in active_games:
            del active_games[self.channel.id]


# ═══════════════════════════════════════
#  2. 五子棋 (Gomoku)
# ═══════════════════════════════════════

class GomokuGame:
    GAME_NAME = "五子棋"
    MOVE_HINT = "输入坐标，如 H8"
    SIZE = 15

    def __init__(self, p1, p2):
        self.p1 = p1
        self.p2 = p2
        self.current = p1  # p1=黑, p2=白
        self.winner = None
        self.board = [[0]*self.SIZE for _ in range(self.SIZE)]
        self.last_move = None

    def switch(self):
        self.current = self.p2 if self.current == self.p1 else self.p1

    def make_move(self, move_str):
        pos = parse_pos(move_str)
        if pos is None:
            return False, "格式: 如 H8"
        r, c = pos
        if r >= self.SIZE or c >= self.SIZE:
            return False, f"坐标超出范围 (A1-{chr(64+self.SIZE)}{self.SIZE})"
        if self.board[r][c] != 0:
            return False, "该位置已有棋子"
        player = 1 if self.current == self.p1 else 2
        self.board[r][c] = player
        self.last_move = (r, c)
        return True, ""

    def check_winner(self):
        if self.last_move is None:
            return
        r, c = self.last_move
        p = self.board[r][c]
        for dr, dc in [(0,1),(1,0),(1,1),(1,-1)]:
            count = 1
            for d in [1, -1]:
                nr, nc = r+dr*d, c+dc*d
                while 0 <= nr < self.SIZE and 0 <= nc < self.SIZE and self.board[nr][nc] == p:
                    count += 1
                    nr += dr*d
                    nc += dc*d
            if count >= 5:
                self.winner = self.p1 if p == 1 else self.p2
                return

    def get_board_str(self):
        # 紧凑显示: ●黑 ○白 ·空 ▲最后一步
        cols_label = '   ' + ' '.join(chr(65+i) for i in range(self.SIZE))
        lines = [cols_label]
        for r in range(self.SIZE-1, -1, -1):
            row_str = f"{r+1:>2} "
            for c in range(self.SIZE):
                if self.last_move and (r, c) == self.last_move:
                    v = '▲' if self.board[r][c] == 1 else '△'
                elif self.board[r][c] == 0:
                    v = '·'
                elif self.board[r][c] == 1:
                    v = '●'
                else:
                    v = '○'
                row_str += v + ' '
            lines.append(row_str)
        return '```\n' + '\n'.join(lines) + '\n```'

    def get_embed(self):
        embed = discord.Embed(title="●○ 五子棋", color=discord.Color.dark_green())
        if self.winner:
            embed.description = f"🏆 **{self.winner.display_name}** 获胜！\n\n{self.get_board_str()}"
            embed.color = discord.Color.gold()
        else:
            sym = "●" if self.current == self.p1 else "○"
            embed.description = f"{sym} **{self.current.display_name}** 的回合\n\n{self.get_board_str()}"
        embed.add_field(name="对战", value=f"● {self.p1.display_name} (黑) vs ○ {self.p2.display_name} (白)")
        return embed


# ═══════════════════════════════════════
#  3. 围棋 (Go)
# ═══════════════════════════════════════

class GoGame:
    GAME_NAME = "围棋"
    MOVE_HINT = "输入坐标如 H8，或输入 pass 虚手"
    SIZE = 9

    def __init__(self, p1, p2):
        self.p1 = p1
        self.p2 = p2
        self.current = p1  # p1=黑, p2=白
        self.winner = None
        self.board = [[0]*self.SIZE for _ in range(self.SIZE)]
        self.captures = {1: 0, 2: 0}  # 提子数
        self.passes = 0
        self.last_board = None  # 用于劫判
        self.last_move = None

    def switch(self):
        self.current = self.p2 if self.current == self.p1 else self.p1

    def _get_group(self, r, c, color):
        visited = set()
        stack = [(r, c)]
        while stack:
            cr, cc = stack.pop()
            if (cr, cc) in visited:
                continue
            if cr < 0 or cr >= self.SIZE or cc < 0 or cc >= self.SIZE:
                continue
            if self.board[cr][cc] != color:
                continue
            visited.add((cr, cc))
            stack.extend([(cr+1,cc),(cr-1,cc),(cr,cc+1),(cr,cc-1)])
        return visited

    def _get_liberties(self, group):
        libs = set()
        for r, c in group:
            for dr, dc in [(1,0),(-1,0),(0,1),(0,-1)]:
                nr, nc = r+dr, c+dc
                if 0 <= nr < self.SIZE and 0 <= nc < self.SIZE and self.board[nr][nc] == 0:
                    libs.add((nr, nc))
        return libs

    def make_move(self, move_str):
        move_str = move_str.strip().lower()
        if move_str == 'pass' or move_str == '虚手':
            self.passes += 1
            self.last_move = None
            if self.passes >= 2:
                self._score()
            return True, ""
        self.passes = 0
        pos = parse_pos(move_str)
        if pos is None:
            return False, "格式: H8 或 pass"
        r, c = pos
        if r >= self.SIZE or c >= self.SIZE:
            return False, f"坐标超出范围 (A1-{chr(64+self.SIZE)}{self.SIZE})"
        if self.board[r][c] != 0:
            return False, "该位置已有棋子"
        player = 1 if self.current == self.p1 else 2
        # 尝试落子
        old_board = copy.deepcopy(self.board)
        self.board[r][c] = player
        # 提取对方无气棋子
        opp = 3 - player
        captured = 0
        checked = set()
        for dr, dc in [(1,0),(-1,0),(0,1),(0,-1)]:
            nr, nc = r+dr, c+dc
            if 0 <= nr < self.SIZE and 0 <= nc < self.SIZE and self.board[nr][nc] == opp:
                if (nr, nc) not in checked:
                    group = self._get_group(nr, nc, opp)
                    checked |= group
                    if len(self._get_liberties(group)) == 0:
                        for gr, gc in group:
                            self.board[gr][gc] = 0
                        captured += len(group)
        # 检查自杀
        my_group = self._get_group(r, c, player)
        if len(self._get_liberties(my_group)) == 0:
            self.board = old_board
            return False, "禁着点（自杀）"
        # 劫判
        if self.last_board is not None:
            new_str = ''.join(str(self.board[i][j]) for i in range(self.SIZE) for j in range(self.SIZE))
            if new_str == self.last_board:
                self.board = old_board
                return False, "违反劫规则"
        self.last_board = ''.join(str(old_board[i][j]) for i in range(self.SIZE) for j in range(self.SIZE))
        self.captures[player] += captured
        self.last_move = (r, c)
        return True, ""

    def _score(self):
        """简单计分: 棋子数 + 提子数"""
        black = sum(1 for r in range(self.SIZE) for c in range(self.SIZE) if self.board[r][c] == 1) + self.captures[1]
        white = sum(1 for r in range(self.SIZE) for c in range(self.SIZE) if self.board[r][c] == 2) + self.captures[2]
        if black > white:
            self.winner = self.p1
        elif white > black:
            self.winner = self.p2
        else:
            self.winner = "draw"

    def check_winner(self):
        pass  # 由 _score 或双 pass 触发

    def get_board_str(self):
        cols_label = '  ' + ' '.join(chr(65+i) for i in range(self.SIZE))
        lines = [cols_label]
        for r in range(self.SIZE-1, -1, -1):
            row_str = f"{r+1} "
            for c in range(self.SIZE):
                if self.last_move and (r, c) == self.last_move:
                    v = '▲' if self.board[r][c] == 1 else '△'
                elif self.board[r][c] == 0:
                    v = '·'
                elif self.board[r][c] == 1:
                    v = '●'
                else:
                    v = '○'
                row_str += v + ' '
            lines.append(row_str)
        return '```\n' + '\n'.join(lines) + '\n```'

    def get_embed(self):
        embed = discord.Embed(title="●○ 围棋 (9×9)", color=discord.Color.dark_gray())
        desc = f"提子 — ●{self.captures[1]} ○{self.captures[2]}"
        if self.winner:
            if self.winner == "draw":
                desc = f"**平局！**\n{desc}"
            else:
                desc = f"🏆 **{self.winner.display_name}** 获胜！\n{desc}"
            embed.color = discord.Color.gold()
        else:
            sym = "●" if self.current == self.p1 else "○"
            desc = f"{sym} **{self.current.display_name}** 的回合\n{desc}"
            if self.passes > 0:
                desc += f"\n⚠️ 对方虚手，再 pass 则结算"
        embed.description = f"{desc}\n\n{self.get_board_str()}"
        embed.add_field(name="对战", value=f"● {self.p1.display_name} (黑) vs ○ {self.p2.display_name} (白)")
        return embed


# ═══════════════════════════════════════
#  4. 跳棋 (Checkers)
# ═══════════════════════════════════════

class CheckersGame:
    GAME_NAME = "跳棋"
    MOVE_HINT = "移动: B3-C4 | 跳吃: B3xC5"
    SIZE = 8
    # 0=空 1=白 2=黑 3=白王 4=黑王

    def __init__(self, p1, p2):
        self.p1 = p1  # 白方(底部)
        self.p2 = p2  # 黑方(顶部)
        self.current = p1
        self.winner = None
        self.board = [[0]*self.SIZE for _ in range(self.SIZE)]
        # 初始布局: 白方在下(底部), 黑方在上(顶部), 只放深色格
        for r in range(3):
            for c in range(self.SIZE):
                if (r + c) % 2 == 1:
                    self.board[r][c] = 1  # 白(底部)
        for r in range(5, 8):
            for c in range(self.SIZE):
                if (r + c) % 2 == 1:
                    self.board[r][c] = 2  # 黑(顶部)
        self.must_jump_from = None  # 连续跳吃

    def switch(self):
        self.current = self.p2 if self.current == self.p1 else self.p1
        self.must_jump_from = None

    def _get_jumps(self, r, c):
        """获取从(r,c)可跳吃的目标"""
        piece = self.board[r][c]
        if piece == 0:
            return []
        is_king = piece in (3, 4)
        color = 1 if piece in (1, 3) else 2
        opp = 2 if color == 1 else 1
        opp_king = 4 if color == 1 else 3
        directions = [(1,1),(1,-1),(-1,1),(-1,-1)] if is_king else \
                      [(1,1),(1,-1)] if color == 1 else [(-1,1),(-1,-1)]
        jumps = []
        for dr, dc in directions:
            mr, mc = r+dr, c+dc
            nr, nc = r+2*dr, c+2*dc
            if 0 <= nr < self.SIZE and 0 <= mc < self.SIZE and 0 <= nc < self.SIZE:
                if self.board[mr][mc] in (opp, opp_king) and self.board[nr][nc] == 0:
                    jumps.append((nr, nc, mr, mc))
        return jumps

    def _has_any_jump(self, color):
        for r in range(self.SIZE):
            for c in range(self.SIZE):
                p = self.board[r][c]
                if p == 0:
                    continue
                if (color == 1 and p in (1, 3)) or (color == 2 and p in (2, 4)):
                    if self._get_jumps(r, c):
                        return True
        return False

    def make_move(self, move_str):
        move_str = move_str.strip().upper().replace(' ', '')
        is_jump = 'x' in move_str
        if is_jump:
            parts = move_str.split('x')
        else:
            parts = move_str.split('-')
        if len(parts) != 2:
            return False, "格式: B3-C4 或 B3xC5"
        f = parse_pos(parts[0])
        t = parse_pos(parts[1])
        if f is None or t is None:
            return False, "坐标格式错误"
        fr, fc = f
        tr, tc = t
        if fr >= self.SIZE or fc >= self.SIZE or tr >= self.SIZE or tc >= self.SIZE:
            return False, "坐标超出范围"
        piece = self.board[fr][fc]
        if piece == 0:
            return False, "起点没有棋子"
        color = 1 if piece in (1, 3) else 2
        current_color = 1 if self.current == self.p1 else 2
        if color != current_color:
            return False, "那是对方的棋子"
        # 如果有连跳要求，必须从指定位置跳
        if self.must_jump_from and (fr, fc) != self.must_jump_from:
            return False, "必须继续连跳"
        # 检查强制跳吃
        if not is_jump and self._has_any_jump(current_color):
            return False, "有棋子可以跳吃，必须跳吃"
        if is_jump:
            jumps = self._get_jumps(fr, fc)
            valid = [j for j in jumps if j[0] == tr and j[1] == tc]
            if not valid:
                return False, "无效的跳吃"
            # 执行跳吃
            self.board[tr][tc] = piece
            self.board[fr][fc] = 0
            self.board[valid[0][2]][valid[0][3]] = 0  # 吃掉对方
            # 升王
            if piece == 1 and tr == self.SIZE - 1:
                self.board[tr][tc] = 3
            elif piece == 2 and tr == 0:
                self.board[tr][tc] = 4
            # 检查连跳
            new_piece = self.board[tr][tc]
            new_jumps = self._get_jumps(tr, tc)
            if new_jumps:
                self.must_jump_from = (tr, tc)
            else:
                self.must_jump_from = None
            return True, ""
        else:
            # 普通移动
            is_king = piece in (3, 4)
            directions = [(1,1),(1,-1),(-1,1),(-1,-1)] if is_king else \
                          [(1,1),(1,-1)] if color == 1 else [(-1,1),(-1,-1)]
            dr, dc = tr - fr, tc - fc
            if (dr, dc) not in directions:
                return False, "只能斜向移动一格"
            if self.board[tr][tc] != 0:
                return False, "目标格被占用"
            self.board[tr][tc] = piece
            self.board[fr][fc] = 0
            # 升王
            if piece == 1 and tr == self.SIZE - 1:
                self.board[tr][tc] = 3
            elif piece == 2 and tr == 0:
                self.board[tr][tc] = 4
            return True, ""

    def check_winner(self):
        if self.must_jump_from:
            return  # 连跳中不检查
        white = sum(1 for r in range(self.SIZE) for c in range(self.SIZE) if self.board[r][c] in (1, 3))
        black = sum(1 for r in range(self.SIZE) for c in range(self.SIZE) if self.board[r][c] in (2, 4))
        if white == 0:
            self.winner = self.p2
        elif black == 0:
            self.winner = self.p1

    def get_board_str(self):
        pieces = {0: '·', 1: '○', 2: '●', 3: '♔', 4: '♚'}
        cols = '  ' + ' '.join(chr(65+i) for i in range(self.SIZE))
        lines = [cols]
        for r in range(self.SIZE-1, -1, -1):
            row_str = f"{r+1} "
            for c in range(self.SIZE):
                row_str += pieces[self.board[r][c]] + ' '
            lines.append(row_str)
        return '```\n' + '\n'.join(lines) + '\n```'

    def get_embed(self):
        embed = discord.Embed(title="○● 跳棋 (西洋跳棋)", color=discord.Color.red())
        if self.winner:
            embed.description = f"🏆 **{self.winner.display_name}** 获胜！\n\n{self.get_board_str()}"
            embed.color = discord.Color.gold()
        else:
            sym = "○" if self.current == self.p1 else "●"
            extra = "\n⚠️ 必须继续连跳！" if self.must_jump_from else ""
            embed.description = f"{sym} **{self.current.display_name}** 的回合{extra}\n\n{self.get_board_str()}"
        embed.add_field(name="对战", value=f"○ {self.p1.display_name} (白) vs ● {self.p2.display_name} (黑)")
        embed.add_field(name="提示", value="♔=白王 ♚=黑王 | 跳吃用 x: B3xC5")
        return embed


# ═══════════════════════════════════════
#  5. 斗兽棋 (Dou Shou Qi)
# ═══════════════════════════════════════

ANIMAL_NAMES = {8: '象', 7: '狮', 6: '虎', 5: '豹', 4: '狼', 3: '狗', 2: '猫', 1: '鼠'}

class AnimalChessGame:
    GAME_NAME = "斗兽棋"
    MOVE_HINT = "移动: A3-A4"
    COLS = 7
    ROWS = 9

    def __init__(self, p1, p2):
        self.p1 = p1  # 底部, 数字大写
        self.p2 = p2  # 顶部, 数字小写
        self.current = p1
        self.winner = None
        # board[row][col] = None 或 (rank, player)  player: 1或2
        self.board = [[None]*self.COLS for _ in range(self.ROWS)]
        self._setup()

    def _setup(self):
        # Player 1 (底部, row 0-2)
        self.board[0][0] = (7, 1)  # 狮 A1
        self.board[0][6] = (6, 1)  # 虎 G1
        self.board[1][1] = (3, 1)  # 狗 B2
        self.board[1][5] = (2, 1)  # 猫 F2
        self.board[2][0] = (1, 1)  # 鼠 A3
        self.board[2][2] = (5, 1)  # 豹 C3
        self.board[2][4] = (4, 1)  # 狼 E3
        self.board[2][6] = (8, 1)  # 象 G3
        # Player 2 (顶部, row 6-8) 镜像
        self.board[8][0] = (7, 2)
        self.board[8][6] = (6, 2)
        self.board[7][1] = (3, 2)
        self.board[7][5] = (2, 2)
        self.board[6][0] = (1, 2)
        self.board[6][2] = (5, 2)
        self.board[6][4] = (4, 2)
        self.board[6][6] = (8, 2)

    def switch(self):
        self.current = self.p2 if self.current == self.p1 else self.p1

    def _is_river(self, r, c):
        """河流: rows 3-5, cols 1-2 和 4-5"""
        return (3 <= r <= 5) and (c in (1, 2, 4, 5))

    def _is_trap(self, r, c, for_player):
        """陷阱: 对方兽穴周围"""
        if for_player == 1:
            # Player 1 的陷阱在顶部 (Player 2 的兽穴旁)
            return (r, c) in [(7, 3), (8, 2), (8, 4)]
        else:
            return (r, c) in [(1, 3), (0, 2), (0, 4)]

    def _is_den(self, r, c, for_player):
        """兽穴"""
        if for_player == 1:
            return (r, c) == (8, 3)  # Player 2 的兽穴
        else:
            return (r, c) == (0, 3)  # Player 1 的兽穴

    def _is_own_den(self, r, c, player):
        if player == 1:
            return (r, c) == (0, 3)
        else:
            return (r, c) == (8, 3)

    def _can_capture(self, attacker_rank, defender_rank, attacker_pos, defender_pos, attacker_player):
        """判断攻击方能否吃防守方"""
        ar, ac = attacker_pos
        dr, dc = defender_pos
        # 防守方在陷阱中，等级降为0
        if self._is_trap(dr, dc, 3 - attacker_player):
            return True
        # 鼠在水中不能吃岸上的象，岸上的不能吃水中的鼠
        if self._is_river(ar, ac) != self._is_river(dr, dc):
            return False
        # 鼠吃象
        if attacker_rank == 1 and defender_rank == 8:
            return True
        # 象不能吃鼠
        if attacker_rank == 8 and defender_rank == 1:
            return False
        return attacker_rank >= defender_rank

    def make_move(self, move_str):
        move = parse_move(move_str)
        if move is None:
            return False, "格式: A3-A4"
        (fr, fc), (tr, tc) = move
        if fr >= self.ROWS or fc >= self.COLS or tr >= self.ROWS or tc >= self.COLS:
            return False, "坐标超出范围"
        piece = self.board[fr][fc]
        if piece is None:
            return False, "起点没有棋子"
        rank, player = piece
        current_player = 1 if self.current == self.p1 else 2
        if player != current_player:
            return False, "那是对方的棋子"
        if self._is_own_den(tr, tc, current_player):
            return False, "不能进入自己的兽穴"
        dr, dc = tr - fr, tc - fc
        # 普通移动: 上下左右一格
        if abs(dr) + abs(dc) == 1:
            # 鼠才能进河
            if self._is_river(tr, tc) and rank != 1:
                return False, "只有鼠能进河"
            # 河中的鼠不能被吃(这里检查目标格)
            target = self.board[tr][tc]
            if target is not None:
                tr_rank, tr_player = target
                if tr_player == current_player:
                    return False, "目标格有自己的棋子"
                if not self._can_capture(rank, tr_rank, (fr, fc), (tr, tc), current_player):
                    return False, "你的棋子吃不了对方"
            self.board[tr][tc] = piece
            self.board[fr][fc] = None
            return True, ""
        # 狮虎跳河
        if rank in (6, 7) and (abs(dr) > 1 or abs(dc) > 1):
            # 必须是直线
            if fr != tr and fc != tc:
                return False, "只能直线移动"
            # 检查路径
            if fr == tr:
                step = 1 if tc > fc else -1
                has_rat = False
                for c in range(fc + step, tc, step):
                    if self._is_river(fr, c):
                        if self.board[fr][c] is not None:
                            has_rat = True
                            break
                    else:
                        return False, "路径不通"
                if has_rat:
                    return False, "河中有鼠阻挡"
            else:
                step = 1 if tr > fr else -1
                has_rat = False
                for r in range(fr + step, tr, step):
                    if self._is_river(r, fc):
                        if self.board[r][fc] is not None:
                            has_rat = True
                            break
                    else:
                        return False, "路径不通"
                if has_rat:
                    return False, "河中有鼠阻挡"
            target = self.board[tr][tc]
            if target is not None:
                tr_rank, tr_player = target
                if tr_player == current_player:
                    return False, "目标格有自己的棋子"
                if not self._can_capture(rank, tr_rank, (fr, fc), (tr, tc), current_player):
                    return False, "你的棋子吃不了对方"
            self.board[tr][tc] = piece
            self.board[fr][fc] = None
            return True, ""
        return False, "无效移动"

    def check_winner(self):
        current_player = 1 if self.current == self.p1 else 2
        # 检查是否进入对方兽穴
        opp_den = (8, 3) if current_player == 1 else (0, 3)
        if self.board[opp_den[0]][opp_den[1]] is not None:
            _, p = self.board[opp_den[0]][opp_den[1]]
            if p == current_player:
                self.winner = self.current
                return
        # 检查对方是否无棋子
        opp = 2 if current_player == 1 else 1
        opp_count = sum(1 for r in range(self.ROWS) for c in range(self.COLS)
                       if self.board[r][c] is not None and self.board[r][c][1] == opp)
        if opp_count == 0:
            self.winner = self.current

    def get_board_str(self):
        cols = '  ' + ' '.join(chr(65+i) for i in range(self.COLS))
        lines = [cols]
        for r in range(self.ROWS-1, -1, -1):
            row_str = f"{r+1} "
            for c in range(self.COLS):
                cell = self.board[r][c]
                if cell is None:
                    if self._is_river(r, c):
                        v = '~'
                    elif self._is_den(r, c, 1) or self._is_den(r, c, 2):
                        v = '穴'
                    elif self._is_trap(r, c, 1) or self._is_trap(r, c, 2):
                        v = '×'
                    else:
                        v = '·'
                else:
                    rank, player = cell
                    name = ANIMAL_NAMES[rank]
                    v = name if player == 1 else name.lower()
                row_str += v + ' '
            lines.append(row_str)
        return '```\n' + '\n'.join(lines) + '\n```'

    def get_embed(self):
        embed = discord.Embed(title="🦁 斗兽棋", color=discord.Color.orange())
        if self.winner:
            embed.description = f"🏆 **{self.winner.display_name}** 获胜！\n\n{self.get_board_str()}"
            embed.color = discord.Color.gold()
        else:
            p_tag = "大写" if self.current == self.p1 else "小写"
            embed.description = f"**{self.current.display_name}** ({p_tag}) 的回合\n\n{self.get_board_str()}"
        embed.add_field(name="对战", value=f"{self.p1.display_name} (大写) vs {self.p2.display_name} (小写)")
        embed.add_field(name="等级", value="象8>狮7>虎6>豹5>狼4>狗3>猫2>鼠1\n鼠可吃象 | 狮虎可跳河 | ~河 ×陷阱 穴兽穴", inline=False)
        return embed


# ═══════════════════════════════════════
#  6. 飞行棋 (Ludo)
# ═══════════════════════════════════════

class LudoGame:
    GAME_NAME = "飞行棋"
    MOVE_HINT = "点击掷骰子按钮"
    TRACK_LEN = 50

    def __init__(self, p1, p2):
        self.p1 = p1  # 🔴
        self.p2 = p2  # 🔵
        self.current = p1
        self.winner = None
        self.positions = {p1.id: 0, p2.id: 0}
        self.last_dice = None

    def switch(self):
        self.current = self.p2 if self.current == self.p1 else self.p1

    def make_move(self, move_str):
        return False, "请点击掷骰子按钮"

    def roll_dice(self):
        self.last_dice = random.randint(1, 6)
        pid = self.current.id
        new_pos = self.positions[pid] + self.last_dice
        # 检查是否踩到对方
        opp_id = self.p2.id if self.current == self.p1 else self.p1.id
        if self.positions[opp_id] == new_pos and new_pos < self.TRACK_LEN:
            self.positions[opp_id] = 0  # 踩回起点
        if new_pos >= self.TRACK_LEN:
            self.winner = self.current
        else:
            self.positions[pid] = new_pos
        return self.last_dice

    def check_winner(self):
        pass

    def get_board_str(self):
        p1_pos = self.positions[self.p1.id]
        p2_pos = self.positions[self.p2.id]
        lines = [
            f"🔴 {self.p1.display_name}: {progress_bar(p1_pos, self.TRACK_LEN)} {p1_pos}/{self.TRACK_LEN}",
            f"🔵 {self.p2.display_name}: {progress_bar(p2_pos, self.TRACK_LEN)} {p2_pos}/{self.TRACK_LEN}",
        ]
        if self.last_dice:
            lines.append(f"\n🎲 上次掷出: {self.last_dice}")
        return '```\n' + '\n'.join(lines) + '\n```'

    def get_embed(self):
        embed = discord.Embed(title="🎲 飞行棋", color=discord.Color.purple())
        if self.winner:
            embed.description = f"🏆 **{self.winner.display_name}** 先到终点，获胜！\n\n{self.get_board_str()}"
            embed.color = discord.Color.gold()
        else:
            sym = "🔴" if self.current == self.p1 else "🔵"
            embed.description = f"{sym} **{self.current.display_name}** 的回合 — 掷骰子\n\n{self.get_board_str()}"
        embed.add_field(name="对战", value=f"🔴 {self.p1.display_name} vs 🔵 {self.p2.display_name}")
        embed.add_field(name="规则", value="踩到对方送其回起点 | 先到终点获胜", inline=False)
        return embed


class LudoView(discord.ui.View):
    def __init__(self, game, channel, points_cb=None):
        super().__init__(timeout=300)
        self.game = game
        self.channel = channel
        self.points_cb = points_cb
        self.message = None

    @discord.ui.button(label="掷骰子", style=discord.ButtonStyle.primary, emoji="🎲")
    async def roll_btn(self, interaction, button):
        if interaction.user.id != self.game.current.id:
            await interaction.response.send_message("还没轮到你！", ephemeral=True)
            return
        dice = self.game.roll_dice()
        self.game.check_winner()
        if self.game.winner:
            for c in self.children:
                c.disabled = True
            embed = self.game.get_embed()
            await interaction.response.edit_message(embed=embed, view=self)
            if self.points_cb:
                await self.points_cb(self.game.winner.id)
            if self.channel.id in active_games:
                del active_games[self.channel.id]
        else:
            self.game.switch()
            await interaction.response.edit_message(embed=self.game.get_embed(), view=self)

    @discord.ui.button(label="认输", style=discord.ButtonStyle.danger, emoji="🏳️")
    async def resign_btn(self, interaction, button):
        if interaction.user.id not in (self.game.p1.id, self.game.p2.id):
            await interaction.response.send_message("你不是本局玩家！", ephemeral=True)
            return
        self.game.winner = self.game.p2 if interaction.user.id == self.game.p1.id else self.game.p1
        for c in self.children:
            c.disabled = True
        embed = self.game.get_embed()
        await interaction.response.edit_message(embed=embed, view=self)
        if self.points_cb:
            await self.points_cb(self.game.winner.id)
        if self.channel.id in active_games:
            del active_games[self.channel.id]

    async def on_timeout(self):
        for c in self.children:
            c.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except:
                pass
        if self.channel.id in active_games:
            del active_games[self.channel.id]


# ═══════════════════════════════════════
#  7. 中国象棋 (Xiangqi)
# ═══════════════════════════════════════

# 棋子: 帥仕相俥傌炮兵 (红) 將士象車馬砲卒 (黑)
XIANGQI_PIECES = {
    '帥': ('general', 1), '將': ('general', 2),
    '仕': ('advisor', 1), '士': ('advisor', 2),
    '相': ('elephant', 1), '象': ('elephant', 2),
    '俥': ('chariot', 1), '車': ('chariot', 2),
    '傌': ('horse', 1), '馬': ('horse', 2),
    '炮': ('cannon', 1), '砲': ('cannon', 2),
    '兵': ('soldier', 1), '卒': ('soldier', 2),
}

class XiangqiGame:
    GAME_NAME = "中国象棋"
    MOVE_HINT = "移动: H2-E2 (列+行-列+行)"
    COLS = 9
    ROWS = 10

    def __init__(self, p1, p2):
        self.p1 = p1  # 红方(底部)
        self.p2 = p2  # 黑方(顶部)
        self.current = p1
        self.winner = None
        self.board = [[None]*self.COLS for _ in range(self.ROWS)]
        self._setup()

    def _setup(self):
        # 红方 (底部, board[0-3], row 1-4)
        self.board[0] = ['俥','傌','相','仕','帥','仕','相','傌','俥']
        self.board[2][1] = '炮'
        self.board[2][7] = '炮'
        for c in [0, 2, 4, 6, 8]:
            self.board[3][c] = '兵'
        # 黑方 (顶部, board[6-9], row 7-10)
        self.board[9] = ['車','馬','象','士','將','士','象','馬','車']
        self.board[7][1] = '砲'
        self.board[7][7] = '砲'
        for c in [0, 2, 4, 6, 8]:
            self.board[6][c] = '卒'

    def switch(self):
        self.current = self.p2 if self.current == self.p1 else self.p1

    def _in_palace(self, r, c, player):
        if player == 1:  # 红方: rows 1-3 (index 0-2), cols 3-5
            return 0 <= r <= 2 and 3 <= c <= 5
        else:  # 黑方: rows 8-10 (index 7-9), cols 3-5
            return 7 <= r <= 9 and 3 <= c <= 5

    def _crossed_river(self, r, player):
        if player == 1:
            return r >= 5  # 红方过河 (向上)
        else:
            return r <= 4  # 黑方过河 (向下)

    def _valid_move(self, fr, fc, tr, tc):
        piece = self.board[fr][fc]
        if piece is None:
            return False, "起点没有棋子"
        ptype, player = XIANGQI_PIECES[piece]
        current_player = 1 if self.current == self.p1 else 2
        if player != current_player:
            return False, "那是对方的棋子"
        if fr == tr and fc == tc:
            return False, "不能原地不动"
        target = self.board[tr][tc]
        if target is not None:
            _, t_player = XIANGQI_PIECES[target]
            if t_player == player:
                return False, "目标格有自己的棋子"
        dr, dc = tr - fr, tc - fc

        if ptype == 'general':
            if not self._in_palace(tr, tc, player):
                return False, "帥/將不能出九宫"
            if abs(dr) + abs(dc) != 1:
                # 检查飞将
                if fc == tc and target and XIANGQI_PIECES[target][0] == 'general':
                    # 检查中间是否有棋子
                    step = 1 if tr > fr else -1
                    for r in range(fr+step, tr, step):
                        if self.board[r][fc] is not None:
                            return False, "无效移动"
                    return True, ""  # 飞将吃将
                return False, "帥/將只能走一步"
            return True, ""

        elif ptype == 'advisor':
            if not self._in_palace(tr, tc, player):
                return False, "仕/士不能出九宫"
            if abs(dr) != 1 or abs(dc) != 1:
                return False, "仕/士只能斜走一步"
            return True, ""

        elif ptype == 'elephant':
            if self._crossed_river(tr, player):
                return False, "相/象不能过河"
            if abs(dr) != 2 or abs(dc) != 2:
                return False, "相/象只能走田字"
            # 塞象眼
            if self.board[fr + dr//2][fc + dc//2] is not None:
                return False, "塞象眼"
            return True, ""

        elif ptype == 'horse':
            if not ((abs(dr) == 2 and abs(dc) == 1) or (abs(dr) == 1 and abs(dc) == 2)):
                return False, "马走日字"
            # 蹩马腿
            if abs(dr) == 2:
                if self.board[fr + dr//2][fc] is not None:
                    return False, "蹩马腿"
            else:
                if self.board[fr][fc + dc//2] is not None:
                    return False, "蹩马腿"
            return True, ""

        elif ptype == 'chariot':
            if dr != 0 and dc != 0:
                return False, "车只能直走"
            step_r = 0 if dr == 0 else (1 if dr > 0 else -1)
            step_c = 0 if dc == 0 else (1 if dc > 0 else -1)
            r, c = fr + step_r, fc + step_c
            while r != tr or c != tc:
                if self.board[r][c] is not None:
                    return False, "车不能越子"
                r += step_r
                c += step_c
            return True, ""

        elif ptype == 'cannon':
            if dr != 0 and dc != 0:
                return False, "炮只能直走"
            step_r = 0 if dr == 0 else (1 if dr > 0 else -1)
            step_c = 0 if dc == 0 else (1 if dc > 0 else -1)
            r, c = fr + step_r, fc + step_c
            screen_count = 0
            while r != tr or c != tc:
                if self.board[r][c] is not None:
                    screen_count += 1
                r += step_r
                c += step_c
            if target is not None:
                if screen_count != 1:
                    return False, "炮吃子需要一个炮架"
            else:
                if screen_count != 0:
                    return False, "炮移动时不能越子"
            return True, ""

        elif ptype == 'soldier':
            forward = 1 if player == 1 else -1  # 红方向上(dr正), 黑方向下(dr负)
            if dr == forward and dc == 0:
                return True, ""
            if self._crossed_river(fr, player):
                if dc != 0 and dr == 0 and abs(dc) == 1:
                    return True, ""
            return False, "兵/卒只能前进，过河后可横走"

        return False, "未知棋子"

    def make_move(self, move_str):
        move = parse_move(move_str)
        if move is None:
            return False, "格式: H2-E2"
        (fr, fc), (tr, tc) = move
        if fr >= self.ROWS or fc >= self.COLS or tr >= self.ROWS or tc >= self.COLS:
            return False, "坐标超出范围"
        ok, err = self._valid_move(fr, fc, tr, tc)
        if not ok:
            return False, err
        # 执行移动
        target = self.board[tr][tc]
        self.board[tr][tc] = self.board[fr][fc]
        self.board[fr][fc] = None
        # 检查是否吃了将/帥
        if target and XIANGQI_PIECES[target][0] == 'general':
            self.winner = self.current
        return True, ""

    def check_winner(self):
        pass  # 在 make_move 中处理

    def get_board_str(self):
        cols = '  ' + ' '.join(chr(65+i) for i in range(self.COLS))
        lines = [cols]
        for r in range(self.ROWS-1, -1, -1):
            row_str = f"{r+1} "
            for c in range(self.COLS):
                cell = self.board[r][c]
                if cell is None:
                    v = '·'
                else:
                    v = cell
                row_str += v + ' '
            lines.append(row_str)
            if r == 5:
                lines.append('  ─ ─ ─ 楚河 漢界 ─ ─ ─')
        return '```\n' + '\n'.join(lines) + '\n```'

    def get_embed(self):
        embed = discord.Embed(title="帥將 中国象棋", color=discord.Color.red())
        if self.winner:
            embed.description = f"🏆 **{self.winner.display_name}** 吃将获胜！\n\n{self.get_board_str()}"
            embed.color = discord.Color.gold()
        else:
            tag = "红" if self.current == self.p1 else "黑"
            embed.description = f"**{self.current.display_name}** ({tag}方) 的回合\n\n{self.get_board_str()}"
        embed.add_field(name="对战", value=f"红 {self.p1.display_name} vs 黑 {self.p2.display_name}")
        return embed


# ═══════════════════════════════════════
#  8. 国际象棋 (Chess)
# ═══════════════════════════════════════

CHESS_PIECES = {
    '♔': ('king', 1), '♚': ('king', 2),
    '♕': ('queen', 1), '♛': ('queen', 2),
    '♖': ('rook', 1), '♜': ('rook', 2),
    '♗': ('bishop', 1), '♝': ('bishop', 2),
    '♘': ('knight', 1), '♞': ('knight', 2),
    '♙': ('pawn', 1), '♟': ('pawn', 2),
}

class ChessGame:
    GAME_NAME = "国际象棋"
    MOVE_HINT = "移动: e2-e4 (列+行-列+行)"
    SIZE = 8

    def __init__(self, p1, p2):
        self.p1 = p1  # 白方(底部)
        self.p2 = p2  # 黑方(顶部)
        self.current = p1
        self.winner = None
        self.board = [[None]*self.SIZE for _ in range(self.SIZE)]
        self._setup()
        self.king_moved = {1: False, 2: False}
        self.rook_moved = {1: {0: False, 7: False}, 2: {0: False, 7: False}}

    def _setup(self):
        # 白方 (底部, board[0-1], row 1-2)
        self.board[0] = ['♖','♘','♗','♕','♔','♗','♘','♖']
        self.board[1] = ['♙'] * 8
        # 黑方 (顶部, board[6-7], row 7-8)
        self.board[7] = ['♜','♞','♝','♛','♚','♝','♞','♜']
        self.board[6] = ['♟'] * 8

    def switch(self):
        self.current = self.p2 if self.current == self.p1 else self.p1

    def _valid_move(self, fr, fc, tr, tc):
        piece = self.board[fr][fc]
        if piece is None:
            return False, "起点没有棋子"
        ptype, player = CHESS_PIECES[piece]
        current_player = 1 if self.current == self.p1 else 2
        if player != current_player:
            return False, "那是对方的棋子"
        if fr == tr and fc == tc:
            return False, "不能原地不动"
        target = self.board[tr][tc]
        if target is not None:
            _, t_player = CHESS_PIECES[target]
            if t_player == player:
                return False, "目标格有自己的棋子"
        dr, dc = tr - fr, tc - fc

        if ptype == 'king':
            # 普通移动
            if abs(dr) <= 1 and abs(dc) <= 1:
                return True, ""
            # 王车易位
            if dr == 0 and abs(dc) == 2 and not self.king_moved[player]:
                # 短易位或长易位
                if dc == 2:  # 短易位
                    if self.board[fr][7] and CHESS_PIECES[self.board[fr][7]][0] == 'rook' \
                       and not self.rook_moved[player][7]:
                        if self.board[fr][5] is None and self.board[fr][6] is None:
                            return True, "castling"
                elif dc == -2:  # 长易位
                    if self.board[fr][0] and CHESS_PIECES[self.board[fr][0]][0] == 'rook' \
                       and not self.rook_moved[player][0]:
                        if self.board[fr][1] is None and self.board[fr][2] is None and self.board[fr][3] is None:
                            return True, "castling"
            return False, "王的移动无效"

        elif ptype == 'queen':
            if dr != 0 and dc != 0 and abs(dr) != abs(dc):
                return False, "后只能直走或斜走"
            step_r = 0 if dr == 0 else (1 if dr > 0 else -1)
            step_c = 0 if dc == 0 else (1 if dc > 0 else -1)
            r, c = fr + step_r, fc + step_c
            while r != tr or c != tc:
                if self.board[r][c] is not None:
                    return False, "后不能越子"
                r += step_r
                c += step_c
            return True, ""

        elif ptype == 'rook':
            if dr != 0 and dc != 0:
                return False, "车只能直走"
            step_r = 0 if dr == 0 else (1 if dr > 0 else -1)
            step_c = 0 if dc == 0 else (1 if dc > 0 else -1)
            r, c = fr + step_r, fc + step_c
            while r != tr or c != tc:
                if self.board[r][c] is not None:
                    return False, "车不能越子"
                r += step_r
                c += step_c
            return True, ""

        elif ptype == 'bishop':
            if abs(dr) != abs(dc) or dr == 0:
                return False, "象只能斜走"
            step_r = 1 if dr > 0 else -1
            step_c = 1 if dc > 0 else -1
            r, c = fr + step_r, fc + step_c
            while r != tr or c != tc:
                if self.board[r][c] is not None:
                    return False, "象不能越子"
                r += step_r
                c += step_c
            return True, ""

        elif ptype == 'knight':
            if (abs(dr), abs(dc)) not in [(2, 1), (1, 2)]:
                return False, "马走日字"
            return True, ""

        elif ptype == 'pawn':
            forward = 1 if player == 1 else -1  # 白方向上(dr正), 黑方向下(dr负)
            start_row = 1 if player == 1 else 6
            # 直走
            if dc == 0 and dr == forward and target is None:
                return True, ""
            # 起始位置可走两步
            if dc == 0 and dr == 2*forward and fr == start_row and target is None \
               and self.board[fr+forward][fc] is None:
                return True, ""
            # 斜吃
            if abs(dc) == 1 and dr == forward and target is not None:
                return True, ""
            return False, "兵的移动无效"

        return False, "未知棋子"

    def make_move(self, move_str):
        # 检查王车易位特殊输入
        castling = move_str.strip().lower()
        if castling in ('0-0', 'o-o', 'o-o', '短易位'):
            player = 1 if self.current == self.p1 else 2
            row = 7 if player == 1 else 0
            ok, err = self._valid_move(row, 4, row, 6)
            if not ok:
                return False, err
            self.board[row][6] = self.board[row][4]
            self.board[row][5] = self.board[row][7]
            self.board[row][4] = None
            self.board[row][7] = None
            self.king_moved[player] = True
            self.rook_moved[player][7] = True
            return True, ""
        if castling in ('0-0-0', 'o-o-o', 'o-o-o', '长易位'):
            player = 1 if self.current == self.p1 else 2
            row = 7 if player == 1 else 0
            ok, err = self._valid_move(row, 4, row, 2)
            if not ok:
                return False, err
            self.board[row][2] = self.board[row][4]
            self.board[row][3] = self.board[row][0]
            self.board[row][4] = None
            self.board[row][0] = None
            self.king_moved[player] = True
            self.rook_moved[player][0] = True
            return True, ""

        move = parse_move(move_str)
        if move is None:
            return False, "格式: e2-e4 或 0-0 (易位)"
        (fr, fc), (tr, tc) = move
        if fr >= self.SIZE or fc >= self.SIZE or tr >= self.SIZE or tc >= self.SIZE:
            return False, "坐标超出范围"
        ok, err = self._valid_move(fr, fc, tr, tc)
        if not ok:
            return False, err
        piece = self.board[fr][fc]
        ptype, player = CHESS_PIECES[piece]
        # 执行移动
        target = self.board[tr][tc]
        self.board[tr][tc] = piece
        self.board[fr][fc] = None
        # 标记王/车已移动
        if ptype == 'king':
            self.king_moved[player] = True
        elif ptype == 'rook':
            if fc == 0:
                self.rook_moved[player][0] = True
            elif fc == 7:
                self.rook_moved[player][7] = True
        # 兵升变 (自动升为后)
        if ptype == 'pawn':
            if (player == 1 and tr == 7) or (player == 2 and tr == 0):
                self.board[tr][tc] = '♕' if player == 1 else '♛'
        # 吃王
        if target and CHESS_PIECES[target][0] == 'king':
            self.winner = self.current
        return True, ""

    def check_winner(self):
        pass  # 在 make_move 中处理

    def get_board_str(self):
        cols = '  ' + ' '.join(chr(97+i) for i in range(self.SIZE))  # a-h
        lines = [cols]
        for r in range(self.SIZE-1, -1, -1):
            row_str = f"{r+1} "
            for c in range(self.SIZE):
                cell = self.board[r][c]
                if cell is None:
                    v = '·'
                else:
                    v = cell
                row_str += v + ' '
            lines.append(row_str)
        return '```\n' + '\n'.join(lines) + '\n```'

    def get_embed(self):
        embed = discord.Embed(title="♔♚ 国际象棋", color=discord.Color.blurple())
        if self.winner:
            embed.description = f"🏆 **{self.winner.display_name}** 吃王获胜！\n\n{self.get_board_str()}"
            embed.color = discord.Color.gold()
        else:
            tag = "白" if self.current == self.p1 else "黑"
            embed.description = f"**{self.current.display_name}** ({tag}方) 的回合\n\n{self.get_board_str()}"
        embed.add_field(name="对战", value=f"♔ {self.p1.display_name} (白) vs ♚ {self.p2.display_name} (黑)")
        embed.add_field(name="特殊", value="兵自动升后 | 0-0短易位 0-0-0长易位", inline=False)
        return embed


# ═══════════════════════════════════════
#  注册函数
# ═══════════════════════════════════════

GAMES = [
    ('c4', '重力四子棋 / Connect Four', Connect4Game, Connect4View, True),
    ('gomoku', '五子棋 / Gomoku', GomokuGame, GameView, False),
    ('go', '围棋 / Go', GoGame, GameView, False),
    ('checkers', '跳棋 / Checkers', CheckersGame, GameView, False),
    ('animal', '斗兽棋 / Animal Chess', AnimalChessGame, GameView, False),
    ('ludo', '飞行棋 / Ludo', LudoGame, LudoView, True),
    ('xiangqi', '中国象棋 / Chinese Chess', XiangqiGame, GameView, False),
    ('chess', '国际象棋 / Chess', ChessGame, GameView, False),
]

def register_board_games(bot, add_points_cb=None):
    """注册所有棋盘游戏命令"""

    async def award_points(winner_id):
        if add_points_cb:
            try:
                add_points_cb(winner_id, 20)
            except Exception as e:
                print(f"[BoardGames] 积分奖励失败: {e}")

    async def start_game(interaction, game_class, view_class, is_custom_view, p1, p2):
        channel = interaction.channel
        if channel.id in active_games:
            await interaction.followup.send("⚠️ 本频道已有进行中的游戏，请先结束。", ephemeral=True)
            return
        game = game_class(p1, p2)
        if is_custom_view:
            view = view_class(game, channel, award_points)
        else:
            view = GameView(game, channel, award_points)
        embed = game.get_embed()
        msg = await interaction.followup.send(embed=embed, view=view)
        view.message = msg
        active_games[channel.id] = view

    for cmd_name, cmd_desc, game_cls, view_cls, is_custom in GAMES:
        def make_command(name=cmd_name, desc=cmd_desc, gcls=game_cls, vcls=view_cls, custom=is_custom):
            @bot.tree.command(name=name, description=desc)
            async def game_command(interaction: discord.Interaction, opponent: discord.Member):
                if opponent.id == interaction.user.id:
                    await interaction.response.send_message("不能和自己下棋！", ephemeral=True)
                    return
                if opponent.bot:
                    await interaction.response.send_message("不能和机器人下棋！", ephemeral=True)
                    return
                embed = discord.Embed(
                    title=f"🎯 {gcls.GAME_NAME} 挑战",
                    description=f"**{interaction.user.display_name}** 向 **{opponent.display_name}** 发起了 {gcls.GAME_NAME} 挑战！\n\n请在60秒内接受或拒绝。",
                    color=discord.Color.green()
                )

                async def start_cb(interaction):
                    await start_game(interaction, gcls, vcls, custom, interaction.user, opponent)

                view = ChallengeView(interaction.user, opponent, gcls.GAME_NAME, start_cb)
                await interaction.response.send_message(embed=embed, view=view)

        make_command()

    print(f"[BoardGames] 已注册 {len(GAMES)} 个棋盘游戏命令")
