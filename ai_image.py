"""
FSBot AI 图像生成模块
使用智谱AI (CogView-3-Flash) 实现文生图功能
命令: .draw <prompt>  /  .draw <prompt> --size WxH  /  .outpaint <prompt>
也支持 .aichat 对话中通过 [image:描述] 触发画图
"""
import asyncio
import aiohttp
import json
import os
import re
import base64
import io
import discord

# ── 智谱AI 图像生成配置 ──
ZHIPU_IMAGE_URL = "https://open.bigmodel.cn/api/paas/v4/images/generations"
ZHIPU_IMAGE_MODEL = "cogview-3-flash"
ZHIPU_IMAGE_KEY = ""

# 支持的预设尺寸
PRESET_SIZES = {
    "square": "1024x1024",
    "portrait": "768x1344",
    "landscape": "1344x768",
    "wide": "1440x720",
    "tall": "720x1440",
    "std": "1152x864",
    "stdv": "864x1152",
}

# ── 运行时统计 ──
_image_stats = {}  # {user_id: {"total": N, "last_used": datetime}}


def _load_image_key():
    """从 img_key.txt 读取图像生成 API Key"""
    global ZHIPU_IMAGE_KEY
    key_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "img_key.txt")
    if os.path.exists(key_file):
        with open(key_file, "r", encoding="utf-8") as f:
            ZHIPU_IMAGE_KEY = f.read().strip()
    else:
        ZHIPU_IMAGE_KEY = os.environ.get("ZHIPU_IMAGE_KEY", "")
    return bool(ZHIPU_IMAGE_KEY)


def _parse_size(size_str: str) -> str:
    """解析尺寸参数，返回标准格式 WxH"""
    if not size_str:
        return "1024x1024"

    # 预设别名
    low = size_str.lower().strip()
    if low in PRESET_SIZES:
        return PRESET_SIZES[low]

    # WxH 格式
    match = re.match(r'^(\d{3,4})[xX\*](\d{3,4})$', size_str.strip())
    if match:
        w, h = int(match.group(1)), int(match.group(2))
        # 验证约束
        if 512 <= w <= 2048 and 512 <= h <= 2048:
            if w % 16 == 0 and h % 16 == 0:
                if w * h <= 2_097_152:  # 2^21
                    return f"{w}x{h}"
    return "1024x1024"  # 无效时回退默认


def _parse_args(args_str: str) -> dict:
    """解析命令行参数: --size WxH --quality hd 等"""
    result = {"size": "1024x1024", "quality": "standard"}
    parts = []
    current = ""
    i = 0
    tokens = args_str.split()
    while i < len(tokens):
        t = tokens[i]
        if t.startswith("--") and i + 1 < len(tokens):
            key = t[2:]
            val = tokens[i + 1]
            if key == "size":
                result["size"] = _parse_size(val)
            elif key == "quality":
                result["quality"] = "hd" if val.lower() in ("hd", "high") else "standard"
            i += 2
        else:
            parts.append(t)
            i += 1

    result["prompt"] = " ".join(parts)
    return result


