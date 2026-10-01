import array
import ctypes
import ctypes.wintypes as wt
import json
import logging
import os
import re
import struct
import time

kernel32 = ctypes.WinDLL("kernel32", use_last_error = True)
psapi = ctypes.WinDLL("psapi", use_last_error = True)

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
LIST_MODULES_ALL = 0x03
IMAGE_SCN_MEM_EXECUTE = 0x20000000
IMAGE_SCN_MEM_WRITE = 0x80000000
MEM_COMMIT = 0x1000
MEM_PRIVATE = 0x20000
PAGE_NOACCESS = 0x01
PAGE_GUARD = 0x100
HEAP_CHUNK = 8 * 1024 * 1024
#从播放列表 JSON 里抠歌曲信息
ID_PATTERN = re.compile(rb'"id"\s*:\s*"?(\d{5,12})')
DURATION_PATTERN = re.compile(rb'"duration"\s*:\s*(\d{4,8})')
COMMENT_PATTERN = re.compile(rb'"commentThreadId"\s*:\s*"R_SO_4_(\d+)"')

#网易云的播放位置是 cloudmusic.dll 里的一个全局 float64(秒), 靠 AOB 定位
MODULE_NAME = "cloudmusic.dll"
CACHE_PATH = "./data/cache/position.json"
CACHE_VERSION = 2
#内置签名 = 操作码前缀 + 末尾 4 字节 disp32 通配; 取自实机 3.1.41.205529
POSITION_SIGNATURES = ["F2 0F 11 3D ?? ?? ?? ??"]
#网易云拿 -1.0 表示"当前没有播放位置"(没加载歌曲/已停止), 别把它当垃圾值
NO_POSITION = -1.0

#差分扫描: 读两遍可写节, 找"Δ 正好等于间隔"的那个变量
SCAN_INTERVAL = 6.0
SCAN_TOLERANCE = 0.4
SCAN_MAX_POSITION = 3600
SCAN_TYPES = [("d", 8, 1.0, "float64秒"), ("f", 4, 1.0, "float32秒"),
              ("i", 4, 1000.0, "int32毫秒"), ("q", 8, 1000.0, "int64毫秒")]

#能被用来读写这个变量的 SSE 指令形态(操作码部分, 不含 ModRM)
OPCODE_SHAPES = (b"\xf2\x0f\x11", b"\xf2\x0f\x10", b"\x66\x0f\x2e", b"\x66\x0f\x2f",
                 b"\xf3\x0f\x11", b"\xf3\x0f\x10", b"\xf2\x0f\x59", b"\xf2\x0f\x5c",
                 b"\x0f\x11", b"\x0f\x10", b"\x0f\x2e", b"\x0f\x2f")
#ModRM 里 mod=00 且 rm=101 才是 RIP 相对寻址
RIP_MODRM = (0x05, 0x0D, 0x15, 0x1D, 0x25, 0x2D, 0x35, 0x3D)

kernel32.OpenProcess.restype = wt.HANDLE
kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
kernel32.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
kernel32.ReadProcessMemory.restype = wt.BOOL
kernel32.CloseHandle.argtypes = [wt.HANDLE]
psapi.EnumProcessModulesEx.argtypes = [wt.HANDLE, ctypes.POINTER(wt.HMODULE), wt.DWORD,
ctypes.POINTER(wt.DWORD), wt.DWORD]
psapi.GetModuleBaseNameW.argtypes = [wt.HANDLE, wt.HMODULE, wt.LPWSTR, wt.DWORD]
psapi.GetModuleFileNameExW.argtypes = [wt.HANDLE, wt.HMODULE, wt.LPWSTR, wt.DWORD]

class MODULEINFO(ctypes.Structure):
    _fields_ = [("lpBaseOfDll", ctypes.c_void_p), ("SizeOfImage", wt.DWORD),
("EntryPoint", ctypes.c_void_p)]

psapi.GetModuleInformation.argtypes = [wt.HANDLE, wt.HMODULE, ctypes.POINTER(MODULEINFO), wt.DWORD]

class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
("AllocationProtect", wt.DWORD), ("PartitionId", wt.WORD), ("RegionSize", ctypes.c_size_t),
("State", wt.DWORD), ("Protect", wt.DWORD), ("Type", wt.DWORD)]

