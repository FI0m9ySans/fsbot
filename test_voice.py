"""
语音连接最小测试 — 直接用系统 Python 测试 discord.py 语音连接
使用方法: D:/Python314/python.exe test_voice.py
"""
import sys
import asyncio
import discord
from discord.ext import commands

# 你的 Bot token
TOKEN = open('token.txt', 'r', encoding='utf-8').read().strip()

intents = discord.Intents.all()

class TestBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!', intents=intents)
    
    async def setup_hook(self):
        print("[Test] Bot 登录成功")
        # 检查 PyNaCl
        try:
            import nacl
            print(f"[Test] PyNaCl 可用: {nacl.__version__}, path: {nacl.__file__}")
        except ImportError as e:
            print(f"[Test] ⚠️ PyNaCl 导入失败: {e}")
        
        # 检查 libopus
        try:
            if discord.opus._load_default():
                print("[Test] libopus 已加载")
            else:
                print("[Test] ⚠️ libopus 未找到")
        except Exception as e:
            print(f"[Test] ⚠️ libopus 检查失败: {e}")
        
        # 尝试连接第一个可用 guild 的语音频道
        await self.test_voice()
    
    async def test_voice(self):
        await asyncio.sleep(2)  # 等待 guild 数据加载
        
        if not self.guilds:
            print("[Test] ⚠️ Bot 没有加入任何服务器，无法测试语音连接")
            await self.close()
            return
        
        guild = self.guilds[0]
        print(f"[Test] 测试服务器: {guild.name} (id={guild.id})")
        
        # 找到第一个有成员的语音频道
        voice_channel = None
        for ch in guild.voice_channels:
            if ch.members:
                voice_channel = ch
                print(f"[Test] 找到有人的语音频道: {ch.name} (id={ch.id})")
                break
        
        if voice_channel is None:
            print("[Test] ⚠️ 没有找到有人的语音频道，尝试连接第一个语音频道")
            if guild.voice_channels:
                voice_channel = guild.voice_channels[0]
        
        if voice_channel is None:
            print("[Test] ⚠️ 服务器没有语音频道")
            await self.close()
            return
        
        # 尝试连接
        print(f"[Test] 正在连接语音频道: {voice_channel.name}...")
        try:
            vc = await voice_channel.connect()
            print(f"[Test] ✅ 语音连接成功！")
            await asyncio.sleep(2)
            await vc.disconnect()
            print("[Test] ✅ 已断开语音连接")
        except Exception as e:
            print(f"[Test] ❌ 语音连接失败:")
            import traceback
            traceback.print_exc()
        finally:
            await self.close()

bot = TestBot()

print("[Test] 开始测试...")
print(f"[Test] Python: {sys.executable}")
print(f"[Test] discord.py: {discord.__version__}")

bot.run(TOKEN)
