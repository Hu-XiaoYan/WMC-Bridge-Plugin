"""汽水音乐: 元数据走它自己的 SMTC 会话, 位置走锚点+时钟, 歌词从内存里捞。

它的 SMTC 时间轴是坏的(只在 拖动/暂停/恢复/换歌 时推一次), 但那几次的值很准;
歌词则完全不经过网络, 直接在渲染进程内存里找 KRC/LRC 字符串。
"""

import logging
import os
import time

from . import mem, paths, sodalyric, sodashare
from .positions import SmtcAnchorPosition
from .smtc import SmtcReader
from .watchdog import list_process_pids

CHECK_INTERVAL = 0.25
APP_ID = "汽水音乐"       #它在系统里的会话名就是这个
PLATFORM = "soda"         #落盘目录用它
LYRIC_RETRY = 8           #换歌后歌词可能还没加载完, 隔几轮再找
MEDIA_REFRESH = 4         #每 4 轮(1秒)刷一次歌名/艺术家
COVER_SETTLE = 4          #换歌后隔 1 秒复查封面(汽水的缩略图偶尔慢半拍)


def format_time(seconds):
    seconds = int(seconds)
    return f"{seconds // 60 % 60:02d}:{seconds % 60:02d}"


def write_output(song_name, song_artist, position, duration, lyric, trans_lyric = None):
    #Tuna 读的就是这个文件, 格式和 legacy 保持一致
    content = (f"正在播放:{song_name}-{song_artist}  {format_time(position)}:{format_time(duration)}\n"
f"{lyric or ''}\n{trans_lyric or ''}")
    paths.ensure(PLATFORM)
    if not os.path.exists(paths.platform_dir(PLATFORM)):
        os.makedirs(paths.platform_dir(PLATFORM))
    with open(paths.output_path(PLATFORM), "w", encoding = "UTF-8") as f:
        f.writelines(content)


def save_cover(reader, key, force = False):
    #汽水的封面只在 SMTC 的流里, 没有 URL; 存下来给界面用
    #force 用来在换歌后复查一次(汽水的缩略图有时慢半拍, 换歌瞬间拿到的还是上一首)
    if not force:
        if os.path.exists(paths.cover_path(PLATFORM, key, "jpg")):
            return paths.cover_path(PLATFORM, key, "jpg")
        if os.path.exists(paths.cover_path(PLATFORM, key, "png")):
            return paths.cover_path(PLATFORM, key, "png")
    data = reader.thumbnail_bytes(APP_ID)
    if not data:
        return None
    ext = "png" if data[:4] == b"\x89PNG" else "jpg"
    path = paths.cover_path(PLATFORM, key, ext)
    if force and os.path.exists(path):
        with open(path, "rb") as f:
            if f.read() == data:
                return path                    #没变就别重复写盘
    paths.ensure(PLATFORM)
    with open(path, "wb") as f:
        f.write(data)
    logging.debug(f"封面已存: {path} ({len(data)} 字节)")
    return path


def find_lyrics(window_pid, title, artist, duration):
    #优先走公开分享页(免签名, 0.7秒, 时间轴精确):
    #   歌名+艺术家 -> 磁盘缓存的 track_id -> 分享页歌词
    #只有第一次听某首歌才需要扫内存拿 id
    track_id = sodalyric.load_track_id(title, artist)
    if not track_id:
        track_id = scan_for_track_id(window_pid, title)
        if track_id:
            sodalyric.save_track_id(title, artist, track_id)
    if track_id:
        #拿到ID就以分享页为准, 分享页没有歌词就是没有, 不再去扫内存
        return sodashare.get_lyrics(track_id), []
    #兜底: 完全拿不到 id 时才扫内存里的歌词(慢, 但能用)
    logging.debug("没拿到曲目ID, 退回内存里找歌词")
    return scan_for_lyrics(window_pid, title, duration)


def scan_for_track_id(window_pid, title):
    if not title:
        return None
    pids = [window_pid] + [pid for pid in list_process_pids("soda") if pid != window_pid]
    for pid in pids:
        handle = mem.open_player(pid)
        if handle is None:
            continue
        try:
            track = sodalyric.find_track(handle, title)
        except Exception as err:
            logging.debug(f"在 pid={pid} 里找曲目ID失败: {err}")
            track = None
        finally:
            mem.close_player(handle)
        if track:
            return track["id"]
    return None


