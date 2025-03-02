import time
import tomli
from multiprocessing import Process

from .cloudmusic import get_player_time
from .process import get_process_info

now_play_time_offset = None
end_play_time_offset = None
pid, base_address = get_process_info("cloudmusic.dll")

with open("./libs/config.toml", "rb") as f:
    config = tomli.load(f)
    now_play_time_offset = config["cloudmusic"]["cloudmusic_play_time_offset"]
    end_play_time_offset = config["cloudmusic"]["cloudmusic_play_end_time_offset"]

def listener_task(stop_event, update_queue):
    while not stop_event.is_set():
        play_time_list = get_play_time()
        if update_queue:
            update_queue.put(play_time_list)
        time.sleep(0.5)

def get_play_time():
    play_time_list = get_player_time(base_address + now_play_time_offset, base_address + end_play_time_offset)
    return play_time_list

def start_listener(stop_event, update_queue):
    p = Process(target=listener_task, args=(stop_event, update_queue))
    p.start()
    return p