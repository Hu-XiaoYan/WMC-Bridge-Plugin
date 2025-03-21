import os
import logging
from .logger import setup_colored_log
setup_colored_log()

import win32com.client
from win32process import EnumProcessModules, EnumProcesses, GetModuleFileNameEx, GetWindowThreadProcessId
from win32api import OpenProcess
from win32con import PROCESS_ALL_ACCESS
from win32gui import GetWindowText, EnumWindows

music_platform_dict = {"网易云音乐": ["cloudmusic.exe", "cloudmusic.dll"]}

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

def detect_process(process_name):
    is_exist = False
    wmi = win32com.client.GetObject('winmgmts:')
    process_code_cov = wmi.ExecQuery('select * from Win32_Process where name=\"%s\"' %(process_name))
    if len(process_code_cov) > 0:
        is_exist = True
    return is_exist

def get_process_info(file_name):
    process_pid_list = EnumProcesses()
    for pid in process_pid_list:
        try:
            process_handle = OpenProcess(PROCESS_ALL_ACCESS, False, pid)
            process_modules = EnumProcessModules(process_handle)
            for module_handle in process_modules:
                module_path = GetModuleFileNameEx(process_handle, module_handle)
                module_filename = os.path.basename(module_path)
                if module_filename.lower() == file_name:
                    logging.debug(f"成功抓取! PID: {pid} -> 基址: {module_handle}")
                    return pid, module_handle
        except:
            pass
    logging.error("未找到程序基址! 可能是权限不足?")
    return None
    #如果获取不了基址的话...直接返回空交给前面的函数处理吧...