def scan_for_lyrics(window_pid, title, duration):
    #流程: 先按歌名定位曲目(拿真 id) -> 查磁盘缓存 -> 没命中才扫内存 -> 按 id 存盘
    #歌词可能在任意一个汽水进程里(主窗口/桌面歌词/任务栏挂件), 挨个找
    pids = [window_pid] + [pid for pid in list_process_pids("soda") if pid != window_pid]
    fallback = None
    for pid in pids:
        handle = mem.open_player(pid)
        if handle is None:
            continue
        track = None
        try:
            track = sodalyric.find_track(handle, title)
            if track and track["duration"] > 5:
                duration = track["duration"]              #用曲目里的准确时长
            if track:
                cached = sodalyric.load_cached(track["id"])
                if cached:
                    return cached
            lines, trans_lines, matched = sodalyric.extract(handle, duration, exact = track is not None)
        finally:
            mem.close_player(handle)
        if lines and matched:
            logging.debug(f"歌词来自 pid={pid}: {len(lines)} 行 "
f"(翻译 {len(trans_lines)} 行, 时长吻合)")
            if track:
                sodalyric.save_cached(track["id"], lines, trans_lines)
            return lines, trans_lines
        if lines and fallback is None:
            fallback = (lines, trans_lines)
    if fallback:
        logging.warning(f"没有时长吻合的歌词, 先用 {len(fallback[0])} 行顶着")
    else:
        logging.warning("所有汽水进程里都没找到歌词")
    return fallback or ([], [])


def listener_task(stop_event, listener_queue, pid):
    reader = SmtcReader()
    position_source = SmtcAnchorPosition(reader, APP_ID)

    last_title = None
    last_content = None
    song_key = None
    cover_path = None
    lyric_lines = []
    trans_lines = []
    cursor = [0]
    trans_cursor = [0]
    lyric_wait = 0
    cover_wait = 0
    tick = 0
    wait_notice = 0.0

    while not stop_event.wait(CHECK_INTERVAL):
        if not position_source.update():
            #汽水没在播放时根本不发布会话, 给界面一个反馈, 别让它停在旧文字上
            if time.time() - wait_notice > 2.0:
                wait_notice = time.time()
                listener_queue.put({"status": False, "song_name": "等待汽水音乐播放",
"song_artist": "", "play_progress": ["--:--", "--:--"],
"progress_seconds": [0.0, 0.0], "playing": False, "cover_ready": False,
"cover_path": None, "song_id": None, "lyric": None, "trans_lyric": None})
            continue
        position = position_source.position()
        if position is None:
            continue
        duration = position_source.duration()
        song_changed = False

        #歌名/艺术家要异步取, 1 秒刷一次就够
        tick += 1
        if last_title is None or tick % MEDIA_REFRESH == 0:
            position_source.refresh_media_properties()
        title, artist = position_source.title_artist()

        if title and title != last_title:
            last_title = title
            song_key = paths.song_key(title or "?", artist or "?")
            lyric_lines = []
            trans_lines = []
            cursor = [0]
            trans_cursor = [0]
            lyric_wait = LYRIC_RETRY
            cover_wait = COVER_SETTLE      #换歌瞬间的缩略图还是上一首的, 等一秒再取
            logging.debug(f"汽水换歌: {title} - {artist}")

        if cover_wait > 0:
            #换歌那一下拿到的封面是上一首的(实测), 等一秒再取一次准的
            cover_wait -= 1
            if cover_wait <= 0:
                if song_key:
                    fresh = save_cover(reader, song_key)
                    if fresh:
                        cover_path = fresh
                #"换歌"这件事等封面就绪之后再上报, 免得拿旧封面配新歌名
                song_changed = True
                logging.debug(f"封面就绪: {cover_path}")

        if lyric_wait > 0:
            #歌词是异步加载的, 换歌后隔几轮再找
            lyric_wait -= 1
            if lyric_wait <= 0:
                try:
                    lyric_lines, trans_lines = find_lyrics(pid, title, artist, duration)
                except Exception as err:
                    #找歌词失败不能把整个监听线程带走
                    logging.error(f"找歌词失败(跳过这首歌的歌词): {err}")

        index = sodalyric.line_index(lyric_lines, position, cursor) if lyric_lines else None
        lyric = lyric_lines[index]["text"] if index is not None else None
        #翻译独立按位置找, 免得行数和原文差一行就整体错位
        trans_lyric = sodalyric.find_current(trans_lines, position, trans_cursor) if trans_lines else None
        if trans_lyric == lyric:
            trans_lyric = None
        content = f"{title}-{artist}{format_time(position)}{lyric}{trans_lyric}"
        if content != last_content:
            write_output(title or "", artist or "", position, duration, lyric, trans_lyric)
            last_content = content

        listener_queue.put({"status": song_changed, "song_name": title or "",
"song_artist": artist or "",
"play_progress": [format_time(position), format_time(duration)],
"progress_seconds": [position, duration], "playing": position_source.playing(),
"cover_ready": cover_path is not None, "cover_path": cover_path,
"song_id": song_key, "lyric": lyric, "trans_lyric": trans_lyric})

    logging.debug("汽水 Listener 顺利退出!")
