import sys
print("[Main] Python executable:", sys.executable)
print("[Main] sys.path[0]:", sys.path[0])

import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import opencc
import sqlite3
import os
from datetime import datetime, timedelta

# ==========================================
# 0.5 模组 SDK 扩展 (Mod SDK Extensions)
# ==========================================
import mod_sdk
import mod_system
import sdk_commands

# ── Web Dashboard + Music + Cross-Guild 模块 ──
import web_dashboard
import music_bot
import cross_guild
import deltarune_quiz
import board_games
import ai_chat
import ai_image


# ── Cog 导入 ──
from cogs.admin import setup as setup_admin
from cogs.user_system import setup as setup_user
from cogs.shop import setup as setup_shop
from cogs.talents import setup as setup_talents
from cogs.games import setup as setup_games
from cogs.big_games import setup as setup_big_games
from cogs.redpacket import setup as setup_redpacket
from cogs.tutorial import setup as setup_tutorial

# ── 数据库层 ──
from utils.db import *
from utils.guards import *


intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)
_ready_done = False  # 防止 on_ready 重连时重复执行

# ── ServerKing 全局锁 (使用 utils.guards 中的共享状态) ──
@bot.tree.interaction_check
async def global_lockdown_check(interaction: discord.Interaction) -> bool:
    """全局命令权限检查：当 ServerKing 锁定时，仅服主不可用（让出权力）"""
    if not get_lockdown_mode():
        return True

    if interaction.command and interaction.command.name == "serverking":
        return True

    if interaction.user.id == OWNER_ID:
        print(f"[ServerKing] 拦截服主命令: {interaction.command.name if interaction.command else 'unknown'}")
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "👑 ServerKing 模式已开启 — 您已主动交出权力，所有命令暂不可用。\n"
                    "使用 `/serverking False` 恢复。",
                    ephemeral=True
                )
        except Exception:
            pass
        return False

    return True

# ── 前缀命令 ──
@bot.command(name="clear")
async def clear(ctx, amount: int = 5):
    await ctx.channel.purge(limit=amount + 1)
    msg = await ctx.send(f'✅ 已清理 {amount} 条消息！')
    await asyncio.sleep(3)
    await msg.delete()

# ==========================================
# 3. 机器人上线提示 & 同步斜杠命令
# ==========================================
@bot.event
async def on_ready():
    global _ready_done
    if _ready_done:
        print(f"[Main] on_ready 跳过（已执行过，当前为重连）")
        return
    _ready_done = True

    print(f'成功登录为: {bot.user}')

    # ── 加载 Cogs ──
    await setup_admin(bot)
    await setup_user(bot)
    await setup_shop(bot)
    await setup_talents(bot)
    await setup_games(bot)
    await setup_big_games(bot)
    await setup_redpacket(bot)
    await setup_tutorial(bot)
    shop_cog = bot.get_cog('Shop')
    if shop_cog:
        shop_cog.start_tasks()
    print('[Main] 所有 Cogs 已加载')


    # 初始化模组 SDK 扩展（先初始化 SDK，再注册命令）
    mod_sdk.init_mod_sdk(cursor, conn, bot)
    print("[Main] 模组 SDK 已初始化")

    # 初始化模组系统加载器（注册 mod 命令）
    mod_system.init_mod_system(bot, cursor, conn, mod_sdk)
    print("[Main] 模组系统已初始化")

    # 初始化通用 SDK 命令
    sdk_commands.init_sdk_commands(bot, cursor, conn, mod_sdk)
    print("[Main] 通用 SDK 命令已初始化")

    # 启动自动化引擎
    try:
        mod_sdk.SDK_API['automation_start_engine'](bot)
    except Exception as e:
        print(f"[Main] 自动化引擎启动失败: {e}")

    # ── Web Dashboard 初始化 ──
    try:
        import time as _time
        web_dashboard.init_web_dashboard(bot, 'users.db', mod_sdk, _time.time())
        web_dashboard.start_web_server(host="0.0.0.0", port=8080)
        print("[Main] Web Dashboard 已启动 → http://localhost:8080")
    except Exception as e:
        print(f"[Main] Web Dashboard 启动失败: {e}")

    # ── Music Bot 初始化 ──
    try:
        await music_bot.init_music_bot(bot)
    except Exception as e:
        print(f"[Main] Music 模块初始化失败: {e}")

    # ── Cross-Guild Bridge 初始化 ──
    try:
        await cross_guild.init_cross_guild(bot)
    except Exception as e:
        print(f"[Main] Cross-Guild 模块初始化失败: {e}")

    # ── Deltarune 问答初始化 ──
    try:
        await deltarune_quiz.init_quiz(bot)
    except Exception as e:
        print(f"[Main] Deltarune 问答模块初始化失败: {e}")

    # ── 棋盘游戏注册 ──
    try:
        board_games.register_board_games(bot, add_points_cb=add_points)
    except Exception as e:
        print(f"[Main] 棋盘游戏模块初始化失败: {e}")

    # ── AI 聊天初始化 ──
    try:
        await ai_chat.init_ai_chat(bot)
    except Exception as e:
        print(f"[Main] AI 聊天模块初始化失败: {e}")

    # ── AI 图像生成初始化 ──
    try:
        await ai_image.init_image_gen(bot)
    except Exception as e:
        print(f"[Main] AI 图像生成模块初始化失败: {e}")

    # 所有命令注册完毕，最后才同步到 Discord
    if not hasattr(bot, '_synced'):
        bot._synced = False
    if not bot._synced:
        async def _sync_all_commands():
            try:
                from datetime import date
                today = date.today().isoformat()

                # 全局命令同步（只做一次，全局命令本就对所有服务器生效）
                last_global_sync = get_meta('global_sync_date')
                if last_global_sync == today:
                    print(f"[Main] 今日已全局同步过，跳过（避免超出 Discord 每日 200 命令创建限制）")
                    bot._synced = True
                else:
                    synced = await bot.tree.sync()
                    set_meta('global_sync_date', today)
                    bot._synced = True
                    print(f"[Main] 全局同步了 {len(synced)} 个斜杠命令！（首次最多1小时生效）")

                # guild-specific 命令由 mod_system._sync_all_guilds() 负责
                # main.py 不再做 copy_global_to + per-guild sync（那会导致 88×N 次命令创建，撞上200上限）
            except Exception as e:
                print(f"[Main] 命令同步失败: {e}")
        asyncio.create_task(_sync_all_commands())

