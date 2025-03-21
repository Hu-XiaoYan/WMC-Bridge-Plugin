import time
import logging
from .logger import setup_colored_log
setup_colored_log()
from multiprocessing import Process

from .process import music_platform_dict, detect_process, get_process_info

def watchdog_task(stop_event, watchdog_queue, player_platform):
    prev_status = None
    while not stop_event.is_set():
        current_status = detect_process(music_platform_dict[player_platform][0])
        if current_status != prev_status:
            prev_status = current_status
            if current_status == True:
                watchdog_queue.put({"status": prev_status, "base_address": get_process_info(music_platform_dict[player_platform][1])})
                logging.debug(f"检测到{player_platform}进程!")
            else:
                watchdog_queue.put({"status": prev_status, "base_address": None})
                logging.debug(f"未检测到{player_platform}进程 或已退出!")
        time.sleep(0.5)

def start_watchdog(stop_event, watchdog_queue, player_platform):
    p = Process(target = watchdog_task, args = (stop_event, watchdog_queue, player_platform))
    p.start()
    return p