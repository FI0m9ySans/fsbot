"""
FSBot Music Bot — 音乐播放模块
支持 YouTube / SoundCloud / 直接URL 播放，队列管理，语音频道控制
依赖: yt-dlp, PyNaCl, FFmpeg
"""
import asyncio
import copy
import discord
from discord.ext import commands
from collections import deque
import re
import os
import sys
import shutil
import traceback
import hashlib
import time
import uuid
import json
import urllib.parse
import urllib.request

# ── FFmpeg 路径修复 (Windows) ──
# WinGet 安装的 ffmpeg 在 PATH 中, 但 bot_gui.py 启动的子进程可能找不到
if not shutil.which('ffmpeg'):
    _ffmpeg_candidates = [
        os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Microsoft', 'WinGet', 'Links'),
        os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Microsoft', 'WinGet', 'Packages'),
    ]
    for _p in _ffmpeg_candidates:
        if os.path.isfile(os.path.join(_p, 'ffmpeg.exe')):
            os.environ['PATH'] = _p + os.pathsep + os.environ.get('PATH', '')
            break
    # 深度搜索 WinGet Packages
    if not shutil.which('ffmpeg'):
        _pkg = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Microsoft', 'WinGet', 'Packages')
        if os.path.isdir(_pkg):
            for _dir in os.listdir(_pkg):
                if 'ffmpeg' in _dir.lower():
                    _bin = os.path.join(_pkg, _dir)
                    # 找 bin 子目录
                    for _root, _dirs, _files in os.walk(_bin):
                        if 'ffmpeg.exe' in _files:
                            os.environ['PATH'] = _root + os.pathsep + os.environ.get('PATH', '')
                            break

# ── SSL 证书修复 (Windows) ──
# Windows 上 yt-dlp 默认使用 certifi 的 CA 证书包, 但该证书包无法验证 YouTube 证书
# 使用 yt-dlp 的 compat_opts=['no-certifi'] 改用 Windows 系统证书

# ── Bilibili 搜索 (wbi 签名) ──
_BILI_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
_BILI_WBI_KEY_CACHE = {'key': '', 'ts': 0}
_BILI_WBI_TIMEOUT = 600  # 10 分钟缓存

_BILI_MIXIN_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52,
]


def _bili_get_wbi_key() -> str:
    """获取 Bilibili wbi 签名密钥 (带缓存)"""
    if time.time() < _BILI_WBI_KEY_CACHE['ts'] + _BILI_WBI_TIMEOUT and _BILI_WBI_KEY_CACHE['key']:
        return _BILI_WBI_KEY_CACHE['key']

    buvid3 = f'{uuid.uuid4()}infoc'
    req = urllib.request.Request(
        'https://api.bilibili.com/x/web-interface/nav',
        headers={'User-Agent': _BILI_UA, 'Cookie': f'buvid3={buvid3}', 'Referer': 'https://www.bilibili.com'}
    )
    resp = urllib.request.urlopen(req, timeout=10)
    nav = json.loads(resp.read().decode('utf-8'))
    img_url = nav['data']['wbi_img']['img_url']
    sub_url = nav['data']['wbi_img']['sub_url']
    lookup = img_url.rpartition('/')[2].partition('.')[0] + sub_url.rpartition('/')[2].partition('.')[0]
    wbi_key = ''.join(lookup[i] for i in _BILI_MIXIN_TAB)[:32]
    _BILI_WBI_KEY_CACHE.update({'key': wbi_key, 'ts': time.time()})
    return wbi_key


def _bili_sign_wbi(params: dict) -> dict:
    """对请求参数进行 wbi 签名"""
    wbi_key = _bili_get_wbi_key()
    params['wts'] = round(time.time())
    params = {
        k: ''.join(filter(lambda c: c not in "!'()*", str(v)))
        for k, v in sorted(params.items())
    }
    query = urllib.parse.urlencode(params)
    params['w_rid'] = hashlib.md5(f'{query}{wbi_key}'.encode()).hexdigest()
    return params


def bilibili_get_pages(bvid: str) -> dict | None:
    """通过 Bilibili API 获取视频信息 (含分P列表)
    返回 {title, thumbnail, pages: [{part, duration, cid}]} 或 None"""
    view_url = f'https://api.bilibili.com/x/web-interface/view?bvid={bvid}'
    req = urllib.request.Request(view_url, headers={
        'User-Agent': _BILI_UA,
        'Referer': 'https://www.bilibili.com',
    })
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read().decode('utf-8'))
        if data.get('code') != 0:
            return None
        d = data['data']
        pages = []
        for p in d.get('pages', []):
            pages.append({
                'part': p.get('part', f'P{p.get("page", 1)}'),
                'duration': p.get('duration', 0),
                'cid': p.get('cid', 0),
                'page': p.get('page', 1),
            })
        return {
            'title': d.get('title', ''),
            'thumbnail': d.get('pic', ''),
            'bvid': bvid,
            'pages': pages,
        }
    except Exception:
        return None


def bilibili_get_audio_info(auid: str) -> dict | None:
    """通过 Bilibili API 获取音频信息 (au号)
    返回 {title, duration, thumbnail, url} 或 None"""
    # auid 格式: au12345678 → 提取数字
    song_id = re.sub(r'^au', '', auid, flags=re.IGNORECASE)
    api_url = f'https://www.bilibili.com/audio/music-service/web/song/info?song_id={song_id}'
    req = urllib.request.Request(api_url, headers={
        'User-Agent': _BILI_UA,
        'Referer': 'https://www.bilibili.com/audio/',
    })
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read().decode('utf-8'))
        if data.get('code') != 0:
            return None
        d = data['data']
        return {
            'title': d.get('title', ''),
            'duration': d.get('duration', 0),
            'thumbnail': d.get('cover', ''),
            'url': f'https://www.bilibili.com/audio/au{d.get("id", song_id)}',
        }
    except Exception:
        return None


def bilibili_search(query: str, limit: int = 5, page: int = 1) -> list[dict]:
    """
    搜索 Bilibili 视频, 返回结果列表
    每个结果: {url, title, duration, thumbnail, bvid}
    """
    buvid3 = f'{uuid.uuid4()}infoc'
    params = _bili_sign_wbi({
        'Search_key': query,
        'keyword': query,
        'page': page,
        'context': '',
        'duration': 0,
        'tids_2': '',
        '__refresh__': 'true',
        'search_type': 'video',
        'tids': 0,
        'highlight': 1,
    })
    search_url = 'https://api.bilibili.com/x/web-interface/search/type?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(search_url, headers={
        'User-Agent': _BILI_UA,
        'Cookie': f'buvid3={buvid3}',
        'Referer': 'https://search.bilibili.com',
    })
    resp = urllib.request.urlopen(req, timeout=10)
    data = json.loads(resp.read().decode('utf-8'))
    results_raw = data.get('data', {}).get('result', []) or []

    results = []
    for r in results_raw[:limit]:
        # 清理标题中的 <em> 高亮标签
        title = re.sub(r'<[^>]+>', '', r.get('title', ''))
        # 解析时长 "2:39" → 秒
        dur_str = r.get('duration', '0:00')
        parts = dur_str.split(':')
        duration = 0
        for p in parts:
            duration = duration * 60 + (int(p) if p.isdigit() else 0)

        results.append({
            'url': f"https://www.bilibili.com/video/{r.get('bvid', '')}",
            'title': title,
            'duration': duration,
            'thumbnail': r.get('pic', ''),
            'bvid': r.get('bvid', ''),
        })
    return results

# ── 语音依赖诊断 ──
print("[MusicBot] Python executable:", sys.executable)
_nacl_ok = False
try:
    import nacl
    _nacl_ok = True
    print(f"[MusicBot] PyNaCl 可用: {nacl.__version__}")
except ImportError as _e:
    print(f"[MusicBot] ⚠️ PyNaCl 导入失败: {_e}")
    nacl = None

