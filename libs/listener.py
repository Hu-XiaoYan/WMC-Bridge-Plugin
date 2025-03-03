import time
import tomli
from multiprocessing import Process

from .cloudmusic import get_player_time
from .process import get_process_info, get_window_titles_by_pid

now_play_time_offset = None
end_play_time_offset = None
pid, base_address = get_process_info("cloudmusic.dll")

with open("./libs/config.toml", "rb") as f:
    config = tomli.load(f)
    now_play_time_offset = config["cloudmusic"]["cloudmusic_play_time_offset"]
    end_play_time_offset = config["cloudmusic"]["cloudmusic_play_end_time_offset"]

def listener_task(stop_event, update_queue):
    last_song = None
    while not stop_event.is_set():
        play_time_list = get_play_time()
        temp_window_title = get_window_titles_by_pid(pid)
        for i in temp_window_title:
            if i in ["桌面歌词", "桌面歌词解锁", "迷你播放器", "GDI+ Window (cloudmusic.exe)", "MSCTFIME UI", "Default IME"]:
                pass
            else:
                temp_window_title = i
                break
        song_name = temp_window_title.split("-")[0][:-1]
        artist = ""
        for i in temp_window_title.split("-"):
            if i[:-1] == song_name:
                pass
            else:
                artist += i
        artist = artist[1:]
        song_changed = (song_name != last_song)
        if update_queue:
            update_queue.put(play_time_list)
            update_queue.put(song_name)
            if song_changed:
                update_queue.put([True, song_name, artist])
            else:
                update_queue.put([False, song_name, artist])
            last_song = song_name
        time.sleep(0.5)

def get_play_time():
    play_time_list = get_player_time(base_address + now_play_time_offset, base_address + end_play_time_offset)
    return play_time_list

def start_listener(stop_event, update_queue):
    p = Process(target = listener_task, args = (stop_event, update_queue))
    p.start()
    return p