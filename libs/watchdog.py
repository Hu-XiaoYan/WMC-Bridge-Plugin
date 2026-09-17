import time
import logging

from .process import detect_process, get_process_info

def watchdog_task(watchdog_queue, process_filename_list, platform):
    prev_status = None
    while True:
        current_status = detect_process(process_filename_list[0])
        if current_status != prev_status:
            prev_status = current_status
            if current_status == True:
                watchdog_queue.put({"status": prev_status,
"base_address": get_process_info(process_filename_list[0], process_filename_list[1])})
                logging.debug(f"检测到{platform}进程!")
            else:
                watchdog_queue.put({"status": prev_status, "base_address": None})
                logging.debug(f"未检测到{platform}进程 或已退出!")
        time.sleep(0.25)