# 检查 libopus
_opus_ok = False
try:
    if not discord.opus._load_default():
        print("[MusicBot] ⚠️ libopus 未找到（不影响连接，但语音质量可能受影响）")
    else:
        _opus_ok = True
        print("[MusicBot] libopus 已加载")
except Exception as _e:
    print(f"[MusicBot] ⚠️ libopus 检查失败: {_e}")

# ── 音乐队列数据结构 ──
class Song:
    """一首歌"""
    def __init__(self, url: str, title: str, duration: int, thumbnail: str, requester: discord.Member):
        self.url = url
        self.title = title
        self.duration = int(duration or 0)  # 秒 (yt-dlp 可能返回 float)
        self.thumbnail = thumbnail
        self.requester = requester

    def duration_str(self):
        m, s = divmod(self.duration, 60)
        if m >= 60:
            h, m = divmod(m, 60)
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"


class MusicQueue:
    """音乐队列管理器 (每个 guild 一个)"""
    def __init__(self):
        self.queue: deque[Song] = deque()
        self.current: Song = None
        self.loop_mode = 0  # 0=off, 1=loop song, 2=loop queue
        self.volume = 1.0
        self.speed = 1.0   # 播放倍速 (0.25 ~ 4.0)
        self.vc: discord.VoiceClient = None
        # ── 播放进度追踪 ──
        self.start_time: float = 0.0        # 当前歌曲开始播放的时间戳
        self.pause_time: float | None = None # 暂停时刻 (None=未暂停)
        self.total_paused: float = 0.0       # 累计暂停时长
        self.np_message: discord.Message | None = None  # 正在播放消息 (用于实时更新)
        self.np_task: asyncio.Task | None = None        # 进度更新后台任务

    def add(self, song: Song):
        self.queue.append(song)

    def get_next(self) -> Song:
        if self.loop_mode == 1 and self.current:
            return self.current
        if self.loop_mode == 2 and self.current:
            self.queue.append(self.current)
        if self.queue:
            return self.queue.popleft()
        return None

    def clear(self):
        self.queue.clear()
        self.current = None

    def remove(self, index: int) -> Song:
        if 0 <= index < len(self.queue):
            song = self.queue[index]
            del self.queue[index]
            return song
        return None

    def shuffle(self):
        import random
        items = list(self.queue)
        random.shuffle(items)
        self.queue = deque(items)


# ── 进度追踪辅助函数 ──

def format_duration(seconds: float) -> str:
    """格式化秒数为 M:SS 或 H:MM:SS"""
    seconds = max(0, int(seconds))
    m, s = divmod(seconds, 60)
    if m >= 60:
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def make_progress_bar(elapsed: float, total: int, length: int = 15) -> str:
    """生成进度条字符串: `1:23 ▰▰▰▰▰▱▱▱▱▱ 4:56`"""
    elapsed = max(0, int(elapsed))
    if total <= 0:
        # 未知时长 (直播等)
        return f"`🔴 {format_duration(elapsed)} ─────────────`"
    total = int(total)
    elapsed = min(elapsed, total)
    progress = elapsed / total
    filled = int(progress * length)
    bar = "▰" * filled + "▱" * (length - filled)
    return f"`{format_duration(elapsed)} {bar} {format_duration(total)}`"


def get_elapsed(queue: MusicQueue) -> float:
    """获取当前歌曲已播放的秒数 (考虑暂停时间)"""
    if not queue.start_time:
        return 0.0
    if queue.pause_time:
        # 暂停中: 进度冻结在暂停时刻
        return max(0, queue.pause_time - queue.start_time - queue.total_paused)
    return max(0, time.time() - queue.start_time - queue.total_paused)


# ── 全局队列 (guild_id -> MusicQueue) ──
music_queues: dict[int, MusicQueue] = {}

# ── 搜索结果缓存 (guild_id, user_id) -> {'results': list, 'ts': float} ──
# 用于 !play N 选歌: 用户搜索后 120 秒内可用 !play 1-5 选歌
_search_cache: dict[tuple[int, int], dict] = {}
_SEARCH_CACHE_TTL = 120  # 秒


# ══════════════════════════════════════════════
# 音频源处理
# ══════════════════════════════════════════════

# ── 代理配置 (环境变量 YTDLP_PROXY) ──
# 支持 http/https/socks5 代理, 用于访问 YouTube 等被墙站点
# 设置方法: set YTDLP_PROXY=http://127.0.0.1:7890
_YTDLP_PROXY = os.environ.get('YTDLP_PROXY', '').strip()

_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'

# FFmpeg 选项说明:
# - FFmpeg 8.1.2+, 支持 -user_agent / -headers / -reconnect
# - Bilibili CDN 需要 Referer 头, 否则 403; -multiple_requests 对分段流更友好
# - -reconnect 系列确保网络波动时自动重连, 减少卡顿和断播
FFMPEG_OPTIONS_BILI = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_at_eof 1 '
                      '-reconnect_on_network_error 1 -reconnect_delay_max 5 '
                      '-multiple_requests 1 '
                      f'-user_agent "{_UA}" '
                      f'-headers "Referer: https://www.bilibili.com\r\n"',
    'options': '-vn -b:a 128k'
}

FFMPEG_OPTIONS_GENERIC = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_at_eof 1 '
                      '-reconnect_on_network_error 1 -reconnect_delay_max 5 '
                      f'-user_agent "{_UA}"',
    'options': '-vn -b:a 128k'
}


def _build_atempo_filter(speed: float) -> str:
    """构建 FFmpeg atempo 滤镜链 (不改变音调)
    atempo 单实例范围 0.5~2.0, 超出范围时链式组合"""
    if speed == 1.0:
        return ''
    remaining = speed
    parts = []
    while remaining < 0.5:
        parts.append('atempo=0.5')
        remaining /= 0.5
    while remaining > 2.0:
        parts.append('atempo=2.0')
        remaining /= 2.0
    if remaining != 1.0:
        parts.append(f'atempo={remaining:g}')
    return ','.join(parts)


def _is_bilibili_url(url: str) -> bool:
    """判断 URL 是否为 Bilibili 链接"""
    return 'bilibili.com' in url or 'b23.tv' in url


def _get_ffmpeg_options(url: str, speed: float = 1.0) -> dict:
    """根据 URL 来源和倍速返回合适的 FFmpeg 参数"""
    base = FFMPEG_OPTIONS_BILI if _is_bilibili_url(url) else FFMPEG_OPTIONS_GENERIC
    atempo = _build_atempo_filter(speed)
    if atempo:
        opts = copy.deepcopy(base)
        opts['options'] = f"{base['options']} -af {atempo}"
        return opts
    return base


def _build_ydl_options(playlist: bool = False, bilibili: bool = True) -> dict:
    """构建 yt-dlp 选项, 自动注入代理和合适的 headers"""
    opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'source_address': '0.0.0.0',
        'nocheckcertificate': True,
        'compat_opts': ['no-certifi'],
    }
    if playlist:
        opts['extract_flat'] = 'in_playlist'
    else:
        opts['extract_flat'] = False
        opts['noplaylist'] = True

    if bilibili:
        opts['http_headers'] = {
            'Referer': 'https://www.bilibili.com',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
        }
    else:
        opts['http_headers'] = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
        }

    if _YTDLP_PROXY:
        opts['proxy'] = _YTDLP_PROXY
        print(f"[MusicBot] 使用代理: {_YTDLP_PROXY}")

    return opts


# 保留旧名称兼容 (部分代码可能直接引用)
YDL_OPTIONS = _build_ydl_options(playlist=False, bilibili=True)
YDL_PLAYLIST_OPTIONS = _build_ydl_options(playlist=True, bilibili=True)


