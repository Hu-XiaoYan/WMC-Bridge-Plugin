import ctypes
import os
import time
from win32api import OpenProcess, CloseHandle
from win32process import EnumProcessModules, GetModuleFileNameEx, GetWindowThreadProcessId
from win32con import PROCESS_ALL_ACCESS
from win32gui import FindWindow

def get_base_address(pid: int, dll_name: str = None) -> int:
    process_handle = None
    try:
        process_handle = OpenProcess(PROCESS_ALL_ACCESS, False, pid)
        process_modules = EnumProcessModules(process_handle)
        if not dll_name:
            return process_modules[0]
        for module_handle in process_modules:
            module_path = GetModuleFileNameEx(process_handle, module_handle)
            module_filename = os.path.basename(module_path)
            if module_filename.lower() == dll_name.lower():
                return module_handle
        return None
    except Exception as e:
        print(f"发生错误!\n错误原因:{str(e)}")
        return None
    finally:
        CloseHandle(process_handle)

def calc_offset_address(address: int) -> int:
    kernel32 = ctypes.windll.kernel32
    window_handle = FindWindow("DesktopLyrics", u"桌面歌词")
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

def get_offset_address(base_address: int) -> int:
    first_offset_address = ctypes.c_ulonglong(calc_offset_address(base_address + 0x01A58480)).value
    second_offset_address = ctypes.c_ulonglong(calc_offset_address(first_offset_address + 0x128)).value
    third_offset_address = ctypes.c_ulonglong(calc_offset_address(second_offset_address + 0x18)).value
    print(hex(third_offset_address))
    return third_offset_address

def get_lyrics_info(lyrics_address: int):
    global last_display_lyrics
    kernel32 = ctypes.windll.kernel32
    window_handle = FindWindow("DesktopLyrics", u"桌面歌词")
    _, pid = GetWindowThreadProcessId(window_handle)
    process_handle = OpenProcess(PROCESS_ALL_ACCESS, False, pid)
    ReadProcessMemory = kernel32.ReadProcessMemory
    ReadProcessMemory.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
    ReadProcessMemory.restype = ctypes.c_bool
    buffer = ctypes.create_string_buffer(200)
    bytes_read = ctypes.c_size_t()
    ctypes.windll.kernel32.ReadProcessMemory(int(process_handle), ctypes.c_void_p(lyrics_address), buffer, 200, ctypes.byref(bytes_read))
    if bytes_read.value == 0:
        raise Exception("读取桌面歌词数据失败")
    splited_raw_data = buffer.raw[:bytes_read.value].split(b"\x00\x00")[0]
    if len(splited_raw_data) % 2 == 1:
        splited_raw_data += b"\x00"
    if last_display_lyrics != splited_raw_data:
        last_display_lyrics = splited_raw_data
        try:
            return splited_raw_data.decode("utf-16-le")
        except UnicodeDecodeError:
            raise Exception("无法解码")

print(get_base_address(22804, "cloudmusic.dll"))
lyrics_address = get_offset_address(140720216014848)
last_display_lyrics=b''
while True:
    now_lyrics = get_lyrics_info(lyrics_address)
    if now_lyrics is not None:
        print(now_lyrics)
    time.sleep(0.1)

