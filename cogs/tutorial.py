"""
FSBot Tutorial Cog -- 新手教程 / Beginner's Guide
/tutorial -- 分页多语言新手教程
"""
import discord
from discord.ext import commands
from discord import app_commands


# ══════════════════════════════════════════════
# 多语言教程数据
# ══════════════════════════════════════════════

TUTORIAL_DATA = {
    'zh': {
        'title': ' FSBot 新手教程',
        'color': 0x5865F2,
        'pages': [
            # ── 第1页: 欢迎 & 基础 ──
            {
                'title': '欢迎来到 FSBot！',
                'fields': [
                    (' daily 每日签到', '每天签到领取积分，连续签到奖励更高！\n签到会同时获得永久积分和月度积分。', False),
                    (' balance 查看余额', '查看你的永久积分、月度积分、等级和经验值。', False),
                    (' rank 等级卡', '查看你的等级卡片，展示当前等级和进度。', False),
                    (' leaderboard 排行榜', '查看本月积分排行榜，每月1日结算Top3奖励丰厚！', False),
                ],
                'footer': '第 1/6 页  基础功能',
            },
            # ── 第2页: 天赋 & 商店 ──
            {
                'title': '天赋系统 & 积分商店',
                'fields': [
                    (' talents 天赋树', '查看你的4大天赋：幸运、财富、智慧、魅力。\n不同天赋影响游戏奖励、经验获取等。', False),
                    (' upgrade 升级天赋', '消耗积分升级天赋等级，解锁更强效果。', False),
                    (' pointshop 积分商店', '浏览商店商品，用永久积分兑换道具。', False),
                    (' redeem 兑换商品', '输入商品ID兑换你想要的道具。', False),
                    (' transfer 转账', '把积分转给其他用户，请谨慎操作。', False),
                ],
                'footer': '第 2/6 页  天赋 & 商店',
            },
            # ── 第3页: 小游戏 ──
            {
                'title': '小游戏中心',
                'fields': [
                    (' games 小游戏列表', '查看所有可玩的小游戏及奖励。', False),
                    (' rps 猜拳  ·  guess 猜数  ·  dice 骰子', '经典三件套，赢了都有积分奖励！', False),
                    (' battle / battle2 对战', '伪联机/真人对战，和其他成员PK！', False),
                    (' slot 摇奖机', '试试手气，三个一样大奖！', False),
                    (' idiom 成语接龙', '中文成语接龙，考验你的词汇量。', False),
                    (' minesweeper 扫雷', '经典扫雷游戏，小心炸弹！', False),
                ],
                'footer': '第 3/6 页  小游戏',
            },
            # ── 第4页: 大型游戏 ──
            {
                'title': '大型多人游戏',
                'fields': [
                    (' russian 恶魔轮盘赌', '紧张刺激的轮盘赌，看谁活到最后！\n用 /russianstop 可强制结束。', False),
                    (' uno UNO卡牌', '经典UNO，支持多人对战！', False),
                    (' werewolf 狼人杀', '夜晚DM交互 + 白天频道投票，完整狼人杀体验。\n4-12人均可游玩。', False),
                    (' quoridor 路墙棋', '策略博弈，用墙挡住对手或冲向终点！\n支持自定义规则和4人模式。', False),
                ],
                'footer': '第 4/6 页  大型游戏',
            },
            # ── 第5页: 棋盘游戏 ──
            {
                'title': '棋盘游戏 (赢方 +20 积分)',
                'fields': [
                    (' c4 重力四子棋  ·  gomoku 五子棋', '经典棋类，快速上手。', False),
                    (' go 围棋  ·  checkers 跳棋', '传统棋类，考验大局观。', False),
                    (' animal 斗兽棋', '象狮虎豹狼狗猫鼠，鼠克象！', False),
                    (' ludo 飞行棋', '4人飞行棋，踩到对方送回起点。', False),
                    (' xiangqi 中国象棋  ·  chess 国际象棋', '两大象棋，支持完整规则。', False),
                    ('用法', '输入命令 + @对手 即可开始对局。\n例: /c4 @玩家', False),
                ],
                'footer': '第 5/6 页  棋盘游戏',
            },
            # ── 第6页: 音乐 & 其他 ──
            {
                'title': '音乐机器人 & 其他功能',
                'fields': [
                    ('音乐命令 (前缀 !)', '!play 播放  !search 搜索B站  !batch 批量加歌\n!skip 跳过  !queue 队列  !nowplaying 正在播放\n!pause !resume 暂停/恢复  !volume 音量\n!loop 循环  !shuffle 随机  !remove 移除  !disconnect 断开', False),
                    ('支持的音源', 'B站视频/分P/au号  ·  YouTube(需配代理)\n!batch 支持 | 或换行分隔，最多20首', False),
                    (' redpacket 红包', '发积分红包，二倍均值法，手气最佳有排行！', False),
                    (' role 游戏身份组', '获取或移除游戏身份组角色。', False),
                    (' listmods 模组列表', '查看当前服务器启用的模组。', False),
                    (' modscreatetutorial 模组教程', '想自己制作模组？查看完整开发教程！', False),
                ],
                'footer': '第 6/6 页  音乐 & 其他',
            },
        ],
    },
    'ja': {
        'title': ' FSBot チュートリアル',
        'color': 0x5865F2,
        'pages': [
            {
                'title': 'FSBotへようこそ！',
                'fields': [
                    (' daily デイリーチェックイン', '毎日チェックインしてポイント獲得！連続で報酬アップ！', False),
                    (' balance 残高確認', 'ポイント・レベル・経験値を確認。', False),
                    (' rank ランクカード', 'あなたのレベルカードを表示。', False),
                    (' leaderboard ランキング', '月間ポイントランキング。毎月1日にトップ3に豪華報酬！', False),
                ],
                'footer': 'ページ 1/6  基本',
            },
            {
                'title': '才能 & ショップ',
                'fields': [
                    (' talents 才能ツリー', '4つの才能：幸運・富・知恵・魅力。', False),
                    (' upgrade 才能アップグレード', 'ポイントを消費して才能を強化。', False),
                    (' pointshop ポイントショップ', 'ポイントでアイテムと交換。', False),
                    (' redeem 交換', 'アイテムIDを入力して交換。', False),
                    (' transfer 送金', '他のユーザーにポイントを送る。', False),
                ],
                'footer': 'ページ 2/6  才能 & ショップ',
            },
            {
                'title': 'ミニゲーム',
                'fields': [
                    (' games ゲーム一覧', '全ミニゲームと報酬を表示。', False),
                    (' rps じゃんけん  ·  guess 数字当て  ·  dice サイコロ', '勝てばポイント獲得！', False),
                    (' battle / battle2 対戦', 'メンバーとPK！', False),
                    (' slot スロット', '運試し！3つ揃えれば大当たり！', False),
                    (' idiom 四字熟語', '四字熟語しりとり。', False),
                    (' minesweeper マインスイーパー', '古典的なマインスイーパー。爆弾に注意！', False),
                ],
                'footer': 'ページ 3/6  ミニゲーム',
            },
            {
                'title': 'マルチプレイヤーゲーム',
                'fields': [
                    (' russian デビルルーレット', 'スリル満点！最後まで生き残れるか？', False),
                    (' uno UNOカード', '古典UNO、多人対戦対応！', False),
                    (' werewolf 人狼', '夜のDM + 昼の投票、完全な人狼体験。4-12人。', False),
                    (' quoridor コリドール', '壁で相手を防ぐか、ゴールへ急ぐか！', False),
                ],
                'footer': 'ページ 4/6  マルチプレイヤー',
            },
            {
                'title': 'ボードゲーム (勝者 +20 ポイント)',
                'fields': [
                    (' c4 四目並べ  ·  gomoku 五目並べ', '古典ボードゲーム。', False),
                    (' go 囲碁  ·  checkers チェッカー', '伝統的な盤上ゲーム。', False),
                    (' animal 動物将棋', '象ライオン虎豹狼犬猫鼠、鼠が象に勝つ！', False),
                    (' ludo すごろく', '4人プレイ、踏まれたらスタートに戻る。', False),
                    (' xiangqi 中国象棋  ·  chess チェス', '完全ルール対応。', False),
                    ('使い方', 'コマンド + @対戦相手 で開始。例: /c4 @player', False),
                ],
                'footer': 'ページ 5/6  ボードゲーム',
            },
            {
                'title': '音楽ボット & その他',
                'fields': [
                    ('音楽コマンド (プレフィックス !)', '!play 再生  !search 検索  !batch 一括追加\n!skip スキップ  !queue キュー  !nowplaying 再生中\n!pause !resume 一時停止/再開  !volume 音量\n!loop ループ  !shuffle シャッフル  !disconnect 切断', False),
                    ('対応音源', 'Bilibili動画/分割P/au番号  ·  YouTube(プロキシ要)\n!batch は | または改行区切り、最大20曲', False),
                    (' redpacket 赤い封筒', 'ポイント赤い封筒、運最好ランキングあり！', False),
                    (' role ゲームロール', 'ゲームロールの取得/削除。', False),
                    (' listmods MOD一覧', 'サーバーの有効なMODを表示。', False),
                    (' modscreatetutorial MOD作成', 'MODを作りたい？完全な開発チュートリアル！', False),
                ],
                'footer': 'ページ 6/6  音楽 & その他',
            },
        ],
    },
    'fr': {
        'title': ' Tutoriel FSBot',
        'color': 0x5865F2,
        'pages': [
            {
                'title': 'Bienvenue sur FSBot !',
                'fields': [
                    (' daily Check-in quotidien', 'Connectez-vous chaque jour pour des points ! Bonus de série !', False),
                    (' balance Solde', 'Voir vos points, niveau et XP.', False),
                    (' rank Carte de rang', 'Affichez votre carte de niveau.', False),
                    (' leaderboard Classement', 'Classement mensuel. Top 3 récompensé le 1er du mois !', False),
                ],
                'footer': 'Page 1/6  Bases',
            },
            {
                'title': 'Talents & Boutique',
                'fields': [
                    (' talents Arbre de talents', '4 talents : Chance, Fortune, Sagesse, Charisme.', False),
                    (' upgrade Améliorer', 'Dépensez des points pour améliorer vos talents.', False),
                    (' pointshop Boutique', 'Échangez vos points contre des objets.', False),
                    (' redeem Échanger', 'Entrez l\'ID de l\'objet à échanger.', False),
                    (' transfer Transfert', 'Envoyez des points à un autre utilisateur.', False),
                ],
                'footer': 'Page 2/6  Talents & Boutique',
            },
            {
                'title': 'Mini-jeux',
                'fields': [
                    (' games Liste', 'Voir tous les mini-jeux et récompenses.', False),
                    (' rps Pierre-Feuille-Ciseaux  ·  guess Nombre  ·  dice Dés', 'Gagnez pour des points !', False),
                    (' battle / battle2 Combat', 'Affrontez d\'autres membres !', False),
                    (' slot Machine à sous', 'Tentez votre chance, 3 identiques = gros lot !', False),
                    (' idiom Idiomes', 'Chaîne d\'idiomes chinois.', False),
                    (' minesweeper Démineur', 'Classique démineur, attention aux bombes !', False),
                ],
                'footer': 'Page 3/6  Mini-jeux',
            },
            {
                'title': 'Jeux multijoueurs',
                'fields': [
                    (' russian Roulette du Diable', 'Thrill garanti ! Qui survivra ?', False),
                    (' uno UNO', 'UNO classique, multijoueur !', False),
                    (' werewolf Loup-Garou', 'DM nocturne + vote diurne. 4-12 joueurs.', False),
                    (' quoridor Quoridor', 'Bloquez l\'adversaire ou foncez au but !', False),
                ],
                'footer': 'Page 4/6  Multijoueur',
            },
            {
                'title': 'Jeux de plateau (gagnant +20 points)',
                'fields': [
                    (' c4 Puissance 4  ·  gomoku Gomoku', 'Jeux classiques, prise en main rapide.', False),
                    (' go Go  ·  checkers Dames', 'Jeux traditionnels.', False),
                    (' animal Échecs des animaux', 'Éléphant>Lion>Tigre>...>Souris, la souris bat l\'éléphant !', False),
                    (' ludo Jeu de petits chevaux', '4 joueurs, écrasez = retour au départ.', False),
                    (' xiangqi Xiangqi  ·  chess Échecs', 'Règles complètes.', False),
                    ('Utilisation', 'Commande + @adversaire. Ex: /c4 @player', False),
                ],
                'footer': 'Page 5/6  Jeux de plateau',
            },
            {
                'title': 'Bot musical & Autres',
                'fields': [
                    ('Commandes musicales (préfixe !)', '!play Jouer  !search Rechercher  !batch Ajout multiple\n!skip Passer  !queue File  !nowplaying En cours\n!pause !resume Pause/Reprendre  !volume Volume\n!loop Boucle  !shuffle Aléatoire  !disconnect Déconnecter', False),
                    ('Sources audio', 'Bilibili vidéo/P multiples/au  ·  YouTube (proxy requis)\n!batch séparé par | ou saut de ligne, max 20', False),
                    (' redpacket Enveloppe rouge', 'Enveloppe de points, meilleur tirage classé !', False),
                    (' role Rôle de jeu', 'Obtenir/supprimer un rôle de jeu.', False),
                    (' listmods Liste des mods', 'Voir les mods activés sur ce serveur.', False),
                    (' modscreatetutorial Tutoriel MOD', 'Envie de créer un mod ? Tutoriel complet !', False),
                ],
                'footer': 'Page 6/6  Musique & Autres',
            },
        ],
    },
    'en': {
        'title': ' FSBot Beginner\'s Guide',
        'color': 0x5865F2,
        'pages': [
            {
                'title': 'Welcome to FSBot!',
                'fields': [
                    (' daily Daily Check-in', 'Check in every day for points! Streak bonuses apply!', False),
                    (' balance Balance', 'View your points, level, and XP.', False),
                    (' rank Rank Card', 'View your level card with progress.', False),
                    (' leaderboard Leaderboard', 'Monthly points ranking. Top 3 rewarded on the 1st!', False),
                ],
                'footer': 'Page 1/6  Basics',
            },
            {
                'title': 'Talents & Shop',
                'fields': [
                    (' talents Talent Tree', '4 talents: Luck, Fortune, Wisdom, Charisma.\nDifferent talents affect game rewards, XP, etc.', False),
                    (' upgrade Upgrade', 'Spend points to level up talents.', False),
                    (' pointshop Point Shop', 'Browse shop items, redeem with points.', False),
                    (' redeem Redeem', 'Enter item ID to redeem.', False),
                    (' transfer Transfer', 'Send points to another user.', False),
                ],
                'footer': 'Page 2/6  Talents & Shop',
            },
            {
                'title': 'Mini Games',
                'fields': [
                    (' games Game List', 'View all available mini games and rewards.', False),
                    (' rps RPS  ·  guess Number  ·  dice Dice', 'Classic trio, win for points!', False),
                    (' battle / battle2 Battle', 'Pseudo PvP or real member battle!', False),
                    (' slot Slot Machine', 'Try your luck, 3 matching = jackpot!', False),
                    (' idiom Idiom Chain', 'Chinese idiom chain game.', False),
                    (' minesweeper Minesweeper', 'Classic minesweeper, watch out for bombs!', False),
                ],
                'footer': 'Page 3/6  Mini Games',
            },
            {
                'title': 'Multiplayer Games',
                'fields': [
                    (' russian Devil\'s Roulette', 'Thrilling roulette, who survives last?', False),
                    (' uno UNO Cards', 'Classic UNO, supports multiplayer!', False),
                    (' werewolf Werewolf', 'Night DM + day vote, full werewolf experience. 4-12 players.', False),
                    (' quoridor Quoridor', 'Block opponents or rush to the goal!\nSupports custom rules and 4-player mode.', False),
                ],
                'footer': 'Page 4/6  Multiplayer',
            },
            {
                'title': 'Board Games (winner +20 points)',
                'fields': [
                    (' c4 Connect Four  ·  gomoku Gomoku', 'Classic board games, quick to learn.', False),
                    (' go Go  ·  checkers Checkers', 'Traditional board games.', False),
                    (' animal Animal Chess', 'Elephant>Lion>Tiger>...>Mouse, mouse beats elephant!', False),
                    (' ludo Ludo', '4-player, land on opponent = back to start.', False),
                    (' xiangqi Chinese Chess  ·  chess Chess', 'Full rules supported.', False),
                    ('Usage', 'Command + @opponent to start. Ex: /c4 @player', False),
                ],
                'footer': 'Page 5/6  Board Games',
            },
            {
                'title': 'Music Bot & More',
                'fields': [
                    ('Music Commands (prefix !)', '!play Play  !search Search  !batch Batch add\n!skip Skip  !queue Queue  !nowplaying Now Playing\n!pause !resume Pause/Resume  !volume Volume\n!loop Loop  !shuffle Shuffle  !disconnect Disconnect', False),
                    ('Audio Sources', 'Bilibili video/multi-P/au  ·  YouTube (proxy required)\n!batch uses | or newlines, max 20 songs', False),
                    (' redpacket Red Packet', 'Points red packet, best draw ranked!', False),
                    (' role Game Role', 'Get or remove a game role.', False),
                    (' listmods Mods List', 'View enabled mods on this server.', False),
                    (' modscreatetutorial Mod Tutorial', 'Want to make your own mod? Full dev tutorial!', False),
                ],
                'footer': 'Page 6/6  Music & More',
            },
        ],
    },
}


