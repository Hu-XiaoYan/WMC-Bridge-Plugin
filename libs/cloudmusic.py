import ctypes
import logging
from .logger import setup_colored_log
setup_colored_log()

from win32con import PROCESS_ALL_ACCESS
from win32gui import FindWindow
from win32process import GetWindowThreadProcessId
from win32api import OpenProcess, CloseHandle

def get_player_time(position_addr, end_addr):
    kernel32 = ctypes.windll.kernel32
    #根据网易云音乐主窗口类名获取HWND
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
            logging.error(f"读取播放时间地址:{address}失败!")
        return ctypes.cast(buffer, ctypes.POINTER(ctypes.c_double)).contents.value
    position_time = read_memory(position_addr)
    end_time = read_memory(end_addr)
    return [int(position_time), int(end_time)]

def calc_offset_address(address, class_name):
    #根据窗口类名获取窗口基址
    kernel32 = ctypes.windll.kernel32
    window_handle = FindWindow(class_name, None)
    _, pid = GetWindowThreadProcessId(window_handle)
    process_handle = OpenProcess(PROCESS_ALL_ACCESS, False, pid)
    target_address = ctypes.c_ulonglong()
    ReadProcessMemory = kernel32.ReadProcessMemory
    ReadProcessMemory.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
    ReadProcessMemory.restype = ctypes.c_bool
    bytes_read = ctypes.c_size_t()
    result = ReadProcessMemory(int(process_handle), ctypes.c_void_p(address), ctypes.byref(target_address), 8, ctypes.byref(bytes_read))
    if not result:
        logging.error(f"读取{target_address}处的内存失败!")
        raise ctypes.WinError()
    CloseHandle(process_handle)
    return target_address.value

def get_offset_address(base_address, offset_list, class_name):
    #计算偏移后的地址
    temp = None
    for offset in offset_list:
        try:
            if temp:
                calc = ctypes.c_ulonglong(calc_offset_address((temp + offset), class_name)).value
                temp = calc
            else:
                calc = ctypes.c_ulonglong(calc_offset_address((base_address + offset), class_name)).value
                temp = calc
        except Exception as err:
            logging.error(f"计算偏移失败! 错误信息: {err}")
            raise ctypes.WinError()
    return temp

def get_mem_info(address, class_name, buf_size, decode_type):
    last_data = b""
    kernel32 = ctypes.windll.kernel32
    window_handle = FindWindow(class_name, None)
    _, pid = GetWindowThreadProcessId(window_handle)
    process_handle = OpenProcess(PROCESS_ALL_ACCESS, False, pid)
    ReadProcessMemory = kernel32.ReadProcessMemory
    ReadProcessMemory.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
    ReadProcessMemory.restype = ctypes.c_bool
    buffer = ctypes.create_string_buffer(buf_size)
    bytes_read = ctypes.c_size_t()
    ctypes.windll.kernel32.ReadProcessMemory(int(process_handle), ctypes.c_void_p(address), buffer, buf_size, ctypes.byref(bytes_read))
    if bytes_read.value == 0:
        logging.error(f"读取:{address}内存为空!")
        return ""
    split_raw_data = buffer.raw[:bytes_read.value].split(b"\x00\x00")[0]
    if len(split_raw_data) % 2 == 1:
        split_raw_data += b"\x00"
    if last_data != split_raw_data:
        last_data = split_raw_data
        try:
            return split_raw_data.decode(decode_type)
        except UnicodeDecodeError:
            logging.error(f"以{decode_type}方式解码数据失败! 内存数据: {split_raw_data}")
            return ""