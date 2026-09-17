import os
import logging
import subprocess

import psutil
from win32process import EnumProcessModules, GetModuleFileNameEx, GetWindowThreadProcessId, EnumProcesses
from win32api import OpenProcess
from win32con import PROCESS_ALL_ACCESS
from win32gui import GetWindowText, EnumWindows

def get_window_titles_by_pid(target_pid):
    titles = []
    def enum_window_callback(hwnd, _):
        _, pid = GetWindowThreadProcessId(hwnd)
        if pid == target_pid:
            title = GetWindowText(hwnd)
            if title:
                titles.append(title)
        return True
    EnumWindows(enum_window_callback, None)
    return titles

#由于win32com非线程安全, 优化了进程检测
def detect_process(process_name):
    try:
        # 获取所有进程列表
        output = subprocess.check_output("tasklist", encoding = "gbk", errors = "ignore")
        return process_name.lower() in output.lower()
    except subprocess.SubprocessError as err:
        logging.error(f"无法获取进程列表! {err}")
        return False

def get_process_info(file_name, dll_name):
    pid_list = []
    for process in psutil.process_iter(attrs=['name']):
        if process.info['name'].lower() == file_name and get_window_titles_by_pid(process.pid) != []:
            if get_window_titles_by_pid(process.pid) == ["Default IME"]:
               pass
            else: 
                pid_list.append(process.pid)
    logging.debug(f"成功抓取PID: {pid_list}")
    if pid_list != []:
        try:
            for pid in pid_list:
                process_handle = OpenProcess(PROCESS_ALL_ACCESS, False, pid)
                process_modules = EnumProcessModules(process_handle)
                for module_handle in process_modules:
                    module_path = GetModuleFileNameEx(process_handle, module_handle)
                    module_filename = os.path.basename(module_path)
                    if module_filename.lower() == dll_name:
                        logging.debug(f"成功抓取基址: {module_handle}")
                        return pid, module_handle
        except:
            pass
    logging.error("未找到程序基址!")
    #如果获取不了基址的话...直接返回空交给前面的函数处理吧...
    return None