# ==========================================
# 3.4 新成员欢迎
# ==========================================
WELCOME_CHANNEL_ID = 1518352725459337256

@bot.event
async def on_member_join(member: discord.Member):
    """新成员加入时发送欢迎消息"""
    channel = bot.get_channel(WELCOME_CHANNEL_ID)
    if not channel:
        print(f"[Welcome] ⚠️ 找不到欢迎频道 ID: {WELCOME_CHANNEL_ID}")
        return

    guild = member.guild
    member_count = guild.member_count

    embed = discord.Embed(
        title="🎉 欢迎新成员！",
        description=f"**{member.mention}** 加入了 **{guild.name}**！\n你是第 **{member_count}** 位成员。",
        color=discord.Color.blurple(),
        timestamp=datetime.now()
    )
    embed.add_field(
        name="📌 快速开始",
        value="输入 `/tutorial` 查看完整新手教程！\n`/daily` 每日签到  ·  `/games` 小游戏  ·  `/leaderboard` 排行榜",
        inline=False
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text=f"ID: {member.id}")

    try:
        await channel.send(embed=embed)
        print(f"[Welcome] 已欢迎新成员 {member.display_name} 在 {guild.name}")
    except Exception as e:
        print(f"[Welcome] 发送欢迎消息失败: {e}")

