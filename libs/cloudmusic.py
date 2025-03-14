import ctypes
from win32con import PROCESS_ALL_ACCESS
from win32gui import FindWindow
from win32process import GetWindowThreadProcessId
from win32api import OpenProcess, CloseHandle

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
    return [int(now_time), int(end_time)]

def calc_offset_address(address, class_name):
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
        raise ctypes.WinError()
    CloseHandle(process_handle)
    return target_address.value

def get_offset_address(base_address, offset_list, class_name):
    temp = None
    for offset in offset_list:
        try:
            if temp:
                calc = ctypes.c_ulonglong(calc_offset_address((temp + offset), class_name)).value
                temp = calc
            else:
                calc = ctypes.c_ulonglong(calc_offset_address((base_address + offset), class_name)).value
                temp = calc
        except:
            raise
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
        raise Exception
    split_raw_data = buffer.raw[:bytes_read.value].split(b"\x00\x00")[0]
    if len(split_raw_data) % 2 == 1:
        split_raw_data += b"\x00"
    if last_data != split_raw_data:
        last_data = split_raw_data
        try:
            return split_raw_data.decode(decode_type)
        except UnicodeDecodeError:
            raise Exception