class YTDLSource(discord.PCMVolumeTransformer):
    """yt-dlp 音频源"""
    def __init__(self, source, *, data, volume=1.0):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title', 'Unknown')
        self.url = data.get('webpage_url', data.get('url', ''))
        self.duration = data.get('duration', 0) or 0
        self.thumbnail = data.get('thumbnail', '')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=True, playlist=False, speed=1.0):
        import yt_dlp

        is_bili = _is_bilibili_url(url)
        opts = _build_ydl_options(playlist=playlist, bilibili=is_bili)
        ydl = yt_dlp.YoutubeDL(opts)

        loop = loop or asyncio.get_running_loop()

        data = await loop.run_in_executor(
            None, lambda: ydl.extract_info(url, download=not stream)
        )

        if data is None:
            raise ValueError("无法获取音频信息")

        # 处理播放列表 / 合集 / 分P
        if 'entries' in data:
            entries = [e for e in data['entries'] if e]
            if not entries:
                raise ValueError("合集/播放列表为空")

            if playlist:
                # 播放列表模式: 返回全部
                return [cls(discord.FFmpegPCMAudio(
                    e['url'], **_get_ffmpeg_options(url, speed)
                ), data=e) for e in entries]

            # 非播放列表模式 (单首播放): 只取第一个
            # 但如果合集只有1个分P, 直接用
            data = entries[0]

        # 单个视频
        filename = data['url'] if stream else ydl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **_get_ffmpeg_options(url, speed)), data=data)

    @classmethod
    async def search_song(cls, query: str, *, loop=None):
        """搜索单首歌曲，返回 Song 或 list[Song] (多分P时返回列表)
        Bilibili: 先用 API 快速获取分P信息 (含标题+时长), 再决定单首/多P
        非 Bilibili URL: 用 yt-dlp 提取"""
        import yt_dlp

        loop = loop or asyncio.get_running_loop()

        # ── 从 URL 或搜索结果中提取 bvid ──
        def _extract_bvid(url: str) -> str | None:
            """从 Bilibili URL 中提取 bvid"""
            m = re.search(r'/video/(BV[\w]+)', url)
            if m:
                return m.group(1)
            m = re.search(r'bvid=(BV[\w]+)', url)
            if m:
                return m.group(1)
            return None

        # ── 从输入中提取 au 号 (Bilibili 音频) ──
        def _extract_auid(text: str) -> str | None:
            """从文本中提取 au 号, 支持 au12345678 或 URL 形式"""
            # URL 形式: https://www.bilibili.com/audio/au12345678
            m = re.search(r'audio/(au\d+)', text, re.IGNORECASE)
            if m:
                return m.group(1)
            # 纯 au 号: au12345678
            m = re.match(r'^(au\d+)$', text.strip(), re.IGNORECASE)
            if m:
                return m.group(1)
            return None

        # ── 用 Bilibili API 构建分P Song 列表 ──
        def _build_songs_from_api(bvid: str, fallback_title: str = '', fallback_thumb: str = '') -> Song | list[Song] | None:
            info = bilibili_get_pages(bvid)
            if not info:
                return None
            base_url = f'https://www.bilibili.com/video/{bvid}'
            thumb = info.get('thumbnail') or fallback_thumb
            pages = info['pages']
            if len(pages) <= 1:
                # 单P
                p = pages[0] if pages else {}
                return Song(
                    url=base_url,
                    title=info.get('title') or fallback_title or 'Unknown',
                    duration=p.get('duration', 0) or 0,
                    thumbnail=thumb,
                    requester=None
                )
            # 多分P: 每个P一个 Song
            return [
                Song(
                    url=f'{base_url}?p={p["page"]}',
                    title=f'{info["title"]} - {p["part"]}' if info.get('title') else p['part'],
                    duration=p.get('duration', 0) or 0,
                    thumbnail=thumb,
                    requester=None
                )
                for p in pages
            ]

        # ── 检查是否为 au 号 (Bilibili 音频) ──
        auid = _extract_auid(query)
        if auid:
            # 用 Bilibili 音频 API 获取元数据
            audio_info = await loop.run_in_executor(None, bilibili_get_audio_info, auid)
            if audio_info:
                return Song(
                    url=audio_info['url'],
                    title=audio_info['title'],
                    duration=audio_info['duration'],
                    thumbnail=audio_info['thumbnail'],
                    requester=None
                )
            # API 失败 → 回退 yt-dlp (它能处理 au URL)
            ydl = yt_dlp.YoutubeDL(YDL_OPTIONS)
            data = await loop.run_in_executor(
                None, lambda: ydl.extract_info(f'https://www.bilibili.com/audio/{auid}', download=False)
            )
            if data:
                return Song(
                    url=data.get('webpage_url', f'https://www.bilibili.com/audio/{auid}'),
                    title=data.get('title', 'Unknown'),
                    duration=data.get('duration', 0) or 0,
                    thumbnail=data.get('thumbnail', ''),
                    requester=None
                )
            return None

        # 如果不是 URL，使用 Bilibili 搜索
        if not query.startswith('http'):
            results = await loop.run_in_executor(None, bilibili_search, query, 1)
            if not results:
                return None
            bili_url = results[0]['url']
            bvid = results[0].get('bvid') or _extract_bvid(bili_url)
            # 优先用 Bilibili API 获取分P (快速 + 完整元数据)
            if bvid:
                songs = await loop.run_in_executor(
                    None, _build_songs_from_api, bvid,
                    results[0]['title'], results[0]['thumbnail']
                )
                if songs is not None:
                    return songs
            # API 失败 → 回退到 yt-dlp
            ydl = yt_dlp.YoutubeDL(YDL_OPTIONS)
            data = await loop.run_in_executor(
                None, lambda: ydl.extract_info(bili_url, download=False)
            )
            if data is None:
                return None
            if 'entries' in data:
                entries = [e for e in data['entries'] if e]
                if not entries:
                    return None
                if len(entries) == 1:
                    e = entries[0]
                    return Song(
                        url=e.get('webpage_url', bili_url),
                        title=e.get('title', results[0]['title']),
                        duration=e.get('duration', 0) or 0,
                        thumbnail=e.get('thumbnail', results[0]['thumbnail']),
                        requester=None
                    )
                return [
                    Song(
                        url=e.get('webpage_url', e.get('original_url', bili_url)),
                        title=e.get('title', 'Unknown'),
                        duration=e.get('duration', 0) or 0,
                        thumbnail=e.get('thumbnail', ''),
                        requester=None
                    )
                    for e in entries
                ]
            return Song(
                url=data.get('webpage_url', bili_url),
                title=data.get('title', results[0]['title']),
                duration=data.get('duration', 0) or results[0]['duration'],
                thumbnail=data.get('thumbnail', results[0]['thumbnail']),
                requester=None
            )

        # 直接 URL 输入
        # Bilibili URL: 优先用 API
        if 'bilibili.com' in query or 'b23.tv' in query:
            bvid = _extract_bvid(query)
            if bvid:
                songs = await loop.run_in_executor(None, _build_songs_from_api, bvid)
                if songs is not None:
                    return songs
            # API 失败 → 回退 yt-dlp playlist 模式
            ydl = yt_dlp.YoutubeDL(_build_ydl_options(playlist=True, bilibili=True))
        else:
            # 非 Bilibili URL (YouTube 等) — 自动注入代理
            ydl = yt_dlp.YoutubeDL(_build_ydl_options(playlist=False, bilibili=False))

        data = await loop.run_in_executor(
            None, lambda: ydl.extract_info(query, download=False)
        )

        if data is None:
            return None

        if 'entries' in data:
            entries = [e for e in data['entries'] if e]
            if not entries:
                return None
            if len(entries) == 1:
                entry = entries[0]
                return Song(
                    url=entry.get('webpage_url', entry.get('original_url', query)),
                    title=entry.get('title', 'Unknown'),
                    duration=entry.get('duration', 0) or 0,
                    thumbnail=entry.get('thumbnail', ''),
                    requester=None
                )
            return [
                Song(
                    url=e.get('webpage_url', e.get('original_url', query)),
                    title=e.get('title', 'Unknown'),
                    duration=e.get('duration', 0) or 0,
                    thumbnail=e.get('thumbnail', ''),
                    requester=None
                )
                for e in entries
            ]

        return Song(
            url=data.get('webpage_url', data.get('original_url', query)),
            title=data.get('title', 'Unknown'),
            duration=data.get('duration', 0) or 0,
            thumbnail=data.get('thumbnail', ''),
            requester=None
        )

    @classmethod
    async def search_playlist(cls, url: str, *, loop=None):
        """搜索播放列表，返回 Song 列表"""
        import yt_dlp

        ydl = yt_dlp.YoutubeDL(_build_ydl_options(playlist=True, bilibili=_is_bilibili_url(url)))
        loop = loop or asyncio.get_running_loop()

        data = await loop.run_in_executor(
            None, lambda: ydl.extract_info(url, download=False)
        )

        if not data or 'entries' not in data:
            return []

        songs = []
        for entry in data['entries']:
            if entry:
                songs.append(Song(
                    url=entry.get('webpage_url', entry.get('url', '')),
                    title=entry.get('title', 'Unknown'),
                    duration=entry.get('duration', 0) or 0,
                    thumbnail=entry.get('thumbnail', ''),
                    requester=None
                ))
        return songs


