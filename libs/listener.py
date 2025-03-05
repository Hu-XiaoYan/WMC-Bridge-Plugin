import time
import requests
from multiprocessing import Process

from .cloudmusic import get_player_time, get_mem_info, get_offect_address
from .process import get_process_info, get_window_titles_by_pid, detect_process

def watchdog_task(stop_event, watchdog_queue):
    prev_status = None
    while not stop_event.is_set():
        if prev_status == None:
            prev_status = detect_process("cloudmusic.exe")
            watchdog_queue.put({"status": prev_status, "platform": "cloudmusic", "base_address": get_process_info("cloudmusic.dll")})
        current_status = detect_process("cloudmusic.exe")
        if current_status != prev_status:
            prev_status = current_status
            if current_status == True:
                watchdog_queue.put({"status": prev_status, "platform": "cloudmusic", "base_address": get_process_info("cloudmusic.dll")})
            else:
                watchdog_queue.put({"status": prev_status, "platform": "cloudmusic", "base_address": None})
        time.sleep(0.5)

def start_watchdog(stop_event, watchdog_queue):
    p = Process(target = watchdog_task, args = (stop_event, watchdog_queue))
    p.start()
    return p

def listener_task(stop_event, listener_queue, now_play_addr, end_play_addr, base_addr, lyric_offset, song_id_offset):
    last_song = None
    cover_url = None
    while not stop_event.is_set():
        try:
            temp_window_title = get_window_titles_by_pid(base_addr[0])
            for title in temp_window_title:
                if title not in ["桌面歌词", "桌面歌词解锁", "迷你播放器", "GDI+ Window (cloudmusic.exe)", "MSCTFIME UI", "Default IME"]:
                    temp_window_title = title
                    break
            song_name, artist = temp_window_title.split(" - ", 1)
        except:
            song_name = "获取歌名失败"
            artist = "获取艺术家失败"
        play_time_list = get_player_time(base_addr[1] + now_play_addr, base_addr[1] + end_play_addr)
        song_changed = (song_name != last_song)
        last_song = song_name
        song_lryic_addr = get_offect_address(base_addr[1], lyric_offset, "DesktopLyrics")
        song_lryic = get_mem_info(song_lryic_addr, "DesktopLyrics", 200, "utf-16-le")
        if song_changed:
            try:
                song_id_addr = get_offect_address(base_addr[1], song_id_offset, "OrpheusBrowserHost")
                song_id = get_mem_info(song_id_addr, "OrpheusBrowserHost", 20, "utf-8").split("_")[0]
                song_info = requests.get(f"https://music.163.com/api/song/detail?ids=[{song_id}]")
                song_info_dict = song_info.json()
                song_cover_url = song_info_dict["songs"][0]["album"]["picUrl"]
                cover_url = song_cover_url + "?param=175y175"
            except:
                listener_queue.put({"status": song_changed, "song_name": song_name, "song_artist": artist,
"play_progress":[format_time(play_time_list[0]), format_time(play_time_list[1])], "image_url": None, "lryic": None,
"original_progress": None})
        listener_queue.put({"status": song_changed, "song_name": song_name, "song_artist": artist,
"play_progress":[format_time(play_time_list[0]), format_time(play_time_list[1])], "image_url": cover_url, "lryic": song_lryic,
"original_progress": [format_original_time(play_time_list[0]), format_original_time(play_time_list[1])]})
        time.sleep(0.5)

def format_time(time):
    return f"{time//60%60:02d}:{time%60:02d}"

def format_original_time(time):
    return [int(f"{time//60%60:02d}"), int(f"{time%60:02d}")]

def start_listener(stop_event, listener_queue, now_play_addr, end_play_addr, base_addr, lyric_offset, song_id_offset):
    p = Process(target = listener_task, args = (stop_event, listener_queue, now_play_addr, end_play_addr, base_addr, lyric_offset, song_id_offset))
    p.start()
    return p