kernel32.VirtualQueryEx.argtypes = [wt.HANDLE, ctypes.c_void_p,
ctypes.POINTER(MEMORY_BASIC_INFORMATION), ctypes.c_size_t]
kernel32.VirtualQueryEx.restype = ctypes.c_size_t

def open_player(pid):
    handle = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
    if not handle:
        logging.error(f"打开进程失败! err={ctypes.get_last_error()} (5=拒绝访问, 试试以管理员身份运行)")
    return handle

def close_player(handle):
    kernel32.CloseHandle(handle)

def get_module(handle, module_name = MODULE_NAME):
    #返回 (基址, 大小, 模块文件路径), 找不到就是 (None, None, None)
    modules = (wt.HMODULE * 1024)()
    needed = wt.DWORD()
    if not psapi.EnumProcessModulesEx(handle, modules, ctypes.sizeof(modules),
ctypes.byref(needed), LIST_MODULES_ALL):
        logging.error(f"枚举模块失败! err={ctypes.get_last_error()}")
        return None, None, None
    for i in range(needed.value // ctypes.sizeof(wt.HMODULE)):
        name = ctypes.create_unicode_buffer(260)
        psapi.GetModuleBaseNameW(handle, modules[i], name, 260)
        if name.value.lower() != module_name.lower():
            continue
        info = MODULEINFO()
        psapi.GetModuleInformation(handle, modules[i], ctypes.byref(info), ctypes.sizeof(info))
        path = ctypes.create_unicode_buffer(512)
        psapi.GetModuleFileNameExW(handle, modules[i], path, 512)
        return info.lpBaseOfDll, info.SizeOfImage, path.value
    logging.error(f"找不到模块 {module_name}")
    return None, None, None

def read_mem(handle, address, size):
    buffer = ctypes.create_string_buffer(size)
    read = ctypes.c_size_t()
    if not kernel32.ReadProcessMemory(handle, ctypes.c_void_p(address), buffer, size,
ctypes.byref(read)):
        return None
    return buffer.raw[: read.value]

def read_double(handle, address):
    raw = read_mem(handle, address, 8)
    return None if raw is None or len(raw) < 8 else struct.unpack("<d", raw)[0]

def iter_heap_regions(handle):
    #枚举进程里可读的私有内存(堆), 跳过各模块镜像
    regions = []
    address = 0x10000
    info = MEMORY_BASIC_INFORMATION()
    while address < 0x00007FFFFFFFFFFF:
        if not kernel32.VirtualQueryEx(handle, ctypes.c_void_p(address), ctypes.byref(info),
ctypes.sizeof(info)):
            address += 0x1000
            continue
        size = info.RegionSize or 0x1000
        protect = info.Protect
        if info.State == MEM_COMMIT and info.Type == MEM_PRIVATE and (protect & 0xFF) in (0x02, 0x04, 0x20, 0x40) \
                and not protect & PAGE_GUARD and not protect & PAGE_NOACCESS:
            regions.append((info.BaseAddress or address, size))
        address += size
    return regions

def find_song_candidates(handle, song_name, window_size = 2000, limit = 8, timeout = 5.0):
    #按歌名在堆里找网易云自己的播放列表 JSON, 收集所有可能的歌曲ID
    #优先用 commentThreadId 里的 R_SO_4_<id>(它和 id 在同一个对象里, 不会抓错)
    if not song_name:
        return []
    needle = song_name.encode("utf-8")
    start = time.time()
    scanned = 0
    candidates = {}
    for region_base, region_size in iter_heap_regions(handle):
        if time.time() - start > timeout:
            logging.debug("找歌曲信息超时, 先用手上这些候选")
            break
        offset = 0
        while offset < region_size:
            chunk_size = min(HEAP_CHUNK, region_size - offset)
            raw = read_mem(handle, region_base + offset, chunk_size)
            offset += chunk_size
            if not raw:
                continue
            scanned += len(raw)
            index = raw.find(needle)
            while index >= 0:
                window = raw[max(0, index - window_size) : index]
                durations = DURATION_PATTERN.findall(window)
                duration = int(durations[-1]) if durations else 0
                comments = COMMENT_PATTERN.findall(window)
                if comments:
                    song_id = comments[-1].decode()
                    consistent = True
                else:
                    ids = ID_PATTERN.findall(window)
                    if not ids:
                        index = raw.find(needle, index + 1)
                        continue
                    song_id = ids[-1].decode()
                    consistent = False
                if song_id not in candidates or consistent:
                    candidates[song_id] = {"id": song_id, "duration": duration,
"consistent": consistent}
                index = raw.find(needle, index + 1)
        if len(candidates) >= limit * 3:
            break
    ordered = sorted(candidates.values(), key = lambda item: (not item["consistent"], -item["duration"]))
    logging.debug(f"歌名 {song_name!r}: {len(ordered)} 个候选ID, 扫了 {scanned/1024/1024:.0f}MB, "
f"耗时 {time.time() - start:.2f}s")
    return ordered[:limit]

def parse_sections(handle, base):
    #解析 PE 节表, 返回 ([(节名, RVA, 大小, 属性), ...], 编译时间戳)
    head = read_mem(handle, base, 0x1000)
    if head is None or head[:2] != b"MZ":
        return [], 0
    e_lfanew = struct.unpack_from("<I", head, 0x3C)[0]
    nt = read_mem(handle, base + e_lfanew, 0x1000)
    if nt is None or nt[:4] != b"PE\x00\x00":
        return [], 0
    section_count = struct.unpack_from("<H", nt, 0x06)[0]
    optional_size = struct.unpack_from("<H", nt, 0x14)[0]
    timestamp = struct.unpack_from("<I", nt, 0x08)[0]
    table = 0x18 + optional_size
    sections = []
    for i in range(section_count):
        offset = table + i * 40
        name = nt[offset : offset + 8].rstrip(b"\x00").decode("ascii", "replace")
        virtual_size, virtual_address = struct.unpack_from("<II", nt, offset + 8)
        characteristics = struct.unpack_from("<I", nt, offset + 36)[0]
        sections.append((name, virtual_address, virtual_size, characteristics))
    return sections, timestamp

def module_key(handle, base, module_path):
    #用文件大小/时间 + PE时间戳判断"还是不是同一个客户端版本"
    stat = os.stat(module_path)
    _, timestamp = parse_sections(handle, base)
    return {"file_size": stat.st_size, "file_mtime": int(stat.st_mtime),
"pe_timestamp": timestamp}

def load_cache():
    #缓存里两类东西: modules=按版本记的 RVA; signatures=反查出来的签名(跨版本复用)
    try:
        with open(CACHE_PATH, "r", encoding = "utf-8") as f:
            data = json.load(f)
    except Exception:
        return {"version": CACHE_VERSION, "modules": {}, "signatures": []}
    if "modules" in data or "signatures" in data:
        data.setdefault("modules", {})
        data.setdefault("signatures", [])
        if data.get("version") != CACHE_VERSION:
            save_cache(data)                    #旧版本格式顺手升级掉
        return data
    #最早的格式: {"cloudmusic.dll": {...}}
    modules = {}
    if MODULE_NAME in data:
        modules[MODULE_NAME] = data[MODULE_NAME]
    cache = {"version": CACHE_VERSION, "modules": modules, "signatures": []}
    save_cache(cache)
    logging.info("缓存文件是旧格式, 已升级到 v2")
    return cache

def save_cache(cache):
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok = True)
    cache["version"] = CACHE_VERSION
    with open(CACHE_PATH, "w", encoding = "utf-8") as f:
        json.dump(cache, f, indent = 2, ensure_ascii = False)