# ══════════════════════════════════════════════
# 辅助函数
# ══════════════════════════════════════════════

def get_queue(guild_id: int) -> MusicQueue:
    """获取或创建 guild 的队列"""
    if guild_id not in music_queues:
        music_queues[guild_id] = MusicQueue()
    return music_queues[guild_id]


async def ensure_voice(ctx) -> tuple:
    """确保 Bot 在语音频道中，返回 (queue, error_msg)"""
    if not ctx.author.voice or not ctx.author.voice.channel:
        return None, "❌ 你需要先加入一个语音频道！"

    channel = ctx.author.voice.channel
    guild_id = ctx.guild.id
    queue = get_queue(guild_id)

    # 检查 Bot 权限
    perms = channel.permissions_for(ctx.guild.me)
    if not perms.connect or not perms.speak:
        return None, "❌ Bot 缺少「连接」或「说话」权限！"

    # 诊断：检查 nacl 是否真的可用 + 写文件日志
    import sys
    _log_file = open('D:/FSBot/music_voice_debug.log', 'a', encoding='utf-8')
    try:
        _log_file.write(f"\n=== {__import__('datetime').datetime.now()} ===\n")
        _log_file.write(f"[Voice] nacl in sys.modules: {'nacl' in sys.modules}\n")
        if 'nacl' in sys.modules:
            import nacl
            _log_file.write(f"[Voice] nacl version: {nacl.__version__}, path: {nacl.__file__}\n")
            try:
                _test_key = nacl.public.PrivateKey.generate()
                _log_file.write("[Voice] nacl 基本功能测试通过\n")
            except Exception as _ne:
                _log_file.write(f"[Voice] ⚠️ nacl 功能测试失败: {_ne}\n")
        _log_file.write(f"[Voice] discord.opus._load_default(): {discord.opus._load_default()}\n")
        _log_file.write(f"[Voice] 尝试连接频道: {channel.name} (guild={guild_id})\n")
        _log_file.flush()
        print(f"[Voice] 诊断日志已写入 music_voice_debug.log")
    finally:
        _log_file.close()

    # 连接语音频道
    if queue.vc is None or not queue.vc.is_connected():
        try:
            print(f"[Voice] 正在连接语音频道: {channel.name} (guild={guild_id})")
            queue.vc = await channel.connect()
            print(f"[Voice] 语音连接成功: {channel.name}")
        except discord.ClientException as e:
            print(f"[Voice] ClientException: {e}")
            _log_file = open('D:/FSBot/music_voice_debug.log', 'a', encoding='utf-8')
            _log_file.write(f"[Voice] ClientException: {e}\n")
            _log_file.close()
            # 可能已在其他频道
            if ctx.guild.voice_client:
                await ctx.guild.voice_client.move_to(channel)
                queue.vc = ctx.guild.voice_client
                print(f"[Voice] 已移动到频道: {channel.name}")
        except Exception as e:
            # 写完整错误到文件
            _log_file = open('D:/FSBot/music_voice_debug.log', 'a', encoding='utf-8')
            _log_file.write(f"[Voice] ❌ 连接语音失败:\n")
            import traceback
            traceback.print_exc(file=_log_file)
            _log_file.write(f"\n错误类型: {type(e).__name__}\n")
            _log_file.write(f"错误消息: {e}\n")
            _log_file.close()
            print(f"[Voice] ❌ 连接语音失败:")
            traceback.print_exc()
            return None, f"❌ 连接语音频道失败: {type(e).__name__}: {e}"
    elif queue.vc.channel != channel:
        await queue.vc.move_to(channel)

    return queue, None


def create_now_playing_embed(song: Song, queue: MusicQueue, elapsed: float = None) -> discord.Embed:
    """创建「正在播放」的 Embed (含进度条)"""
    embed = discord.Embed(
        title="🎵 正在播放",
        description=f"[{song.title}]({song.url})",
        color=0x1DB954
    )

    # ── 进度条 ──
    if elapsed is None:
        elapsed = get_elapsed(queue)
    progress_str = make_progress_bar(elapsed, song.duration)
    embed.add_field(name="📊 进度", value=progress_str, inline=False)

    embed.add_field(name="⏱ 时长", value=song.duration_str(), inline=True)
    embed.add_field(name="👤 点歌者", value=song.requester.mention, inline=True)
    embed.add_field(name="🔊 音量", value=f"{int(queue.volume * 100)}%", inline=True)

    if song.thumbnail:
        embed.set_thumbnail(url=song.thumbnail)

    if queue.queue:
        preview = ""
        for i, s in enumerate(list(queue.queue)[:5]):
            preview += f"`{i+1}.` [{s.title}]({s.url}) — {s.requester.display_name}\n"
        if len(queue.queue) > 5:
            preview += f"*…以及 {len(queue.queue) - 5} 首更多歌曲*"
        embed.add_field(name=f"📋 队列 ({len(queue.queue)} 首)", value=preview, inline=False)

    loop_text = {0: "关", 1: "🔂 单曲循环", 2: "🔁 列表循环"}
    embed.set_footer(text=f"循环: {loop_text[queue.loop_mode]}")

    return embed


async def _np_update_loop(guild_id: int):
    """后台任务: 每 10 秒更新「正在播放」消息的进度条"""
    queue = get_queue(guild_id)
    try:
        while True:
            await asyncio.sleep(10)
            # 退出条件: 没有在播放 / 消息不存在 / 断开连接
            if not queue.current or not queue.np_message:
                break
            if not queue.vc or not queue.vc.is_connected():
                break
            # 歌曲播完 (after_play 会处理切歌, 这里只是保险)
            elapsed = get_elapsed(queue)
            if queue.current.duration > 0 and elapsed >= queue.current.duration + 10:
                break
            # 更新进度条
            embed = create_now_playing_embed(queue.current, queue, elapsed)
            try:
                await queue.np_message.edit(embed=embed)
            except (discord.NotFound, discord.Forbidden):
                break
            except Exception:
                pass  # 网络抖动等, 忽略
    except asyncio.CancelledError:
        pass
    except Exception:
        pass


