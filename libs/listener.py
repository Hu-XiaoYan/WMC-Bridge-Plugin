import time
import os
import requests
import asyncio
from multiprocessing import Process
from PIL import Image

from.cloudmusic import get_player_time, get_offect_address, get_mem_info
from .process import detect_process, get_process_info, get_window_titles_by_pid
music_platform_dict = {"网易云音乐": ["cloudmusic.exe", "cloudmusic.dll"]}

def watchdog_task(stop_event, watchdog_queue, player_platform):
    prev_status = None
    while not stop_event.is_set():
        if prev_status == None:
            prev_status = detect_process(music_platform_dict[player_platform][0])
            watchdog_queue.put({"status": prev_status, "base_address": get_process_info(music_platform_dict[player_platform][1])})
        current_status = detect_process(music_platform_dict[player_platform][0])
        if current_status != prev_status:
            prev_status = current_status
            if current_status == True:
                watchdog_queue.put({"status": prev_status, "base_address": get_process_info(music_platform_dict[player_platform][1])})
            else:
                watchdog_queue.put({"status": prev_status, "base_address": None})
        time.sleep(0.5)

def start_watchdog(stop_event, watchdog_queue, player_platform):
    p = Process(target = watchdog_task, args = (stop_event, watchdog_queue, player_platform))
    p.start()
    return p

def listener_task(stop_event, listener_queue, base_addr, now_play_addr
, end_play_addr, song_lyric_offset, song_id_offect):
    last_played_song = None
    last_song_id = None
    while not stop_event.is_set():
        try:
            temp_window_title = get_window_titles_by_pid(base_addr[0])
            for title in temp_window_title:
                if title not in ["桌面歌词", "桌面歌词解锁", "迷你播放器", "GDI+ Window (cloudmusic.exe)", "MSCTFIME UI", "Default IME"]:
                    temp_window_title = title
                    break
            song_name, song_artist = temp_window_title.split(" - ", 1)
        except:
            song_name = "获取歌名失败"
            song_artist = "获取艺术家失败"
        play_time_list = get_player_time(base_addr[1] + now_play_addr, base_addr[1] + end_play_addr)
        song_id_addr = get_offect_address(base_addr[1], song_id_offect, "OrpheusBrowserHost")
        song_id = get_mem_info(song_id_addr, "OrpheusBrowserHost", 20, "utf-8").split("_")[0]
        song_lryic_addr = get_offect_address(base_addr[1], song_lyric_offset, "DesktopLyrics")
        song_lryic = get_mem_info(song_lryic_addr, "DesktopLyrics", 200, "utf-16-le")
        song_changed = (song_name != last_played_song)
        if song_changed:
            if not os.path.exists("./cache"):
                os.makedirs("./cache")
            while last_song_id == song_id:
                song_id = get_mem_info(song_id_addr, "OrpheusBrowserHost", 20, "utf-8").split("_")[0]
            img_data =  start_download_cover(song_id)
            if img_data == None:
                cover_ready = False
            else:
                cover_ready = True
        last_played_song = song_name
        last_song_id = song_id
        listener_queue.put({"cover_status": cover_ready, "song_name": song_name, "song_artist": song_artist,
"play_progress":[format_time(play_time_list[0]), format_time(play_time_list[1])],
"original_progress": [format_original_time(play_time_list[0]), format_original_time(play_time_list[1])],
"lryic": song_lryic, "cover_img": img_data})
        time.sleep(0.5)

async def download_task(song_id):
    if os.path.exists(f"./cache/{song_id}.jpg"):
        return "file_exists"
    elif not os.path.exists(f"./cache/{song_id}.jpg"):
        song_info = requests.get(f"https://music.163.com/api/song/detail?ids=[{song_id}]")
        song_info_dict = song_info.json()
        song_cover_url = song_info_dict["songs"][0]["album"]["picUrl"] + "?param=180y180"
        img_data = requests.get(song_cover_url).content
        with open(f"./cache/{song_id}.jpg", "wb") as f:
            f.write(img_data)
        return "dl_ok"

def start_download_cover(song_id):
    if asyncio.run(download_task(song_id)) == "file_exists":
        return Image.open(f"./cache/{song_id}.jpg")
    elif asyncio.run(download_task(song_id)) == "dl_ok":
        return Image.open(f"./cache/{song_id}.jpg")
    else:
        return None

def format_time(time):
    return f"{time//60%60:02d}:{time%60:02d}"

def format_original_time(time):
    return [int(f"{time//60%60:02d}"), int(f"{time%60:02d}")]

def start_listener(stop_event, listener_queue, base_addr, now_play_addr, end_play_addr,
song_lyric_offset, song_id_offect):
    p = Process(target = listener_task, args = (stop_event, listener_queue, base_addr, now_play_addr, end_play_addr, 
song_lyric_offset, song_id_offect))
    p.start()
    return p