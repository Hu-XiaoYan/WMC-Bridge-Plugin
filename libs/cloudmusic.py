import ctypes
from win32con import PROCESS_ALL_ACCESS
from win32gui import FindWindow
from win32process import GetWindowThreadProcessId
from win32api import OpenProcess

def get_player_time(now_time_address, end_time_address):
    kernel32 = ctypes.windll.kernel32
    window_handle = FindWindow("OrpheusBrowserHost", None)
    _, pid = GetWindowThreadProcessId(window_handle)
    process_handle = OpenProcess(PROCESS_ALL_ACCESS, False, pid)
    ReadProcessMemory = kernel32.ReadProcessMemory
    ReadProcessMemory.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
    ReadProcessMemory.restype = ctypes.c_bool
    def read_memory(address):
        buffer = ctypes.create_string_buffer(8)
        bytes_read = ctypes.c_size_t()
        if not ReadProcessMemory(int(process_handle), ctypes.c_void_p(address), buffer, 8, ctypes.byref(bytes_read)) or bytes_read.value == 0:
            raise Exception(f"读取地址 {address} 失败")
        return ctypes.cast(buffer, ctypes.POINTER(ctypes.c_double)).contents.value
    now_time = read_memory(now_time_address)
    end_time = read_memory(end_time_address)
    return [now_time, end_time]