# ==========================================
# 3.5 全局斜杠命令错误处理
# ==========================================
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    """全局斜杠命令错误处理器，防止 NotFound 等异常导致完整 traceback"""
    if isinstance(error, app_commands.CommandInvokeError):
        original = error.original
        if isinstance(original, discord.NotFound):
            # 交互令牌过期或失效，无法回复，静默处理
            print(f"[WARN] 交互已失效 (NotFound): {error.command.name if error.command else 'unknown'} - 用户可能关闭了弹窗")
            return
        if isinstance(original, discord.InteractionResponded):
            # 已经回复过了，尝试 followup
            try:
                await interaction.followup.send("❌ 发生错误 / An error occurred", ephemeral=True)
            except:
                pass
            return
    # 其他错误尝试通知用户
    try:
        if interaction.response.is_done():
            await interaction.followup.send(f"❌ 发生错误: {error}", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ 发生错误: {error}", ephemeral=True)
    except:
        pass
    print(f"[ERROR] 斜杠命令错误: {error}")


# ==========================================
# 4. 多语言欢迎新成员
# ==========================================
@bot.event
async def on_member_join(member):
    # 使用你指定的频道 ID
    welcome_channel_id = 1516860607217926316
    channel = member.guild.get_channel(welcome_channel_id)
    
    if channel:
        welcome_msg = f"""
🎉 **欢迎 {member.mention} 加入 FI0m9ySans's Community Hub！**
🎉 **Welcome {member.mention} to FI0m9ySans's Community Hub!**
🎉 **{member.mention} さん、FI0m9ySansのコミュニティハブへようこそ！**
🎉 **Bienvenue {member.mention} dans le Community Hub de FI0m9ySans !**

🇨🇳 欢迎来到我们的多语言游戏社区！
🇬🇧 Welcome to our multilingual gaming community!
🇯🇵 私たちの多言語ゲームコミュニティへようこそ！
🇫🇷 Bienvenue dans notre communauté de jeux multilingue !

📋 **快速开始 / Quick Start / クイックスタート / Démarrage rapide:**
• 输入 `/tutorial` 查看完整新手教程！ / Type `/tutorial` for a full guide! / `/tutorial` で完全ガイド！ / Tapez `/tutorial` pour le guide complet !
• 查看 #rules 了解规则
• 填写加入获批的问题获取游戏身份组
• 加入前选择你喜欢的语言频道聊天
-------
• Check #rules to see the rules
• Fill out the approved questions to get the game role
• Choose your favorite language channel to chat before joining
-------
• #rules を見てルールを確認する
• 加入承認の質問に答えてゲームの役職を取得する
• 加入前に好きな言語チャンネルでチャットを選ぶ
-------
• Consultez #rules pour connaître les règles
• Remplissez les questions d'adhésion approuvées pour obtenir le rôle de jeu
• Choisissez le canal linguistique que vous aimez avant de rejoindre pour discuter
-------

Enjoy your stay! 玩得开心！楽しんでね！Amuse-toi bien !
        """
        await channel.send(welcome_msg)
        
# ==========================================
# 5. 自动语言检测 (opencc)
# ==========================================
# 初始化 opencc 转换器
converter_t2s = opencc.OpenCC('t2s')
converter_s2t = opencc.OpenCC('s2t')

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # AI 聊天 (.aichat)
    if message.content.strip().startswith(".aichat"):
        handled = await ai_chat.handle_aichat(message, bot)
        if handled:
            return

    # AI 图像生成 (.draw / .outpaint)
    if message.content.strip().lower().startswith((".draw", ".outpaint")):
        handled = await ai_image.handle_draw(message, bot)
        if handled:
            return

    CHINESE_MSG_ID = 1516904688572825791
    TRAD_CHINESE_MSG_ID = 1517123618461712444
    
    if message.channel.id == CHINESE_MSG_ID:
        if converter_t2s.convert(message.content) != message.content:
            await message.channel.send(f"{message.author.mention} ⚠️ 检测到繁体中文，请移步 <#{TRAD_CHINESE_MSG_ID}> 频道哦！")
            return
    elif message.channel.id == TRAD_CHINESE_MSG_ID:
        if converter_s2t.convert(message.content) != message.content:
            await message.channel.send(f"{message.author.mention} ⚠️ 检测到简体中文，请移步 <#{CHINESE_MSG_ID}> 频道哦！")
            return

    # 模组消息规则处理（keyword_reply / message_rules）
    await mod_system.handle_message(message)

    # 跨服桥接消息转发
    await cross_guild.handle_cross_guild_message(message)

    # 消息获得经验值（排除命令消息）
    if not message.content.startswith(bot.command_prefix):
        # 应用智慧天赋：每级 +5% 经验
        wisdom = get_talents(message.author.id)[3]
        exp_gain = int(10 * (1 + wisdom * 0.05))
        leveled_up, new_level, new_exp = add_exp(message.author.id, exp_gain)
        if leveled_up:
            asyncio.create_task(message.channel.send(
                f"🎉 {message.author.mention} Level Up! | 升级啦！| レベルアップ！| Niveau supérieur !\n"
                f"❤️ Love Level: **{new_level}** 🆙"
            ))

    # timets 时区转换功能
    if '{timets' in message.content.lower():
        import re, pytz
        from datetime import datetime as dt
        match = re.search(r'\{timets[:\s]*([^}]*)\}', message.content, re.IGNORECASE)
        if match:
            time_str = match.group(1).strip()
            now = dt.now()
            try:
                if time_str:
                    # 尝试解析时间
                    for fmt in ("%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M", "%m-%d %H:%M", "%H:%M"):
                        try:
                            t = dt.strptime(time_str, fmt)
                            if fmt == "%H:%M":
                                now = now.replace(hour=t.hour, minute=t.minute)
                            else:
                                now = t
                            break
                        except ValueError:
                            continue
                
                timezones = {
                    "🇨🇳 中国/北京": "Asia/Shanghai",
                    "🇯🇵 日本/东京": "Asia/Tokyo",
                    "🇫🇷 法国/巴黎": "Europe/Paris",
                    "🇬🇧 英国/伦敦": "Europe/London",
                    "🇺🇸 美国/洛杉矶": "America/Los_Angeles",
                    "🇺🇸 美国/纽约": "America/New_York",
                }
                
                tz_labels = {
                    'zh': {"🇨🇳 中国/北京": "Asia/Shanghai", "🇯🇵 日本/东京": "Asia/Tokyo", "🇫🇷 法国/巴黎": "Europe/Paris", "🇬🇧 英国/伦敦": "Europe/London", "🇺🇸 美国/洛杉矶": "America/Los_Angeles", "🇺🇸 美国/纽约": "America/New_York"},
                    'ja': {"🇨🇳 中国/北京": "Asia/Shanghai", "🇯🇵 日本/東京": "Asia/Tokyo", "🇫🇷 フランス/パリ": "Europe/Paris", "🇬🇧 英国/ロンドン": "Europe/London", "🇺🇸 米国/ロサンゼルス": "America/Los_Angeles", "🇺🇸 米国/ニューヨーク": "America/New_York"},
                    'fr': {"🇨🇳 Chine/Pékin": "Asia/Shanghai", "🇯🇵 Japon/Tokyo": "Asia/Tokyo", "🇫🇷 France/Paris": "Europe/Paris", "🇬🇧 UK/Londres": "Europe/London", "🇺🇸 USA/Los Angeles": "America/Los_Angeles", "🇺🇸 USA/New York": "America/New_York"},
                    'en': {"🇨🇳 China/Beijing": "Asia/Shanghai", "🇯🇵 Japan/Tokyo": "Asia/Tokyo", "🇫🇷 France/Paris": "Europe/Paris", "🇬🇧 UK/London": "Europe/London", "🇺🇸 USA/Los Angeles": "America/Los_Angeles", "🇺🇸 USA/New York": "America/New_York"},
                }
                user_lang = 'zh' if str(message.author.locale).startswith('zh') else ('ja' if str(message.author.locale).startswith('ja') else ('fr' if str(message.author.locale).startswith('fr') else 'en'))
                titles = {'zh': '🌍 Timets - 全球时间', 'ja': '🌍 Timets - 世界時間', 'fr': '🌍 Timets - Heures mondiales', 'en': '🌍 Timets - World Time'}
                footers = {'zh': '原始时间', 'ja': '元の時間', 'fr': 'Heure originale', 'en': 'Original time'}
                embed = discord.Embed(title=titles.get(user_lang, titles['en']), color=discord.Color.blue())
                for name, tz in tz_labels.get(user_lang, tz_labels['en']).items():
                    local = now.astimezone(pytz.timezone(tz))
                    embed.add_field(name=name, value=local.strftime("%Y-%m-%d %H:%M"), inline=True)
                embed.set_footer(text=f"{footers.get(user_lang, footers['en'])}: {time_str or 'now'} | {message.author.display_name}")
                await message.channel.send(embed=embed)
            except Exception as e:
                await message.channel.send(f"❌ 时间解析失败: {e}")

    await bot.process_commands(message)

# ==========================================
# 5.5 反应获得经验值
# ==========================================
@bot.event
async def on_reaction_add(reaction, user):
    if user.bot:
        return
    wisdom = get_talents(user.id)[3]
    exp_gain = int(5 * (1 + wisdom * 0.05))
    leveled_up, new_level, new_exp = add_exp(user.id, exp_gain)
    if leveled_up:
        asyncio.create_task(reaction.message.channel.send(
            f"🎉 {user.mention} Level Up! | 升级啦！| レベルアップ！| Niveau supérieur !\n"
            f"❤️ Love Level: **{new_level}** 🆙"
        ))

# ==========================================
# 5.6 Bot 加入新服务器 — 初始化模组状态
# ==========================================
@bot.event
async def on_guild_join(guild):
    """Bot 加入新服务器时，初始化该服务器的模组状态"""
    mod_system.on_guild_join(guild)

# 13. 小游戏
# ==========================================
# 99. 模组管理命令 (Mod Management Commands)
# ==========================================

# 99.1 列出已加载的模组（按服务器隔离）
@bot.tree.command(name="listmods", description="列出当前服务器的模组 / List mods in this server")
async def listmods_slash(interaction: discord.Interaction):
    """列出当前服务器已加载的模组"""
    locale = str(interaction.locale)
    lang = 'zh' if locale.startswith('zh') else ('ja' if locale.startswith('ja') else ('fr' if locale.startswith('fr') else 'en'))

    if not interaction.guild_id:
        await interaction.response.send_message("❌ 此命令只能在服务器中使用。", ephemeral=True)
        return

    guild_id = interaction.guild_id
    mods = mod_system.list_mods(guild_id)
    all_cache = mod_system.list_available_mods()

    if not mods:
        if lang == 'zh':
            msg = f"📦 当前服务器没有已加载的模组。\n（mods/ 目录共 {len(all_cache)} 个可用模组，用 `/loadmod` 加载）"
        elif lang == 'ja':
            msg = f"📦 このサーバーに読み込まれたモッドはありません。\n（mods/ に {len(all_cache)} 個のモッドがあります）"
        elif lang == 'fr':
            msg = f"📦 Aucun mod chargé sur ce serveur.\n({len(all_cache)} mods disponibles dans mods/)"
        else:
            msg = f"📦 No mods loaded on this server.\n({len(all_cache)} mods available in mods/)"
        await interaction.response.send_message(msg, ephemeral=True)
        return

    if lang == 'zh':
        title = "📦 当前服务器的模组"
        desc = f"已加载 **{len(mods)}** / {len(all_cache)} 个模组：\n\n"
        for mod_name, mod_info in mods.items():
            desc += f"• **{mod_name}** - {mod_info['data'].get('description', '无描述')}\n"
    elif lang == 'ja':
        title = "📦 このサーバーのモッド"
        desc = f"読み込み済み **{len(mods)}** / {len(all_cache)} 個：\n\n"
        for mod_name, mod_info in mods.items():
            desc += f"• **{mod_name}** - {mod_info['data'].get('description', '説明なし')}\n"
    elif lang == 'fr':
        title = "📦 Mods de ce serveur"
        desc = f"Chargés **{len(mods)}** / {len(all_cache)} :\n\n"
        for mod_name, mod_info in mods.items():
            desc += f"• **{mod_name}** - {mod_info['data'].get('description', 'Pas de description')}\n"
    else:
        title = "📦 Mods on this server"
        desc = f"Loaded **{len(mods)}** / {len(all_cache)} mods:\n\n"
        for mod_name, mod_info in mods.items():
            desc += f"• **{mod_name}** - {mod_info['data'].get('description', 'No description')}\n"

    embed = discord.Embed(title=title, description=desc, color=discord.Color.blue())
    await interaction.response.send_message(embed=embed, ephemeral=True)


# 99.2 重新加载模组（按服务器隔离）
@bot.tree.command(name="reloadmod", description="重新加载一个模组 / Reload a mod")
@app_commands.describe(mod_name="模组名称 / Mod name / モッド名 / Nom du mod")
async def reloadmod_slash(interaction: discord.Interaction, mod_name: str):
    """重新加载模组（当前服务器）"""
    locale = str(interaction.locale)
    lang = 'zh' if locale.startswith('zh') else ('ja' if locale.startswith('ja') else ('fr' if locale.startswith('fr') else 'en'))

    if not interaction.guild_id:
        await interaction.response.send_message("❌ 此命令只能在服务器中使用。", ephemeral=True)
        return

    success, msg = mod_system.reload_mod_for_guild(mod_name, interaction.guild_id)
    
    if success:
        if lang == 'zh':
            reply = f"✅ {msg}"
        elif lang == 'ja':
            reply = f"✅ {msg}"
        elif lang == 'fr':
            reply = f"✅ {msg}"
        else:
            reply = f"✅ {msg}"
    else:
        if lang == 'zh':
            reply = f"❌ {msg}"
        elif lang == 'ja':
            reply = f"❌ {msg}"
        elif lang == 'fr':
            reply = f"❌ {msg}"
        else:
            reply = f"❌ {msg}"
    
    await interaction.response.send_message(reply, ephemeral=True)


# 99.25 加载已存在的模组文件（按服务器隔离）
async def loadmod_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    """自动补全：列出 mods/ 下当前服务器未加载的 .fsbods 文件"""
    choices = []
    available = mod_system.list_available_mods()
    guild_id = interaction.guild_id

    for mod_name, mod_info in available.items():
        # 过滤掉当前服务器已加载的
        if guild_id and mod_system.is_mod_loaded_in_guild(mod_name, guild_id):
            continue
        desc = mod_info['data'].get('description', '')[:80]
        label = f"{mod_name} ({os.path.basename(mod_info['file_path'])})"
        if desc:
            label += f" - {desc[:40]}"
        choices.append(app_commands.Choice(name=label[:100], value=mod_name))

    # 模糊过滤
    if current:
        current_lower = current.lower()
        choices = [c for c in choices if current_lower in c.name.lower()]
    return choices[:25]


@bot.tree.command(name="loadmod", description="📂 加载模组到当前服务器 / Load a mod to this server")
@app_commands.describe(mod_name="选择要加载的模组 / Select mod to load")
@app_commands.autocomplete(mod_name=loadmod_autocomplete)
async def loadmod_slash(interaction: discord.Interaction, mod_name: str):
    """加载模组到当前服务器"""
    locale = str(interaction.locale)
    lang = 'zh' if locale.startswith('zh') else ('ja' if locale.startswith('ja') else ('fr' if locale.startswith('fr') else 'en'))

    if not interaction.guild_id:
        await interaction.response.send_message("❌ 此命令只能在服务器中使用。", ephemeral=True)
        return

    guild_id = interaction.guild_id

    # 检查是否已在此服务器加载
    if mod_system.is_mod_loaded_in_guild(mod_name, guild_id):
        msgs = {
            'zh': f'❌ 模组 `{mod_name}` 已经在此服务器加载了！用 `/reloadmod` 重载或 `/unloadmod` 卸载',
            'ja': f'❌ モッド `{mod_name}` はこのサーバーで既にロードされています！',
            'fr': f'❌ Le mod `{mod_name}` est déjà chargé sur ce serveur !',
            'en': f'❌ Mod `{mod_name}` is already loaded on this server! Use `/reloadmod` or `/unloadmod`'
        }
        await interaction.response.send_message(msgs.get(lang, msgs['en']), ephemeral=True)
        return

    success, msg = mod_system.load_mod_for_guild(mod_name, guild_id)
    if success:
        msgs = {
            'zh': f'✅ {msg}',
            'ja': f'✅ {msg}',
            'fr': f'✅ {msg}',
            'en': f'✅ {msg}'
        }
    else:
        msgs = {
            'zh': f'❌ {msg}',
            'ja': f'❌ {msg}',
            'fr': f'❌ {msg}',
            'en': f'❌ {msg}'
        }
    await interaction.response.send_message(msgs.get(lang, msgs['en']), ephemeral=True)


# 99.3 卸载模组（按服务器隔离）
@bot.tree.command(name="unloadmod", description="从当前服务器卸载模组 / Unload a mod from this server")
@app_commands.describe(mod_name="模组名称 / Mod name / モッド名 / Nom du mod")
async def unloadmod_slash(interaction: discord.Interaction, mod_name: str):
    """从当前服务器卸载模组"""
    locale = str(interaction.locale)
    lang = 'zh' if locale.startswith('zh') else ('ja' if locale.startswith('ja') else ('fr' if locale.startswith('fr') else 'en'))

    if not interaction.guild_id:
        await interaction.response.send_message("❌ 此命令只能在服务器中使用。", ephemeral=True)
        return

    success, msg = mod_system.unload_mod_from_guild(mod_name, interaction.guild_id)
    
    if success:
        if lang == 'zh':
            reply = f"✅ {msg}"
        elif lang == 'ja':
            reply = f"✅ {msg}"
        elif lang == 'fr':
            reply = f"✅ {msg}"
        else:
            reply = f"✅ {msg}"
    else:
        if lang == 'zh':
            reply = f"❌ {msg}"
        elif lang == 'ja':
            reply = f"❌ {msg}"
        elif lang == 'fr':
            reply = f"❌ {msg}"
        else:
            reply = f"❌ {msg}"
    
    await interaction.response.send_message(reply, ephemeral=True)


# 99.3 上传模组文件（按服务器隔离）
@bot.tree.command(name="uploadmods", description="📦 上传 .fsbods 模组文件到当前服务器 / Upload .fsbods mod file")
@app_commands.describe(file="选择要上传的 .fsbods 模组文件 / Select .fsbods file")
async def uploadmods_slash(interaction: discord.Interaction, file: discord.Attachment):
    """上传并加载模组文件到当前服务器"""
    await interaction.response.defer(ephemeral=True)
    locale = str(interaction.locale)
    lang = 'zh' if locale.startswith('zh') else ('ja' if locale.startswith('ja') else ('fr' if locale.startswith('fr') else 'en'))

    if not interaction.guild_id:
        await interaction.followup.send("❌ 此命令只能在服务器中使用。")
        return

    guild_id = interaction.guild_id

    if not file.filename.endswith('.fsbods'):
        msgs = {
            'zh': '❌ 只支持 `.fsbods` 格式的模组文件！',
            'ja': '❌ `.fsbods` 形式のファイルのみ対応しています！',
            'fr': '❌ Seuls les fichiers `.fsbods` sont acceptés !',
            'en': '❌ Only `.fsbods` files are supported!',
        }
        await interaction.followup.send(msgs.get(lang, msgs['en']))
        return

    import aiohttp
    os.makedirs(mod_system.MODS_DIR, exist_ok=True)
    save_path = os.path.join(mod_system.MODS_DIR, file.filename)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(file.url) as resp:
                content_bytes = await resp.read()
        with open(save_path, 'wb') as f:
            f.write(content_bytes)

        # 重新扫描缓存，使新上传的模组进入缓存
        mod_system.scan_mod_files()

        # 从文件中读取模组名
        import json as _json
        with open(save_path, 'r', encoding='utf-8') as _f:
            _data = _json.load(_f)
        _mod_name = _data.get('name', file.filename.replace('.fsbods', ''))

        # 加载到当前服务器
        ok, msg = mod_system.load_mod_for_guild(_mod_name, guild_id)
        if ok:
            res = {
                'zh': f'📦 `{file.filename}` 已上传并成功加载到当前服务器！\n{msg}',
                'ja': f'📦 `{file.filename}` をアップロードして読み込みました！\n{msg}',
                'fr': f'📦 `{file.filename}` a été téléchargé et chargé !\n{msg}',
                'en': f'📦 `{file.filename}` uploaded and loaded successfully!\n{msg}',
            }
        else:
            res = {
                'zh': f'📦 `{file.filename}` 已上传但加载失败：\n{msg}',
                'ja': f'📦 `{file.filename}` アップロード成功、読み込み失敗：\n{msg}',
                'fr': f'📦 `{file.filename}` téléchargé mais échec du chargement :\n{msg}',
                'en': f'📦 `{file.filename}` uploaded but failed to load:\n{msg}',
            }
        await interaction.followup.send(res.get(lang, res['en']))
    except Exception as e:
        err = {
            'zh': f'❌ 上传失败: {e}',
            'ja': f'❌ アップロード失敗: {e}',
            'fr': f'❌ Échec du téléchargement : {e}',
            'en': f'❌ Upload failed: {e}',
        }
        await interaction.followup.send(err.get(lang, err['en']))


# 99.4 模组创建教程
@bot.tree.command(name="modscreatetutorial", description="查看模组创建教程 / View mod creation tutorial")
@app_commands.describe(language="教程语言 / Tutorial language / チュートリアル言語 / Langue du tutoriel")
@app_commands.choices(language=[
    app_commands.Choice(name="中文", value="zh"),
    app_commands.Choice(name="English", value="en")
])
async def modscreatetutorial_slash(interaction: discord.Interaction, language: app_commands.Choice[str] = None):
    """显示模组创建教程（作为文件附件发送）"""
    lang = language.value if language else 'zh'
    
    # 发送教程文件
    tutorial_file = f"mods/SDK_TUTORIAL_FULL.md" if lang == 'zh' else "mods/SDK_TUTORIAL_EN_FULL.md"
    
    if os.path.exists(tutorial_file):
        # 作为文件附件发送（完整内容）
        discord_file = discord.File(tutorial_file, filename=os.path.basename(tutorial_file))
        await interaction.response.send_message(
            f"📚 **模组创建教程** ({'中文' if lang == 'zh' else 'English'})\n完整教程已作为文件发送，请下载查看。",
            file=discord_file,
            ephemeral=True
        )
    else:
        await interaction.response.send_message(f"❌ 教程文件不存在: {tutorial_file}", ephemeral=True)


# 99.5 模组状态自查命令（按服务器隔离）
@bot.tree.command(name="modcheck", description="🔍 检查模组加载状态和权限 / Check mod loading & permissions")
async def modcheck_slash(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    locale = str(interaction.locale)
    lang = 'zh' if locale.startswith('zh') else 'en'

    owner_id = 1516859801790054532
    lines = []

    if not interaction.guild_id:
        await interaction.followup.send("❌ 此命令只能在服务器中使用。")
        return

    guild_id = interaction.guild_id

    # 1. 模组加载状态（当前服务器）
    mods = mod_system.list_mods(guild_id)
    all_cache = mod_system.list_available_mods()
    if lang == 'zh':
        lines.append(f"📦 **当前服务器模组**: {len(mods)} / {len(all_cache)} 个")
    else:
        lines.append(f"📦 **Mods on this server**: {len(mods)} / {len(all_cache)}")

    for name in mods:
        cmd_count = len(mods[name].get('registered_commands', []))
        lines.append(f"  {'✅' if name == 'owner_guard' else '📎'} `{name}` — {cmd_count} 命令")

    owner_guard_loaded = 'owner_guard' in mods

    # 2. 权限检查
    if interaction.guild:
        me = interaction.guild.me
        can_manage = me.guild_permissions.manage_messages
        can_moderate = me.guild_permissions.moderate_members
        can_admin = me.guild_permissions.administrator

        if lang == 'zh':
            lines.append(f"\n🔑 **Bot 权限**:")
            lines.append(f"  {'✅' if can_admin else '⬜'} Administrator")
            lines.append(f"  {'✅' if can_manage else '❌'} Manage Messages（删消息）")
            lines.append(f"  {'✅' if can_moderate else '⬜'} Moderate Members（禁言）")
        else:
            lines.append(f"\n🔑 **Bot Permissions**:")
            lines.append(f"  {'✅' if can_admin else '⬜'} Administrator")
            lines.append(f"  {'✅' if can_manage else '❌'} Manage Messages (delete)")
            lines.append(f"  {'✅' if can_moderate else '⬜'} Moderate Members (timeout)")

    # 3. DM 测试
    dm_ok = False
    try:
        test_msg = await interaction.user.send(
            "🔍 **modcheck 测试**：这是一条测试消息，如果你收到了说明 DM 通道正常。" if lang == 'zh'
            else "🔍 **modcheck test**: If you see this, DM channel is working."
        )
        await test_msg.delete()
        dm_ok = True
    except Exception:
        pass

    if lang == 'zh':
        lines.append(f"\n📨 **DM 通道**: {'✅ 正常' if dm_ok else '❌ 失败（请检查隐私设置）'}")
    else:
        lines.append(f"\n📨 **DM Channel**: {'✅ OK' if dm_ok else '❌ Failed (check privacy settings)'}")

    # 4. 总结
    if lang == 'zh':
        if owner_guard_loaded and can_manage and dm_ok:
            lines.append(f"\n✅ **owner_guard 可以正常工作**")
        else:
            lines.append(f"\n⚠️ **问题汇总**:")
            if not owner_guard_loaded:
                lines.append(f"  • owner_guard 未加载 — 检查 `mods/` 目录")
            if not can_manage:
                lines.append(f"  • 缺少 Manage Messages — 无法删除违规消息")
            if not dm_ok:
                lines.append(f"  • DM 通道不通 — 检查隐私设置中是否允许该服务器成员私信")

        await interaction.followup.send('\n'.join(lines), ephemeral=True)
    else:
        if owner_guard_loaded and can_manage and dm_ok:
            lines.append(f"\n✅ **owner_guard is ready to work**")
        else:
            lines.append(f"\n⚠️ **Issues found**:")
            if not owner_guard_loaded:
                lines.append(f"  • owner_guard not loaded — check `mods/` directory")
            if not can_manage:
                lines.append(f"  • Missing Manage Messages — cannot delete violating messages")
            if not dm_ok:
                lines.append(f"  • DM channel blocked — check privacy settings")

        await interaction.followup.send('\n'.join(lines), ephemeral=True)


with open('token.txt', 'r', encoding='utf-8') as f:
    bot.run(f.read().strip())