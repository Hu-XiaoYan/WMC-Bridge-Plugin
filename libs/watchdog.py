import ctypes
import ctypes.wintypes as wt
import logging
import time

user32 = ctypes.WinDLL("user32", use_last_error = True)
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
user32.EnumWindows.argtypes = [WNDENUMPROC, wt.LPARAM]

#候选播放器窗口: (窗口类名, 标题关键字)  标题关键字为 None 表示不校验标题
#网易云 3.0+ = CEF 外壳; 标题关键字留空表示不校验
PLAYER_WINDOWS = [("OrpheusBrowserHost", None)]

def enum_top_windows():
    #枚举所有顶层窗口(不筛可见性, 缩托盘隐藏的窗口也要算)
    windows = []
    def enum_callback(window_handle, _):
        class_name = ctypes.create_unicode_buffer(256)
        title = ctypes.create_unicode_buffer(512)
        user32.GetClassNameW(window_handle, class_name, 256)
        user32.GetWindowTextW(window_handle, title, 512)
        windows.append((window_handle, class_name.value, title.value))
        return True
    user32.EnumWindows(WNDENUMPROC(enum_callback), 0)
    return windows

def find_player_window(matchers = PLAYER_WINDOWS):
    #返回(窗口句柄, pid, 命中的窗口类名), 找不到就是(None, None, None)
    for window_handle, class_name, title in enum_top_windows():
        for match_class, match_title in matchers:
            if class_name != match_class:
                continue
            if match_title and match_title not in title:
                continue
            pid = wt.DWORD(0)
            user32.GetWindowThreadProcessId(window_handle, ctypes.byref(pid))
            return window_handle, pid.value, class_name
    return None, None, None

def get_window_title(window_handle):
    title = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(window_handle, title, 512)
    return title.value

def current_player_title(matchers = PLAYER_WINDOWS):
    #当前播放器的窗口标题(也就是"歌名 - 艺术家"), 拿不到就是空串
    window_handle, pid, matched_class = find_player_window(matchers)
    return get_window_title(window_handle) if window_handle else ""

def watchdog_task(watchdog_queue, platform, matchers = PLAYER_WINDOWS):
    prev_status = None
    prev_pid = None
    while True:
        window_handle, pid, matched_class = find_player_window(matchers)
        current_status = window_handle is not None
        #状态或pid变了才上报, 避免刷队列
        if current_status != prev_status or pid != prev_pid:
            prev_status = current_status
            prev_pid = pid
            if current_status:
                watchdog_queue.put({"status": True, "pid": pid, "window_handle": window_handle,
"window_class": matched_class})
                logging.debug(f"检测到{platform}进程! pid={pid} 窗口类={matched_class}")
            else:
                watchdog_queue.put({"status": False, "pid": None, "window_handle": None,
"window_class": None})
                logging.debug(f"未检测到{platform}进程 或已退出!")
        time.sleep(0.25)