def remember_module(key, rva, signature):
    cache = load_cache()
    cache["modules"][MODULE_NAME] = {"key": key, "rva": rva, "signature": signature,
"updated_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    save_cache(cache)

def remember_signature(signature):
    cache = load_cache()
    if signature and signature not in cache["signatures"]:
        cache["signatures"].append(signature)
        save_cache(cache)
        logging.info(f"新签名已记入缓存: {signature}")

def all_signatures():
    #内置的 + 本机反查学到的, 去重
    signatures = list(POSITION_SIGNATURES)
    for signature in load_cache().get("signatures", []):
        if signature not in signatures:
            signatures.append(signature)
    return signatures

def is_sane_position(value):
    #NaN/无穷、比哨兵还小的负数、超过一小时的都算垃圾; -1.0 本身是合法状态
    return value is not None and value == value and NO_POSITION <= value < 3600

def parse_signature(signature):
    #把 "F2 0F 11 3D ?? ?? ?? ??" 拆成 (操作码前缀, 通配字节数)
    prefix = bytearray()
    wildcard = 0
    for part in signature.split():
        if part == "??":
            wildcard += 1
        else:
            prefix.append(int(part, 16))
    return bytes(prefix), wildcard

def aob_scan(handle, base, signature):
    #x64 的 RIP 相对寻址: 目标 = 指令结束地址 + disp32
    #所以扫到操作码前缀后, 读它后面 4 字节当 disp32 就能反推出变量地址
    prefix, wildcard = parse_signature(signature)
    if wildcard != 4:
        logging.error(f"暂不支持这种签名: {signature}")
        return []
    sections, _ = parse_sections(handle, base)
    hits = []
    for name, virtual_address, virtual_size, characteristics in sections:
        if not characteristics & IMAGE_SCN_MEM_EXECUTE:
            continue
        code = read_mem(handle, base + virtual_address, virtual_size)
        if code is None:
            logging.debug(f"节 {name} 读取失败, 跳过")
            continue
        index = code.find(prefix)
        while index >= 0:
            if index + len(prefix) + 4 > len(code):
                break
            disp = struct.unpack_from("<i", code, index + len(prefix))[0]
            target_rva = virtual_address + index + len(prefix) + 4 + disp
            hits.append((name, target_rva))
            index = code.find(prefix, index + 1)
    return hits

def from_bytes(raw, code, size):
    #把原始字节按指定类型转成 array, 走 C 层, 比 struct 逐个解快
    buffer = array.array(code)
    buffer.frombytes(raw[: len(raw) // size * size])
    return buffer

def scan_buffers(raw_a, raw_b, section_rva, interval):
    #在两次快照之间找"Δ 正好等于间隔"的变量; 抽出来方便离线自测
    candidates = []
    for code, size, scale, label in SCAN_TYPES:
        count = min(len(raw_a), len(raw_b)) // size
        values_a = from_bytes(raw_a, code, size)
        values_b = from_bytes(raw_b, code, size)
        for index in range(count):
            value = values_a[index] / scale
            if not (0 <= value < SCAN_MAX_POSITION):
                continue
            delta = (values_b[index] - values_a[index]) / scale
            if abs(delta - interval) <= SCAN_TOLERANCE:
                candidates.append({"rva": section_rva + index * size, "dtype": label,
"value": value, "delta": delta})
    return candidates

def differential_scan(handle, base, interval = SCAN_INTERVAL, stop_event = None):
    #不知道偏移时的兜底: 音乐在播时, 播放位置每秒 +1, 读两遍可写节找 Δ 对得上的变量
    sections, _ = parse_sections(handle, base)
    regions = [(va, vs) for name, va, vs, ch in sections if ch & IMAGE_SCN_MEM_WRITE]
    total = sum(size for _, size in regions)
    if not regions:
        logging.error("找不到可写数据节, 差分扫描无法进行")
        return []
    first = {}
    for va, vsize in regions:
        raw = read_mem(handle, base + va, vsize)
        if raw:
            first[va] = raw
    logging.info(f"差分扫描: 第一次快照 {total/1024/1024:.1f}MB, 等 {interval:.0f} 秒 (需要音乐在播)")
    if stop_event is not None:
        if stop_event.wait(interval):
            return []
    else:
        time.sleep(interval)
    candidates = []
    for va, raw_a in first.items():
        raw_b = read_mem(handle, base + va, len(raw_a))
        if raw_b is None:
            continue
        candidates.extend(scan_buffers(raw_a, raw_b, va, interval))
    logging.info(f"差分扫描完成: 命中 {len(candidates)} 个候选")
    return candidates

def pick_candidate(candidates):
    #优先 float64(实测就是它), 其次 Δ 最接近的
    def score(candidate):
        return (0 if candidate["dtype"] == "float64秒" else 1, abs(candidate["delta"] - SCAN_INTERVAL))
    return sorted(candidates, key = score)[0]

def iter_references(code, section_rva, target_rva):
    #在代码里找所有 RIP 相对引用 target_rva 的指令, 返回 disp32 所在偏移
    seen = set()
    for shape in OPCODE_SHAPES:
        index = code.find(shape)
        while index >= 0:
            modrm_index = index + len(shape)
            if modrm_index + 5 <= len(code) and code[modrm_index] in RIP_MODRM:
                disp_index = modrm_index + 1
                disp = struct.unpack_from("<i", code, disp_index)[0]
                if section_rva + disp_index + 4 + disp == target_rva and disp_index not in seen:
                    seen.add(disp_index)
                    yield disp_index
            index = code.find(shape, index + 1)

def derive_signature(handle, base, target_rva):
    #反查引用指令, 取"操作码前缀 + 通配 disp32"当新签名
    sections, _ = parse_sections(handle, base)
    candidates = []
    for name, virtual_address, virtual_size, characteristics in sections:
        if not characteristics & IMAGE_SCN_MEM_EXECUTE:
            continue
        code = read_mem(handle, base + virtual_address, virtual_size)
        if code is None:
            continue
        for disp_index in iter_references(code, virtual_address, target_rva):
            #从 4 字节前缀开始试, 要在这节里唯一; 不行就加长
            for length in (4, 5, 6, 3):
                start = disp_index - length
                if start < 0:
                    continue
                prefix = code[start:disp_index]
                if code.count(prefix) == 1:
                    signature = " ".join(f"{byte:02X}" for byte in prefix) + " ?? ?? ?? ??"
                    if signature not in candidates:
                        candidates.append(signature)
                    break
    if not candidates:
        logging.warning(f"没能在代码里反查到引用 RVA=0x{target_rva:x} 的指令")
        return None
    for signature in candidates:
        if verify_signature(handle, base, signature, target_rva):
            logging.info(f"反查成功: {signature} (共 {len(candidates)} 条候选, 这条已验证唯一)")
            return signature
    logging.warning(f"反查出的 {len(candidates)} 条候选都没通过唯一性验证")
    return None

def verify_signature(handle, base, signature, target_rva):
    targets = []
    for name, rva in aob_scan(handle, base, signature):
        if rva not in targets:
            targets.append(rva)
    return targets == [target_rva]

def resolve_position(handle, base, module_path, stop_event = None):
    #三级: 缓存 RVA -> 签名(AOB) -> 差分扫描兜底; 返回 (地址, RVA, 来源)
    key = module_key(handle, base, module_path)
    entry = load_cache().get("modules", {}).get(MODULE_NAME)
    if entry and entry.get("key") == key:
        address = base + entry["rva"]
        if is_sane_position(read_double(handle, address)):
            logging.info(f"缓存命中 position: RVA=0x{entry['rva']:x}")
            return address, entry["rva"], "cache"
        logging.warning("缓存里的 RVA 读出来不合理, 换成 AOB 重扫")
    for signature in all_signatures():
        sane = []
        for name, rva in aob_scan(handle, base, signature):
            if is_sane_position(read_double(handle, base + rva)) and rva not in sane:
                sane.append(rva)
        if len(sane) > 1:
            logging.warning(f"签名 [{signature}] 有 {len(sane)} 个候选, 跳过")
            continue
        if not sane:
            continue
        rva = sane[0]
        remember_module(key, rva, signature)
        logging.info(f"AOB 命中 position: {signature} -> RVA=0x{rva:x} (已写缓存)")
        return base + rva, rva, "aob"
    logging.warning("签名全部失效(客户端更新了?), 启动差分扫描兜底")
    candidates = differential_scan(handle, base, stop_event = stop_event)
    if not candidates:
        logging.error("差分扫描没有命中: 确认一下音乐是不是正在播放")
        return None, None, None
    best = pick_candidate(candidates)
    rva = best["rva"]
    logging.info(f"差分扫描命中 position: RVA=0x{rva:x} ({best['dtype']}, "
f"当前 {best['value']:.2f}s, 实测 Δ={best['delta']:.2f})")
    if best["dtype"] != "float64秒":
        logging.warning(f"这个版本的位置像是用 {best['dtype']} 存的, 目前只按 float64 读, 数值可能不对")
    signature = derive_signature(handle, base, rva)
    remember_module(key, rva, signature)
    if signature:
        remember_signature(signature)
    return base + rva, rva, "scan"