async def play_next(guild_id: int, channel):
    """播放队列中的下一首"""
    queue = get_queue(guild_id)

    if not queue.vc or not queue.vc.is_connected():
        return

    song = queue.get_next()
    if song is None:
        queue.current = None
        # 取消进度更新任务
        if queue.np_task and not queue.np_task.done():
            queue.np_task.cancel()
        # 空闲 3 分钟后自动离开
        await asyncio.sleep(180)
        if queue.vc and queue.vc.is_connected() and queue.current is None:
            await queue.vc.disconnect()
        return

    queue.current = song

    try:
        loop = asyncio.get_running_loop()
        source = await YTDLSource.from_url(song.url, loop=loop, speed=queue.speed)

        # 安全检查: 如果返回了列表 (合集/分P), 只播放第一首
        if isinstance(source, list):
            if not source:
                raise ValueError("音频源为空")
            source = source[0]

        source.volume = queue.volume

        def after_play(error):
            if error:
                print(f"[Music] 播放错误: {error}")
                # 网络中断导致的 FFmpeg 退出 → 通知频道
                asyncio.run_coroutine_threadsafe(
                    channel.send(f"⚠️ 播放中断: `{song.title}` 因网络问题被跳过"),
                    loop
                )
            else:
                # 正常结束 → 检查是否中途被截断
                elapsed = get_elapsed(queue)
                effective_duration = song.duration / queue.speed if queue.speed > 0 else song.duration
                # 如果剩余 >10 秒且进度不到 85%，很可能是流被截断了
                remaining = effective_duration - elapsed
                if remaining > 10 and effective_duration > 30 and elapsed / effective_duration < 0.85:
                    print(f"[Music] 歌曲被截断: {song.title} (已播 {elapsed:.0f}s/{effective_duration:.0f}s)")
                    asyncio.run_coroutine_threadsafe(
                        channel.send(f"⚠️ `{song.title}` 播放中断 (已播 {format_duration(elapsed)}/{song.duration_str()})，可能是网络波动"),
                        loop
                    )
            asyncio.run_coroutine_threadsafe(
                play_next(guild_id, channel), loop
            )

        # ── 重置进度追踪 ──
        queue.start_time = time.time()
        queue.pause_time = None
        queue.total_paused = 0.0

        # 取消旧的进度更新任务
        if queue.np_task and not queue.np_task.done():
            queue.np_task.cancel()

        queue.vc.play(source, after=after_play)

        embed = create_now_playing_embed(song, queue)
        queue.np_message = await channel.send(embed=embed)

        # 启动进度更新后台任务
        queue.np_task = asyncio.create_task(_np_update_loop(guild_id))

    except Exception as e:
        print(f"[Music] 播放失败: {e}")
        await channel.send(f"❌ 播放 {song.title} 时出错，正在跳过…")
        await play_next(guild_id, channel)


# ══════════════════════════════════════════════
# 合集选择 View
# ══════════════════════════════════════════════

