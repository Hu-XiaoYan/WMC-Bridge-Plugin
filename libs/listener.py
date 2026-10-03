import logging
import os

from . import cloudmusic, lyric, mem, paths
from .watchdog import current_player_title

CHECK_INTERVAL = 0.25     #和 legacy 一样 250ms 一轮
PLAY_TOLERANCE = 0.6      #判定"在播"的容差(占间隔的比例)
PLATFORM = "netease"

def format_time(seconds):
    seconds = int(seconds)
    return f"{seconds // 60 % 60:02d}:{seconds % 60:02d}"

def split_title(title):
    #窗口标题就是"歌名 - 艺术家"
    if " - " in title:
        song_name, song_artist = title.split(" - ", 1)
        return song_name, song_artist
    return title, ""

def match_song(detail, song_name, song_artist):
    #用接口返回的名字/艺术家反过来验证内存里抓到的ID对不对
    if not detail:
        return False
    api_name = (detail.get("name") or "").strip().lower()
    title = song_name.strip().lower()
    if not api_name or not (api_name == title or title.startswith(api_name) or api_name.startswith(title)):
        return False
    artists = [artist for artist in detail.get("artists", []) if artist]
    if not artists:
        return True
    return any(artist in song_artist for artist in artists)

def write_output(song_name, song_artist, position, duration, normal_lyric, trans_lyric):
    #Tuna 读的就是这个文件, 格式和 legacy 保持一致
    content = (f"正在播放:{song_name}-{song_artist}  {format_time(position)}:{format_time(duration)}\n"
f"{normal_lyric or ''}\n{trans_lyric or ''}")
    paths.ensure(PLATFORM)
    with open(paths.output_path(PLATFORM), "w", encoding = "UTF-8") as f:
        f.writelines(content)

def is_playing(raw_position, last_position):
    #位置按间隔稳定前进就是在播; 切歌/拖动会大跳, 也算在播
    if raw_position < 0:
        return False
    if last_position is None or last_position < 0:
        return True
    delta = raw_position - last_position
    if delta < 0 or delta > CHECK_INTERVAL * 2:
        return True
    return abs(delta - CHECK_INTERVAL) < CHECK_INTERVAL * PLAY_TOLERANCE

def listener_task(stop_event, listener_queue, pid):
    handle = mem.open_player(pid)
    if handle is None:
        return
    try:
        base, size, module_path = mem.get_module(handle)
        if base is None:
            return
        address, rva, source = mem.resolve_position(handle, base, module_path, stop_event)
        if address is None:
            return
        logging.debug(f"Listener 就绪: position 地址=0x{address:x} (来源: {source})")

        last_title = None
        last_content = None
        last_position = None
        song_id = None
        duration = 0
        cover_path = None
        normal_lines = trans_lines = None
        normal_times = trans_times = None
        normal_cursor = [0]
        trans_cursor = [0]

        while not stop_event.wait(CHECK_INTERVAL):
            raw_position = mem.read_double(handle, address)
            if raw_position is None:
                logging.warning("读 position 失败, 播放器可能已退出")
                break
            position = raw_position if raw_position >= 0 else 0.0    #-1.0 是"没有播放位置"哨兵
            playing = is_playing(raw_position, last_position)
            last_position = raw_position

            title = current_player_title()
            song_name, song_artist = split_title(title)
            song_changed = title != last_title

            if song_changed:
                last_title = title
                song_id = None
                duration = 0
                cover_path = None
                normal_lines = trans_lines = None
                normal_times = trans_times = None
                normal_cursor = [0]
                trans_cursor = [0]
                if song_name:
                    logging.debug(f"换歌: {song_name} - {song_artist}")
                    for candidate in mem.find_song_candidates(handle, song_name):
                        detail = cloudmusic.get_song_detail(candidate["id"])
                        if not match_song(detail, song_name, song_artist):
                            logging.debug(f"候选 {candidate['id']} 不匹配"
f"({detail.get('name') if detail else '接口没返回'}), 跳过")
                            continue
                        song_id = candidate["id"]
                        duration = (detail.get("duration") or candidate["duration"]) / 1000
                        cover_path = cloudmusic.start_download_cover(song_id, detail.get("cover_url"))
                        normal_lrc, trans_lrc = cloudmusic.get_lyric(song_id)
                        if normal_lrc:
                            normal_lines, normal_times = lyric.parse_lrc(normal_lrc)
                        if trans_lrc:
                            trans_lines, trans_times = lyric.parse_lrc(trans_lrc)
                        break
                    if song_id is None:
                        logging.warning(f"没能确认 {song_name} 的歌曲ID, 请尝试切歌来重新获取歌曲ID")

            normal_lyric = lyric.find_current_lyric(normal_lines, normal_times, position,
normal_cursor) if normal_lines else None
            trans_lyric = lyric.find_current_lyric(trans_lines, trans_times, position,
trans_cursor) if trans_lines else None

            content = f"{song_name}-{song_artist}{format_time(position)}{normal_lyric}{trans_lyric}"
            if content != last_content:     #内容变了才动磁盘
                write_output(song_name, song_artist, position, duration, normal_lyric, trans_lyric)
                last_content = content

            listener_queue.put({"status": song_changed, "song_name": song_name,
"song_artist": song_artist,
"play_progress": [format_time(position), format_time(duration)],
"progress_seconds": [position, duration], "playing": playing,
"cover_ready": cover_path is not None, "cover_path": cover_path,
"song_id": song_id,
"lyric": normal_lyric, "trans_lyric": trans_lyric})
    finally:
        mem.close_player(handle)
        logging.debug("Listener 顺利退出!")