# ══════════════════════════════════════════════
# 分页按钮 View
# ══════════════════════════════════════════════

class TutorialView(discord.ui.View):
    def __init__(self, lang: str, user_id: int):
        super().__init__(timeout=300)
        self.lang = lang
        self.user_id = user_id
        self.page = 0
        self.data = TUTORIAL_DATA.get(lang, TUTORIAL_DATA['en'])
        self.max_page = len(self.data['pages'])

    def build_embed(self) -> discord.Embed:
        page_data = self.data['pages'][self.page]
        embed = discord.Embed(
            title=page_data['title'],
            color=self.data['color']
        )
        for name, value, inline in page_data['fields']:
            embed.add_field(name=name, value=value, inline=inline)
        embed.set_footer(text=page_data['footer'])
        return embed

    async def update_page(self, interaction: discord.Interaction):
        self.prev_btn.disabled = (self.page == 0)
        self.next_btn.disabled = (self.page == self.max_page - 1)
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label='◀', style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your tutorial session!", ephemeral=True)
            return
        if self.page > 0:
            self.page -= 1
            await self.update_page(interaction)

    @discord.ui.button(label='▶', style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your tutorial session!", ephemeral=True)
            return
        if self.page < self.max_page - 1:
            self.page += 1
            await self.update_page(interaction)

    @discord.ui.button(label='✕', style=discord.ButtonStyle.danger)
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your tutorial session!", ephemeral=True)
            return
        await interaction.response.edit_message(view=None)
        self.stop()


# ══════════════════════════════════════════════
# Cog
# ══════════════════════════════════════════════

class TutorialCog(commands.Cog, name="Tutorial"):
    """新手教程命令包"""

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print("[Cog:Tutorial] 已加载")

    @app_commands.command(name="tutorial", description="查看新手教程 / View beginner's guide / チュートリアル / Tutoriel")
    async def tutorial(self, interaction: discord.Interaction):
        """分页多语言新手教程"""
        locale = str(interaction.locale)
        if locale.startswith('zh'):
            lang = 'zh'
        elif locale.startswith('ja'):
            lang = 'ja'
        elif locale.startswith('fr'):
            lang = 'fr'
        else:
            lang = 'en'

        view = TutorialView(lang, interaction.user.id)
        embed = view.build_embed()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot):
    await bot.add_cog(TutorialCog(bot))
