"""
clear_guild_commands.py — 清除 bot 在所有 guild 中的斜杠命令
用法：把此文件放在 D:/FSBot/ 下，运行 python clear_guild_commands.py
"""
import discord
from discord.ext import commands
import asyncio
import sys

TOKEN = open('token.txt', 'r', encoding='utf-8').read().strip()

intents = discord.Intents.default()
bot = commands.Bot(command_prefix='!', intents=intents)


@bot.event
async def on_ready():
    print(f'登录为: {bot.user}')
    for g in bot.guilds:
        try:
            # 获取 guild 已有的命令
            cmds = await bot.tree.fetch_commands(guild=discord.Object(id=g.id))
            print(f'  Guild [{g.name}]: 找到 {len(cmds)} 个命令')
            for c in cmds:
                print(f'    - /{c.name}')
            # 清除所有 guild 命令
            await bot.tree.clear_commands(guild=discord.Object(id=g.id))
            # 同步（推送清除）
            await bot.tree.sync(guild=discord.Object(id=g.id))
            print(f'  ✅ Guild [{g.name}]: 已清除并同步（0 个命令）')
        except Exception as e:
            print(f'  ❌ Guild [{g.name}]: 失败: {e}')
    # 同时也清除全局命令（谨慎！）
    try:
        global_cmds = await bot.tree.fetch_commands()
        print(f'全局命令: {len(global_cmds)} 个')
        if global_cmds:
            await bot.tree.clear_commands()
            await bot.tree.sync()
            print('✅ 全局命令已清除')
    except Exception as e:
        print(f'全局命令清除失败（可忽略）: {e}')

    await bot.close()
    print('完成！现在可以重新运行 main.py 了。')


bot.run(TOKEN)