async def _generate_image(prompt: str, size: str = "1024x1024", quality: str = "standard",
                          user_id: str = "") -> dict:
    """
    调用智谱AI CogView-3-Flash 生成图片
    返回: {"url": "...", "created": ...} 或 {"error": "..."}
    """
    if not ZHIPU_IMAGE_KEY:
        return {"error": "图像生成 API Key 未配置 (img_key.txt)"}

    headers = {
        "Authorization": f"Bearer {ZHIPU_IMAGE_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": ZHIPU_IMAGE_MODEL,
        "prompt": prompt,
        "size": size,
    }

    # quality 仅在 cogview-4 系列支持，cogview-3-flash 忽略此参数
    if quality == "hd":
        payload["quality"] = "hd"

    # 合规: user_id >= 6 字符
    if user_id and len(user_id) >= 6:
        payload["user_id"] = user_id[:128]

    # 指数退避重试
    max_retries = 3
    last_error = None

    for attempt in range(max_retries):
        try:
            timeout = aiohttp.ClientTimeout(total=90)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(ZHIPU_IMAGE_URL, headers=headers,
                                        json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if "data" in data and len(data["data"]) > 0:
                            return {
                                "url": data["data"][0].get("url", ""),
                                "created": data.get("created", 0),
                            }
                        else:
                            return {"error": f"API 返回空结果: {json.dumps(data, ensure_ascii=False)[:300]}"}

                    error_text = await resp.text()
                    last_error = Exception(f"HTTP {resp.status}: {error_text[:200]}")

                    # 429 限流，等待重试
                    if resp.status == 429:
                        wait = (attempt + 1) * 3
                        print(f"[ImageGen] 429 限流，等待 {wait}s 后重试 (第{attempt+1}次)")
                        await asyncio.sleep(wait)
                        continue

                    # 5xx 服务端错误
                    if 500 <= resp.status < 600:
                        wait = (attempt + 1) * 2
                        print(f"[ImageGen] HTTP {resp.status}，等待 {wait}s 后重试 (第{attempt+1}次)")
                        await asyncio.sleep(wait)
                        continue

                    raise last_error

        except asyncio.TimeoutError:
            last_error = Exception("请求超时")
            if attempt < max_retries - 1:
                wait = (attempt + 1) * 5
                print(f"[ImageGen] 超时，等待 {wait}s 后重试 (第{attempt+1}次)")
                await asyncio.sleep(wait)
                continue
        except aiohttp.ClientError as e:
            last_error = Exception(f"网络错误: {e}")
            if attempt < max_retries - 1:
                wait = (attempt + 1) * 3
                print(f"[ImageGen] 网络错误，等待 {wait}s 后重试 (第{attempt+1}次)")
                await asyncio.sleep(wait)
                continue

    if last_error:
        return {"error": str(last_error)}
    return {"error": "未知错误"}


async def _download_image(url: str) -> bytes:
    """下载生成的图片到内存"""
    headers = {"User-Agent": "FSBot/1.0"}
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                return await resp.read()
            raise Exception(f"下载图片失败: HTTP {resp.status}")


def _get_system_image_instructions() -> str:
    """返回给 AI 对话的图像生成指令"""
    return (
        "\n=== 图像生成功能 ===\n"
        "你也可以帮助用户生成图片。在回复中使用 [image:中文描述] 标记，\n"
        "系统会自动调用 CogView-3-Flash 生成图片并发送给用户。\n"
        f"支持的预设尺寸: {', '.join(PRESET_SIZES.keys())}\n"
        f"自定义尺寸: WxH (512-2048px, 需被16整除)\n"
        "例如用户说「帮我画一只猫」，你可以在回复中加入 [image:一只可爱的橘猫，坐在窗台上，阳光明媚，写实风格]\n"
        "注意: 这是一个文生图模型，不支持基于已有图片的编辑/扩图。"
    )


# ── 公开接口 ──

async def init_image_gen(bot):
    """初始化图像生成模块（在 bot.on_ready 中调用）"""
    if _load_image_key():
        print(f"[ImageGen] CogView-3-Flash 图像生成模块已初始化")
    else:
        print("[ImageGen] img_key.txt 未找到，图像生成功能不可用")


async def handle_draw(message, bot):
    """
    处理 .draw 和 .outpaint 命令
    在 on_message 中调用, 返回 True 表示已处理
    """
    content = message.content.strip()

    if message.author.bot:
        return False

    # ── .draw ──
    if content.lower().startswith(".draw"):
        args_str = content[5:].strip()
        if not args_str:
            await _send_help(message)
            return True

        parsed = _parse_args(args_str)
        prompt = parsed["prompt"]
        if not prompt:
            await message.reply("❌ 请提供图片描述，例如: `.draw 一只可爱的猫咪`")
            return True

        await _do_draw(message, prompt, parsed["size"], parsed["quality"])
        return True

    # ── .outpaint ──
    if content.lower().startswith(".outpaint"):
        args_str = content[9:].strip()
        if not args_str:
            await message.reply(
                "🖼️ **扩图** (Outpainting)\n"
                "CogView-3-Flash 是纯文生图模型，不支持基于图片的扩图。\n"
                "请用文字描述你想要的扩图效果，例如:\n"
                "`.outpaint 补充场景左侧，增加一片森林和远处山脉`\n\n"
                "💡 提示: 此功能通过文字描述生成扩展场景图。"
            )
            return True

        parsed = _parse_args(args_str)
        prompt = parsed["prompt"]
        if not prompt:
            await message.reply("❌ 请描述你想要的扩图效果")
            return True

        # 给 prompt 加上引导前缀
        full_prompt = f"扩展画面: {prompt}"
        await _do_draw(message, full_prompt, parsed["size"], parsed["quality"],
                       label="扩图")
        return True

    return False


async def handle_image_tag(message, bot, reply_text: str):
    """
    解析 AI 回复中的 [image:描述] 标记，生成图片并发送
    由 ai_chat.handle_aichat 调用
    """
    pattern = re.compile(r'\[image:(.*?)\]')
    matches = pattern.findall(reply_text)
    if not matches:
        return None  # 没有图片标记

    # 移除标记并清理
    clean_reply = pattern.sub('', reply_text).strip()

    results = []
    for prompt in matches[:3]:  # 最多3张图
        prompt = prompt.strip()
        if not prompt:
            continue

        result = await _generate_image(prompt, user_id=str(message.author.id))
        if "url" in result:
            results.append({"prompt": prompt, "url": result["url"]})

    return {"text": clean_reply, "images": results}


async def _do_draw(message, prompt: str, size: str, quality: str, label: str = "文生图"):
    """执行画图逻辑，发送结果"""
    if not ZHIPU_IMAGE_KEY:
        await message.reply("❌ 图像生成功能未配置 API Key")
        return

    # 显示等待
    thinking = await message.reply(
        f"🎨 **{label}生成中...**\n"
        f"📝 描述: {prompt[:200]}{'...' if len(prompt) > 200 else ''}\n"
        f"📐 尺寸: {size}"
    )

    result = await _generate_image(prompt, size=size, quality=quality,
                                   user_id=str(message.author.id))

    if "error" in result:
        await thinking.edit(content=f"❌ **{label}失败**: {result['error']}")
        return

    image_url = result["url"]
    if not image_url:
        await thinking.edit(content=f"❌ **{label}失败**: API 未返回图片 URL")
        return

    # 更新统计
    uid = message.author.id
    import datetime as dt
    if uid not in _image_stats:
        _image_stats[uid] = {"total": 0, "last_used": None}
    _image_stats[uid]["total"] += 1
    _image_stats[uid]["last_used"] = dt.datetime.now().isoformat()

    # 生成 Embed
    embed = discord.Embed(
        title=f"🎨 {label}结果",
        description=f"📝 {prompt[:250]}{'...' if len(prompt) > 250 else ''}",
        color=discord.Color.blue(),
    )
    embed.set_image(url=image_url)
    embed.set_footer(text=f"CogView-3-Flash | {size} | 图片链接 30 天有效")

    try:
        await thinking.edit(content=None, embed=embed)
    except Exception:
        # 如果 embed 发送失败（eg. 消息太长）, 直接发链接
        await thinking.edit(content=f"🎨 **{label}结果**\n{image_url}\n\n📝 {prompt[:100]}")
        # 补充发 embed
        try:
            await message.channel.send(embed=embed)
        except Exception:
            pass


async def _send_help(message):
    """发送 .draw 帮助信息"""
    embed = discord.Embed(
        title="🎨 AI 图像生成",
        description="使用 CogView-3-Flash 模型进行文生图",
        color=discord.Color.blue(),
    )
    embed.add_field(
        name="📝 文生图",
        value=(
            "```\n"
            ".draw <描述>\n"
            ".draw <描述> --size 1024x1024\n"
            "```\n"
            "例如: `.draw 一只可爱的橘猫在窗台上晒太阳`"
        ),
        inline=False,
    )
    embed.add_field(
        name="🖼️ 扩图(文字版)",
        value=(
            "```\n"
            ".outpaint <描述>\n"
            "```\n"
            "💡 CogView-3-Flash 是纯文生图模型，\n"
            "扩图通过文字描述生成扩展后的画面。\n"
            "例如: `.outpaint 场景左侧延伸出森林`"
        ),
        inline=False,
    )
    embed.add_field(
        name="📐 预设尺寸",
        value="`square` 1024x1024 | `portrait` 768x1344 | `landscape` 1344x768\n"
              "`wide` 1440x720 | `tall` 720x1440 | `std` 1152x864 | `stdv` 864x1152",
        inline=False,
    )
    embed.add_field(
        name="🤖 AI 对话触发",
        value="在 `.aichat` 对话中说「帮我画一张...」，AI 会自动生成图片。",
        inline=False,
    )
    embed.set_footer(text="CogView-3-Flash | 免费模型 | 图片链接 30 天有效")
    await message.reply(embed=embed)
