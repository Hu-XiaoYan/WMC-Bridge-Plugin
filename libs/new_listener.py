import time
from multiprocessing import Process
from .process import get_process_info, get_window_titles_by_pid, detect_process

def watchdog_task(stop_event, watchdog_queue):
    while not stop_event.is_set():
        if detect_process("cloudmusic.exe"):
            watchdog_queue.put({"status": True, "platform": "cloudmusic"})
        else:
            watchdog_queue.put({"status": False, "platform": None})
        time.sleep(0.5)

def start_watchdog(stop_event, watchdog_queue):
    p = Process(target = watchdog_task, args = (stop_event, watchdog_queue))
    p.start()
    return p