class CollectionView(discord.ui.View):
    """Bilibili 合集选择界面: 选单首播放 / 全部播放 / 翻页"""
    def __init__(self, songs: list, ctx: commands.Context, play_single_cb, play_all_cb):
        super().__init__(timeout=120)
        self.all_songs = songs
        self.ctx = ctx
        self.play_single_cb = play_single_cb
        self.play_all_cb = play_all_cb
        self.page = 0          # 0-indexed
        self.page_size = 5
        self.message: discord.Message = None

    @property
    def total_pages(self):
        return max(1, (len(self.all_songs) - 1) // self.page_size + 1)

    def _page_songs(self) -> list:
        start = self.page * self.page_size
        return self.all_songs[start:start + self.page_size]

    def _build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=f"📚 合集 ({len(self.all_songs)} 个视频)",
            description=f"👆 **点按钮播放单集 | 📋 全部播放 | 或 `!play 1-5`** | 第 {self.page+1}/{self.total_pages} 页",
            color=0x00A1D6
        )
        for i, s in enumerate(self._page_songs(), 1):
            global_idx = self.page * self.page_size + i
            embed.add_field(
                name=f"#{global_idx}  ⏱ {s.duration_str()}",
                value=f"[{s.title}]({s.url})",
                inline=False
            )
        embed.set_footer(text=f"合集 | {self.ctx.author.display_name} | 120秒内有效")
        return embed

    def _update_buttons(self):
        page_songs = self._page_songs()
        for i in range(5):
            self.children[i].disabled = i >= len(page_songs)
        # children[5] = 上一页, [6] = 下一页, [7] = 全部播放
        self.children[5].disabled = self.page <= 0
        self.children[6].disabled = self.page >= self.total_pages - 1
        self.children[7].disabled = len(self.all_songs) == 0

    def _cache_page(self):
        """缓存当前页, 供 !play N 使用"""
        key = (self.ctx.guild.id, self.ctx.author.id)
        page_songs = self._page_songs()
        _search_cache[key] = {
            'results': [
                {'url': s.url, 'title': s.title, 'duration': s.duration, 'thumbnail': s.thumbnail}
                for s in page_songs
            ],
            'ts': time.time(),
        }

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.ctx.author:
            await interaction.response.send_message("❌ 只有搜索者可以操作", ephemeral=True)
            return False
        return True

    async def show(self):
        if not self.all_songs:
            await self.ctx.send("❌ 合集为空")
            self.stop()
            return
        self._cache_page()
        self._update_buttons()
        self.message = await self.ctx.send(embed=self._build_embed(), view=self)

    async def _reload_page(self, interaction: discord.Interaction):
        self._cache_page()
        self._update_buttons()
        await interaction.response.edit_message(embed=self._build_embed(), view=self)

    async def _select_single(self, interaction: discord.Interaction, num: int):
        """播放合集中的单首"""
        page_songs = self._page_songs()
        if num >= len(page_songs):
            return
        song = page_songs[num]
        song.requester = self.ctx.author
        self.stop()
        await interaction.response.edit_message(
            content=f"✅ 已选择: **{song.title}**，正在获取音频…",
            embed=None,
            view=None
        )
        try:
            await self.play_single_cb(self.ctx, song)
        except Exception as e:
            await self.ctx.send(f"❌ 播放失败: {e}")

    async def _play_all(self, interaction: discord.Interaction):
        """播放合集全部"""
        self.stop()
        await interaction.response.edit_message(
            content=f"📋 正在添加合集全部 {len(self.all_songs)} 个视频…",
            embed=None,
            view=None
        )
        try:
            await self.play_all_cb(self.ctx, self.all_songs)
        except Exception as e:
            await self.ctx.send(f"❌ 添加失败: {e}")

    @discord.ui.button(label="1", style=discord.ButtonStyle.primary, row=0)
    async def btn_1(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._select_single(interaction, 0)

    @discord.ui.button(label="2", style=discord.ButtonStyle.primary, row=0)
    async def btn_2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._select_single(interaction, 1)

    @discord.ui.button(label="3", style=discord.ButtonStyle.primary, row=0)
    async def btn_3(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._select_single(interaction, 2)

    @discord.ui.button(label="4", style=discord.ButtonStyle.primary, row=0)
    async def btn_4(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._select_single(interaction, 3)

    @discord.ui.button(label="5", style=discord.ButtonStyle.primary, row=0)
    async def btn_5(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._select_single(interaction, 4)

    @discord.ui.button(label="◀️ 上一页", style=discord.ButtonStyle.secondary, row=1)
    async def btn_prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
            await self._reload_page(interaction)

    @discord.ui.button(label="下一页 ▶️", style=discord.ButtonStyle.secondary, row=1)
    async def btn_next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page < self.total_pages - 1:
            self.page += 1
            await self._reload_page(interaction)

    @discord.ui.button(label="📋 全部播放", style=discord.ButtonStyle.success, row=1)
    async def btn_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._play_all(interaction)

    async def on_timeout(self):
        if self.message:
            try:
                for child in self.children:
                    child.disabled = True
                embed = self._build_embed()
                embed.color = 0x95A5A6
                embed.description = f"⏰ 合集选择已超时"
                await self.message.edit(embed=embed, view=self)
            except Exception:
                pass


# ══════════════════════════════════════════════
# 搜索结果翻页 View
# ══════════════════════════════════════════════

class SearchView(discord.ui.View):
    """Bilibili 搜索结果交互界面: 翻页 + 按钮选歌 + !play N 兼容"""
    def __init__(self, query: str, ctx: commands.Context, play_callback):
        super().__init__(timeout=120)
        self.query = query
        self.ctx = ctx
        self.play_callback = play_callback
        self.page = 1
        self.results: list[dict] = []
        self.message: discord.Message = None
        self._loading = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.ctx.author:
            await interaction.response.send_message("❌ 只有搜索者可以操作", ephemeral=True)
            return False
        return True

    def _build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=f"🔍 搜索: {self.query}",
            description=f"👆 **点击按钮 或 输入 `!play 1-5` 选歌** | 第 {self.page} 页",
            color=0x00A1D6
        )
        for i, r in enumerate(self.results, 1):
            m, s = divmod(r['duration'], 60)
            embed.add_field(
                name=f"#{i}  ⏱ {m}:{s:02d}",
                value=f"[{r['title']}]({r['url']})",
                inline=False
            )
        embed.set_footer(text=f"Bilibili | 搜索者: {self.ctx.author.display_name} | 120秒内有效")
        return embed

    def _update_buttons(self):
        for i in range(5):
            self.children[i].disabled = i >= len(self.results)
        self.children[5].disabled = self.page <= 1
        self.children[6].disabled = len(self.results) < 5

    def _cache_results(self):
        """缓存当前页搜索结果, 供 !play N 使用"""
        key = (self.ctx.guild.id, self.ctx.author.id)
        _search_cache[key] = {
            'results': self.results,
            'ts': time.time(),
        }

    async def _load_page(self):
        """加载当前页的搜索结果"""
        loop = asyncio.get_running_loop()
        self.results = await loop.run_in_executor(
            None, bilibili_search, self.query, 5, self.page
        )
        self._cache_results()

    async def show(self):
        await self._load_page()
        if not self.results:
            await self.ctx.send("❌ 搜索无结果")
            self.stop()
            return
        self._update_buttons()
        self.message = await self.ctx.send(embed=self._build_embed(), view=self)

    async def _reload_page(self, interaction: discord.Interaction):
        await self._load_page()
        if not self.results:
            self.page = max(1, self.page - 1)
            await self._load_page()
        self._update_buttons()
        await interaction.response.edit_message(embed=self._build_embed(), view=self)

    async def _select(self, interaction: discord.Interaction, num: int):
        if num >= len(self.results):
            return
        song_url = self.results[num]['url']
        song_title = self.results[num].get('title', 'Unknown')
        self.stop()
        await interaction.response.edit_message(
            content=f"✅ 已选择: **{song_title}**，正在获取音频…",
            embed=None,
            view=None
        )
        try:
            await self.play_callback(self.ctx, query=song_url)
        except Exception as e:
            await self.ctx.send(f"❌ 播放失败: {e}")

    @discord.ui.button(label="1", style=discord.ButtonStyle.primary, row=0)
    async def btn_1(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._select(interaction, 0)

    @discord.ui.button(label="2", style=discord.ButtonStyle.primary, row=0)
    async def btn_2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._select(interaction, 1)

    @discord.ui.button(label="3", style=discord.ButtonStyle.primary, row=0)
    async def btn_3(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._select(interaction, 2)

    @discord.ui.button(label="4", style=discord.ButtonStyle.primary, row=0)
    async def btn_4(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._select(interaction, 3)

    @discord.ui.button(label="5", style=discord.ButtonStyle.primary, row=0)
    async def btn_5(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._select(interaction, 4)

    @discord.ui.button(label="◀️ 上一页", style=discord.ButtonStyle.secondary, row=1)
    async def btn_prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 1 and not self._loading:
            self._loading = True
            self.page -= 1
            await self._reload_page(interaction)
            self._loading = False

    @discord.ui.button(label="下一页 ▶️", style=discord.ButtonStyle.secondary, row=1)
    async def btn_next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._loading:
            self._loading = True
            self.page += 1
            await self._reload_page(interaction)
            self._loading = False

    async def on_timeout(self):
        """超时后保留搜索结果(可见), 仅禁用按钮"""
        if self.message:
            try:
                for child in self.children:
                    child.disabled = True
                embed = self._build_embed()
                embed.color = 0x95A5A6
                embed.description = f"⏰ 搜索已超时 | 重新搜索请 `!search {self.query}`"
                await self.message.edit(embed=embed, view=self)
            except Exception:
                pass


# ══════════════════════════════════════════════
# Music Cog
# ══════════════════════════════════════════════

class Music(commands.Cog):
    """🎵 音乐播放器"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="play")
    async def play(self, ctx: commands.Context, *, query: str = None):
        """🎵 播放音乐 (搜索或 URL)"""
        if not query:
            await ctx.send("❌ 请提供歌曲名或URL！用法: `!play <歌曲名/URL>` 或先用 `!search` 搜索")
            return

        # ── 搜索结果选歌: !play 1-5 ──
        # 如果输入是纯数字 1-5 且用户近期搜索过, 直接播放对应结果
        if query.strip().isdigit():
            num = int(query.strip())
            if 1 <= num <= 5:
                key = (ctx.guild.id, ctx.author.id)
                cache = _search_cache.get(key)
                if cache and (time.time() - cache['ts'] < _SEARCH_CACHE_TTL):
                    results = cache['results']
                    if num <= len(results):
                        song_url = results[num - 1]['url']
                        song_title = results[num - 1].get('title', 'Unknown')
                        await ctx.send(f"📋 从搜索结果选择: **{song_title}**")
                        query = song_url  # 用 URL 走正常播放流程
                    else:
                        await ctx.send(f"❌ 搜索结果只有 {len(results)} 个，请输入 1-{len(results)}")
                        return
                # 如果没有缓存或已过期, 数字 1-5 也当搜索词处理 (搜 "1" 等)

        await ctx.typing()

        queue, err = await ensure_voice(ctx)
        if err:
            await ctx.send(err)
            return

        try:
            # ── 检测播放列表/合集 ──
            # YouTube: playlist 或 list= 参数
            # Bilibili 合集: medialist, collectiondetail, seriesdetail, /channel/
            # Bilibili 分P: BV URL 带 ?p= 参数 (但通常只播单集, 走普通流程)
            is_bili_collection = 'bilibili.com' in query and any(x in query for x in [
                'medialist', 'collectiondetail', 'seriesdetail', '/channel/',
            ])
            is_yt_playlist = 'playlist' in query or 'list=' in query

            if is_bili_collection:
                # ── Bilibili 合集: 提取后显示选择界面 ──
                song_list = await YTDLSource.search_playlist(query, loop=self.bot.loop)
                if not song_list:
                    await ctx.send("❌ 未找到有效视频（合集可能为空或需要登录）")
                    return
                view = CollectionView(
                    song_list, ctx,
                    play_single_cb=self._play_single_song,
                    play_all_cb=self._play_all_songs,
                )
                await view.show()
                return  # 合集选择界面会通过回调处理播放

            elif is_yt_playlist:
                # ── YouTube 播放列表: 直接全部加入 ──
                song_list = await YTDLSource.search_playlist(query, loop=self.bot.loop)
                if not song_list:
                    await ctx.send("❌ 未找到有效歌曲")
                    return
                for song in song_list:
                    song.requester = ctx.author
                    queue.add(song)
                await ctx.send(
                    f"✅ 已添加 **{len(song_list)}** 首歌曲到队列！\n"
                    f"{ctx.author.mention} 从播放列表中添加"
                )
            else:
                result = await YTDLSource.search_song(query, loop=self.bot.loop)
                if result is None:
                    await ctx.send("❌ 找不到这首歌，请尝试其他关键词")
                    return
                # 多分P视频: 显示选择界面 (同合集处理)
                if isinstance(result, list):
                    view = CollectionView(
                        result, ctx,
                        play_single_cb=self._play_single_song,
                        play_all_cb=self._play_all_songs,
                    )
                    await view.show()
                    return
                song = result
                song.requester = ctx.author
                queue.add(song)
                embed = discord.Embed(
                    title="✅ 已添加到队列",
                    description=f"[{song.title}]({song.url})",
                    color=0x1DB954
                )
                embed.add_field(name="⏱ 时长", value=song.duration_str(), inline=True)
                embed.add_field(name="📋 队列位置", value=f"#{len(queue.queue)}", inline=True)
                if song.thumbnail:
                    embed.set_thumbnail(url=song.thumbnail)
                embed.set_footer(text=f"点歌: {ctx.author.display_name}")
                await ctx.send(embed=embed)

            if not queue.vc.is_playing() and not queue.vc.is_paused():
                await play_next(ctx.guild.id, ctx.channel)
        except Exception as e:
            await ctx.send(f"❌ 搜索时出错: {e}")

    # ── CollectionView 回调 ──
    async def _play_single_song(self, ctx: commands.Context, song: Song):
        """从合集选择单首播放"""
        queue = get_queue(ctx.guild.id)
        song.requester = ctx.author
        queue.add(song)
        embed = discord.Embed(
            title="✅ 已添加到队列",
            description=f"[{song.title}]({song.url})",
            color=0x1DB954
        )
        embed.add_field(name="⏱ 时长", value=song.duration_str(), inline=True)
        embed.add_field(name="📋 队列位置", value=f"#{len(queue.queue)}", inline=True)
        if song.thumbnail:
            embed.set_thumbnail(url=song.thumbnail)
        embed.set_footer(text=f"点歌: {ctx.author.display_name}")
        await ctx.send(embed=embed)
        if not queue.vc.is_playing() and not queue.vc.is_paused():
            await play_next(ctx.guild.id, ctx.channel)

    async def _play_all_songs(self, ctx: commands.Context, songs: list):
        """从合集全部播放"""
        queue = get_queue(ctx.guild.id)
        for song in songs:
            song.requester = ctx.author
            queue.add(song)
        await ctx.send(
            f"✅ 已添加 **{len(songs)}** 首歌曲到队列！\n"
            f"{ctx.author.mention} 从 Bilibili 合集中添加"
        )
        if not queue.vc.is_playing() and not queue.vc.is_paused():
            await play_next(ctx.guild.id, ctx.channel)

    @commands.command(name="skip")
    async def skip(self, ctx: commands.Context):
        queue = get_queue(ctx.guild.id)
        if not queue.vc or not queue.vc.is_connected():
            await ctx.send("❌ Bot 不在语音频道中")
            return
        if not queue.vc.is_playing() and not queue.vc.is_paused():
            await ctx.send("❌ 当前没有在播放")
            return
        song = queue.current
        # 取消进度更新任务
        if queue.np_task and not queue.np_task.done():
            queue.np_task.cancel()
        queue.vc.stop()
        embed = discord.Embed(
            title="⏭ 已跳过",
            description=f"[{song.title}]({song.url})" if song else "Unknown",
            color=0xFEE75C
        )
        embed.set_footer(text=f"操作: {ctx.author.display_name}")
        await ctx.send(embed=embed)

    @commands.command(name="stop")
    async def stop(self, ctx: commands.Context):
        queue = get_queue(ctx.guild.id)
        if not queue.vc or not queue.vc.is_connected():
            await ctx.send("❌ Bot 不在语音频道中")
            return
        # 取消进度更新任务
        if queue.np_task and not queue.np_task.done():
            queue.np_task.cancel()
        queue.clear()
        if queue.vc.is_playing() or queue.vc.is_paused():
            queue.vc.stop()
        await ctx.send("⏹ 已停止播放并清空队列")

    @commands.command(name="pause")
    async def pause(self, ctx: commands.Context):
        queue = get_queue(ctx.guild.id)
        if not queue.vc or not queue.vc.is_playing():
            await ctx.send("❌ 当前没有在播放")
            return
        # 记录暂停时刻 (进度冻结)
        queue.pause_time = time.time()
        queue.vc.pause()
        await ctx.send("⏸ 已暂停")

    @commands.command(name="resume")
    async def resume(self, ctx: commands.Context):
        queue = get_queue(ctx.guild.id)
        if not queue.vc or not queue.vc.is_paused():
            await ctx.send("❌ 当前没有暂停")
            return
        # 累计暂停时长, 恢复进度追踪
        if queue.pause_time:
            queue.total_paused += time.time() - queue.pause_time
            queue.pause_time = None
        queue.vc.resume()
        await ctx.send("▶ 正在继续播放")

    @commands.command(name="queue")
    async def queue_cmd(self, ctx: commands.Context):
        queue = get_queue(ctx.guild.id)
        if not queue.current and not queue.queue:
            await ctx.send("📭 队列为空")
            return
        embed = discord.Embed(title="📋 播放队列", color=0x1DB954)
        if queue.current:
            prog = "▶" if queue.vc and queue.vc.is_playing() else "⏸"
            elapsed = get_elapsed(queue)
            progress_bar = make_progress_bar(elapsed, queue.current.duration)
            embed.add_field(
                name=f"{prog} 正在播放",
                value=f"[{queue.current.title}]({queue.current.url})\n{progress_bar}\n👤 {queue.current.requester.mention}",
                inline=False
            )
        if queue.queue:
            q_text = ""
            for i, song in enumerate(queue.queue, 1):
                if len(q_text) > 900:
                    q_text += f"\n*…还有 {len(queue.queue) - i + 1} 首*"
                    break
                q_text += f"`{i}.` [{song.title}]({song.url}) — `{song.duration_str()}` 👤 {song.requester.display_name}\n"
            embed.add_field(name=f"📋 队列 ({len(queue.queue)} 首)", value=q_text, inline=False)
        loop_text = {0: "关", 1: "🔂 单曲循环", 2: "🔁 列表循环"}
        embed.add_field(name="🔂 循环模式", value=loop_text[queue.loop_mode], inline=True)
        embed.add_field(name="🔊 音量", value=f"{int(queue.volume * 100)}%", inline=True)
        if queue.vc:
            duration = queue.current.duration if queue.current else 0
            total = duration + sum(s.duration for s in queue.queue)
            m, s = divmod(total, 60)
            embed.set_footer(text=f"总时长约 {m} 分 {s} 秒")
        await ctx.send(embed=embed)

    @commands.command(name="nowplaying")
    async def nowplaying(self, ctx: commands.Context):
        queue = get_queue(ctx.guild.id)
        if not queue.current:
            await ctx.send("📭 当前没有在播放")
            return
        elapsed = get_elapsed(queue)
        embed = create_now_playing_embed(queue.current, queue, elapsed)
        await ctx.send(embed=embed)

    @commands.command(name="volume")
    async def volume(self, ctx: commands.Context, level: int):
        queue = get_queue(ctx.guild.id)
        if not queue.vc:
            await ctx.send("❌ Bot 不在语音频道中")
            return
        level = max(0, min(200, level))
        queue.volume = level / 100
        if queue.vc.source:
            queue.vc.source.volume = queue.volume
        emoji = "🔊" if level >= 50 else "🔉" if level >= 10 else "🔈" if level > 0 else "🔇"
        await ctx.send(f"{emoji} 音量已设置为 **{level}%**")

    @commands.command(name="speed")
    async def speed(self, ctx: commands.Context, rate: float = None):
        """⏩ 设置播放倍速 (0.25 ~ 4.0), 不带参数查看当前倍速"""
        queue = get_queue(ctx.guild.id)

        if rate is None:
            # 查看当前倍速
            if queue.speed == 1.0:
                await ctx.send(f"⏩ 当前播放倍速: **1.0x** (正常)")
            else:
                await ctx.send(f"⏩ 当前播放倍速: **{queue.speed:g}x**")
            return

        # 设置倍速
        rate = max(0.25, min(4.0, rate))
        # 四舍五入到两位小数
        rate = round(rate * 100) / 100
        queue.speed = rate

        if rate == 1.0:
            msg = "⏩ 播放倍速已恢复为 **1.0x** (正常)"
        elif rate < 1.0:
            msg = f"🐢 播放倍速已设置为 **{rate:g}x** (慢放)"
        else:
            msg = f"🐇 播放倍速已设置为 **{rate:g}x** (快放)"

        if queue.vc and (queue.vc.is_playing() or queue.vc.is_paused()):
            msg += "\n💡 将从**下一首**开始生效"

        await ctx.send(msg)

    @commands.command(name="loop")
    async def loop(self, ctx: commands.Context, mode: int):
        if mode not in (0, 1, 2):
            await ctx.send("❌ 循环模式: 0=关, 1=单曲循环, 2=列表循环")
            return
        queue = get_queue(ctx.guild.id)
        queue.loop_mode = mode
        mode_text = {0: "关 ❌", 1: "🔂 单曲循环", 2: "🔁 列表循环"}
        await ctx.send(f"循环模式: **{mode_text[mode]}**")

    @commands.command(name="remove")
    async def remove(self, ctx: commands.Context, index: int):
        queue = get_queue(ctx.guild.id)
        if not queue.queue:
            await ctx.send("❌ 队列中没有歌曲")
            return
        song = queue.remove(index - 1)
        if song:
            await ctx.send(f"🗑 已从队列中移除: **{song.title}**")
        else:
            await ctx.send(f"❌ 找不到位置 #{index} 的歌曲")

    @commands.command(name="shuffle")
    async def shuffle(self, ctx: commands.Context):
        queue = get_queue(ctx.guild.id)
        if len(queue.queue) < 2:
            await ctx.send("❌ 队列中至少需要 2 首歌才能打乱")
            return
        queue.shuffle()
        await ctx.send("🔀 队列已随机打乱！")

    @commands.command(name="disconnect")
    async def disconnect(self, ctx: commands.Context):
        queue = get_queue(ctx.guild.id)
        if not queue.vc or not queue.vc.is_connected():
            await ctx.send("❌ Bot 不在语音频道中")
            return
        # 取消进度更新任务
        if queue.np_task and not queue.np_task.done():
            queue.np_task.cancel()
        queue.clear()
        if queue.vc.is_playing() or queue.vc.is_paused():
            queue.vc.stop()
        await queue.vc.disconnect()
        queue.vc = None
        queue.np_message = None
        await ctx.send("👋 已断开语音连接")

    @commands.command(name="search")
    async def search(self, ctx: commands.Context, *, query: str = None):
        """🔍 搜索 Bilibili 视频 (翻页+按钮选歌)"""
        if not query:
            await ctx.send("❌ 请提供搜索关键词！用法: `!search <关键词>`")
            return
        await ctx.typing()
        try:
            view = SearchView(query, ctx, self.play)
            await view.show()
        except Exception as e:
            await ctx.send(f"❌ 搜索时出错: {e}")

    # ══════════════════════════════════════════════
    #  批量加歌引擎
    # ══════════════════════════════════════════════

    @commands.command(name="batch")
    async def batch(self, ctx: commands.Context, *, queries: str = None):
        """📋 批量添加歌曲 (用 | 或换行分隔)

        用法:
          !batch 歌曲1 | 歌曲2 | 歌曲3
          !batch https://bilibili.com/video/BVxxx | 歌曲名 | 另一首歌
        每条可以是 URL 或搜索关键词，最多 20 首。
        """
        if not queries:
            await ctx.send(
                "❌ 请提供歌曲列表！用法:\n"
                "```\n!batch 歌曲1 | 歌曲2 | 歌曲3\n```\n"
                "用 `|` 或换行分隔每首歌，最多 20 首"
            )
            return

        # 解析歌曲列表 (支持 | 和换行分隔)
        items = re.split(r'[|\n]', queries)
        items = [item.strip() for item in items if item.strip()]

        if not items:
            await ctx.send("❌ 没有有效的歌曲条目")
            return

        if len(items) > 20:
            await ctx.send(f"❌ 批量添加最多 20 首，你提供了 {len(items)} 首")
            return

        # 确保在语音频道
        queue, err = await ensure_voice(ctx)
        if err:
            await ctx.send(err)
            return

        # 发送初始进度消息
        embed = discord.Embed(
            title="📋 批量添加中...",
            description=f"正在解析 **{len(items)}** 首歌曲，请稍候",
            color=0xFEE75C
        )
        embed.add_field(name="进度", value=f"`0/{len(items)}`", inline=True)
        embed.add_field(name="✅ 成功", value="0", inline=True)
        embed.add_field(name="❌ 失败", value="0", inline=True)
        embed.set_footer(text=f"操作: {ctx.author.display_name}")
        progress_msg = await ctx.send(embed=embed)

        # 逐个解析并添加
        success_list: list[Song] = []
        fail_list: list[tuple[str, str]] = []

        for i, item in enumerate(items):
            # 更新进度 (每首歌解析前更新一次)
            try:
                embed.description = f"正在解析 ({i+1}/{len(items)}): `{item[:50]}`"
                embed.clear_fields()
                embed.add_field(name="进度", value=f"`{i+1}/{len(items)}`", inline=True)
                embed.add_field(name="✅ 成功", value=str(len(success_list)), inline=True)
                embed.add_field(name="❌ 失败", value=str(len(fail_list)), inline=True)
                await progress_msg.edit(embed=embed)
            except Exception:
                pass

            try:
                result = await YTDLSource.search_song(item, loop=self.bot.loop)
                if result is None:
                    fail_list.append((item, "未找到"))
                elif isinstance(result, list):
                    # 多分P视频: 全部加入
                    for s in result:
                        s.requester = ctx.author
                        queue.add(s)
                        success_list.append(s)
                else:
                    result.requester = ctx.author
                    queue.add(result)
                    success_list.append(result)
            except Exception as e:
                fail_list.append((item, str(e)[:60]))

        # 最终结果 embed
        total_in_queue = len(queue.queue) + (1 if queue.current else 0)
        embed = discord.Embed(
            title="📋 批量添加完成",
            color=0x1DB954 if success_list else 0xED4245
        )
        embed.add_field(name="✅ 成功", value=str(len(success_list)), inline=True)
        embed.add_field(name="❌ 失败", value=str(len(fail_list)), inline=True)
        embed.add_field(name="📊 队列总数", value=str(total_in_queue), inline=True)

        # 列出成功添加的歌曲
        if success_list:
            success_text = ""
            for i, song in enumerate(success_list[:10]):
                success_text += f"`{i+1}.` [{song.title}]({song.url}) — {song.duration_str()}\n"
            if len(success_list) > 10:
                success_text += f"*…以及 {len(success_list) - 10} 首更多*"
            embed.add_field(name="已添加歌曲", value=success_text, inline=False)

        # 列出失败的歌曲
        if fail_list:
            fail_text = ""
            for item, reason in fail_list[:5]:
                fail_text += f"❌ `{item[:40]}` — {reason}\n"
            if len(fail_list) > 5:
                fail_text += f"*…以及 {len(fail_list) - 5} 首更多*"
            embed.add_field(name="失败歌曲", value=fail_text, inline=False)

        embed.set_footer(text=f"操作: {ctx.author.display_name}")
        await progress_msg.edit(embed=embed)

        # 如果没有在播放，开始播放
        if not queue.vc.is_playing() and not queue.vc.is_paused():
            await play_next(ctx.guild.id, ctx.channel)


async def init_music_bot(bot: commands.Bot):
    """注册 Music Cog"""
    await bot.add_cog(Music(bot))
    proxy_info = f", 代理: {_YTDLP_PROXY}" if _YTDLP_PROXY else ""
    print(f"[Music] 音乐模块已初始化 (!play, !search, !batch, !skip, !stop, !pause, !resume, !queue, !nowplaying, !volume, !loop, !remove, !shuffle, !disconnect){proxy_info}")
