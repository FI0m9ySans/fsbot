"""
更新后的 /modscreatetutorial 命令 — 涵盖全部 15 个扩展功能
"""
import os

async def modscreatetutorial_slash(interaction: discord.Interaction):
    locale = str(interaction.locale)
    lang = 'zh' if locale.startswith('zh') else ('ja' if locale.startswith('ja') else ('fr' if locale.startswith('fr') else 'en'))

    # 完整示例 JSON（包含基础功能 + 扩展功能）
    example_json = '''{
  "name": "my_full_mod",
  "version": "1.0",
  "description": "完整功能示例模组",
  "commands": [
    {
      "name": "hello",
      "description": "打个招呼",
      "response": {
        "zh": "你好！",
        "en": "Hello!"
      }
    }
  ],
  "currencies": [
    {
      "name": "金币",
      "symbol": "🟡",
      "description": "冒险者金币",
      "earn_methods": []
    }
  ],
  "items": [
    {
      "name": "木剑",
      "type": "weapon",
      "description": "攻击力+5",
      "properties": {"damage": 5},
      "transferable": true
    }
  ],
  "shops": [
    {
      "name": "冒险者商店",
      "description": "购买冒险装备",
      "items": [
        {"item_id": "木剑", "price": 100, "currency_type": "points"}
      ]
    }
  ],
  "red_packets": [
    {
      "name": "新人红包",
      "total_amount": 500,
      "quantity": 10,
      "description": "欢迎新人！"
    }
  ],
  "custom_channels": [
    {"channel_id": 123456789012345678, "description": "游戏频道"}
  ],
  "custom_roles": [
    {"role_id": 123456789012345678, "description": "VIP角色"}
  ],
  "dependencies": [
    {"name": "base_mod", "type": "requires"}
  ]
}'''

    if lang == 'zh':
        embed = discord.Embed(
            title='📖 FSBot 模组制作教程 v2.0',
            description='`.fsbods` 文件是 **JSON 格式**的模组文件，放入 `mods/` 文件夹后自动加载。\n**v2.0 新增 15 个扩展功能！**',
            color=discord.Color.blurple()
        )
        embed.add_field(name='📁 文件存放位置', value='`mods/` 目录（与 `main.py` 同级）', inline=False)
        embed.add_field(name='🔑 必填字段', value='`name` — 模组唯一名称（英文，不含空格）\n`version` — 版本号（可选）\n`description` — 模组描述（可选）', inline=False)
        
        # 基础功能
        embed.add_field(name='⚡ 基础功能', value=(
            '• `commands` — 新增斜杠命令（支持多语言 response）\n'
            '• `auto_messages` — 定时自动消息（需 `channel_id` + `interval_hours`）\n'
            '• `replies` — 关键词自动回复（`match`: `contains`/`startswith`/`exact`）'
        ), inline=False)
        
        # 扩展功能
        embed.add_field(name='🆕 v2.0 扩展功能（15个）', value=(
            '1. `currencies` — 创建自定义货币\n'
            '2. `items` — 创建自定义物品（支持 `type`: box/weapon/food/tool/...）\n'
            '3. `shops` — 创建自定义商店+商品\n'
            '4. `red_packets` — 创建红包（用户可领取）\n'
            '5. `storage_bags` — 储物袋（通过 SDK API 使用）\n'
            '6. `custom_games` — 记录自定义游戏（下注/赢家）\n'
            '7. `notes` — 记事本（通过 SDK API 使用）\n'
            '8. `calc_history` — 计算器历史（通过 SDK API 使用）\n'
            '9. `todos` — 待办事项（通过 SDK API 使用）\n'
            '10. `custom_channels` — 自定义频道ID（模组专用）\n'
            '11. `custom_roles` — 自定义身份组ID（模组专用）\n'
            '12. `dependencies` — 父子模组依赖（`requires`/`optional`）\n'
            '13. `mass_send` — 群发货币（通过 SDK API 调用）\n'
            '14. `item.transferable` — 物品转交控制（创建时设置）\n'
            '15. `commands[].action` — 动态命令（调用 SDK 函数，开发中）'
        ), inline=False)
        
        embed.add_field(name='📝 完整示例（部分）', value=f'```json\n{example_json[:800]}...\n```\n（完整示例请在附件教程中查看）', inline=False)
        embed.add_field(name='📤 上传方式', value='使用 `/uploadmods` 命令上传 `.fsbods` 文件\n或直接将文件放入服务器 `mods/` 文件夹', inline=False)
        embed.set_footer(text='详细教程请在附件中查看 SDK_TUTORIAL_FULL.md | 内置功能无法通过模组删除。')

    elif lang == 'ja':
        embed = discord.Embed(
            title='📖 FSBot モッド作成チュートリアル v2.0',
            description='`.fsbods` ファイルは **JSON形式** のモッドファイルです。`mods/` フォルダに入れると自動的に読み込まれます。\n**v2.0 で 15 の拡張機能が追加されました！**',
            color=discord.Color.blurple()
        )
        embed.add_field(name='📁 ファイルの場所', value='`mods/` ディレクトリ（`main.py` と同じ階層）', inline=False)
        embed.add_field(name='🔑 必須フィールド', value='`name` — モッドの一意の名前（英語、スペースなし）', inline=False)
        embed.add_field(name='⚡ 基本機能', value=(
            '• `commands` — スラッシュコマンドの追加\n'
            '• `auto_messages` — 自動定期メッセージ\n'
            '• `replies` — キーワード自動返信'
        ), inline=False)
        embed.add_field(name='🆕 v2.0 拡張機能（15個）', value=(
            '1. `currencies` — カスタム通貨\n'
            '2. `items` — カスタムアイテム\n'
            '3. `shops` — カスタムショップ\n'
            '4. `red_packets` — 紅包（お年玉）システム\n'
            '5. `storage_bags` — 保管袋\n'
            '6. `custom_games` — カスタムゲーム記録\n'
            '7. `notes` — ノート\n'
            '8. `calc_history` — 計算履歴\n'
            '9. `todos` — やることリスト\n'
            '10. `custom_channels` — カスタムチャンネルID\n'
            '11. `custom_roles` — カスタムロールID\n'
            '12. `dependencies` — モッド依存関係\n'
            '13. `mass_send` — 一括送信\n'
            '14. `item.transferable` — アイテム転送制御\n'
            '15. `commands[].action` — 動的コマンド'
        ), inline=False)
        embed.set_footer(text='詳細なチュートリアルは添付の SDK_TUTORIAL_FULL.md をご覧ください。')

    elif lang == 'fr':
        embed = discord.Embed(
            title='📖 Tutoriel de création de mod FSBot v2.0',
            description='Les fichiers `.fsbods` sont des mods en **format JSON**. Placez-les dans le dossier `mods/` pour les charger automatiquement.\n**v2.0 ajoute 15 nouvelles fonctionnalités d\'extension !**',
            color=discord.Color.blurple()
        )
        embed.add_field(name='📁 Emplacement', value='Dossier `mods/` (à côté de `main.py`)', inline=False)
        embed.add_field(name='🔑 Champ obligatoire', value='`name` — Nom unique du mod (en anglais, sans espace)', inline=False)
        embed.add_field(name='⚡ Fonctions de base', value=(
            '• `commands` — Ajout de commandes slash\n'
            '• `auto_messages` — Messages automatiques planifiés\n'
            '• `replies` — Réponses automatiques par mot-clé'
        ), inline=False)
        embed.add_field(name='🆕 v2.0 Fonctionnalités d\'extension (15)', value=(
            '1. `currencies` — Monnaie personnalisée\n'
            '2. `items` — Objets personnalisés\n'
            '3. `shops` — Boutique personnalisée\n'
            '4. `red_packets` — Système de enveloppes rouges\n'
            '5. `storage_bags` — Sacs de stockage\n'
            '6. `custom_games` — Jeux personnalisés\n'
            '7. `notes` — Notes\n'
            '8. `calc_history` — Historique calculateur\n'
            '9. `todos` — Tâches\n'
            '10. `custom_channels` — ID de canal personnalisé\n'
            '11. `custom_roles` — ID de rôle personnalisé\n'
            '12. `dependencies` — Dépendances de mods\n'
            '13. `mass_send` — Envoi en masse\n'
            '14. `item.transferable` — Contrôle de transfert\n'
            '15. `commands[].action` — Commandes dynamiques'
        ), inline=False)
        embed.set_footer(text='Voir le tutoriel complet dans le fichier SDK_TUTORIAL_FULL.md attaché.')

    else:
        embed = discord.Embed(
            title='📖 FSBot Mod Creation Tutorial v2.0',
            description='`.fsbods` files are **JSON-format** mod files. Place them in the `mods/` folder to auto-load.\n**v2.0 adds 15 new extension features!**',
            color=discord.Color.blurple()
        )
        embed.add_field(name='📁 File Location', value='`mods/` directory (same level as `main.py`)', inline=False)
        embed.add_field(name='🔑 Required Field', value='`name` — Unique mod name (English, no spaces)', inline=False)
        embed.add_field(name='⚡ Basic Features', value=(
            '• `commands` — Add slash commands\n'
            '• `auto_messages` — Scheduled auto messages\n'
            '• `replies` — Keyword auto-reply'
        ), inline=False)
        embed.add_field(name='🆕 v2.0 Extension Features (15)', value=(
            '1. `currencies` — Custom currency\n'
            '2. `items` — Custom items\n'
            '3. `shops` — Custom shops\n'
            '4. `red_packets` — Red packet system\n'
            '5. `storage_bags` — Storage bags\n'
            '6. `custom_games` — Custom game records\n'
            '7. `notes` — Notes\n'
            '8. `calc_history` — Calculator history\n'
            '9. `todos` — Todo list\n'
            '10. `custom_channels` — Custom channel IDs\n'
            '11. `custom_roles` — Custom role IDs\n'
            '12. `dependencies` — Mod dependencies\n'
            '13. `mass_send` — Mass send currency\n'
            '14. `item.transferable` — Item transfer control\n'
            '15. `commands[].action` — Dynamic commands'
        ), inline=False)
        embed.add_field(name='📤 Upload', value='Use `/uploadmods` to upload a `.fsbods` file\nOr place it directly in the server\'s `mods/` folder', inline=False)
        embed.set_footer(text='See full tutorial in attached SDK_TUTORIAL_FULL.md | Built-in features cannot be removed by mods.')

    # 发送 embed + 教程文件
    tutorial_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mods', 'SDK_TUTORIAL_FULL.md')
    if os.path.exists(tutorial_path):
        file = discord.File(tutorial_path, filename='SDK_TUTORIAL_FULL.md')
        await interaction.response.send_message(embed=embed, file=file)
    else:
        await interaction.response.send_message(embed=embed)
