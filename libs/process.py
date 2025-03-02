import os
from win32process import EnumProcessModules, EnumProcesses, GetModuleFileNameEx, GetWindowThreadProcessId
from win32api import OpenProcess
from win32con import PROCESS_ALL_ACCESS
from win32gui import GetWindowText, EnumWindows, FindWindow

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
                    return pid, module_handle
        except:
            pass