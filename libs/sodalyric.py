"""汽水音乐的歌词: 从渲染进程内存里捞 KRC/LRC 字符串再解析。

汽水把整份歌词放在一个字符串里, 两种格式:
  KRC: [行起始ms,行时长ms]<字偏移ms,字时长ms,标志>字<...>字...
  LRC: [mm:ss.mmm]文字
翻译是**另一个字符串**(translations.cn), 时间戳和原文一一对应。

内存里同时躺着好几首歌的歌词, 所以流程是:
  1. 拿 SMTC 给的歌名, 先在内存里定位曲目 JSON, 读出真实的 id 和时长
  2. 按 id 查磁盘缓存 —— 命中就完全不碰内存
  3. 没命中才扫内存, 用时长精确认领歌词, 再按 id 存盘

(接口那条路走不通: /luna/pc 下没有歌词端点, track_v2 又被原生 metasecml.dll 的
 签名挡着, 复刻签名工程量巨大且跟版本强绑定)
"""

import logging
import os
import re
import time

from . import mem, paths

KRC_LINE = re.compile(r"^\[(\d{1,6}),(\d{1,6})\](.*)$")
KRC_CHAR = re.compile(r"<(\d+),(\d+),(\d+)>([^<]*)")
LRC_LINE = re.compile(r"^\[(\d{1,2}):(\d{2})(?:[.:](\d{1,3}))?\](.*)$")
#在解出来的文本里找歌词行的开头(KRC 或 LRC 都算)
LINE_MARK = re.compile(r"\[(?:\d{1,6},\d{1,6}\]<|\d{1,2}:\d{2}[.:]\d{1,3}\])")
CHUNK = 16 * 1024 * 1024
MAX_CANDIDATES = 200
MAX_STRING = 256 * 1024
BACK_WINDOW = 0          #从命中点开始解析(往前取了会把别的歌的歌词拼进来)


def split_monotonic(lines):
    #原文和翻译在内存里是首尾相连的, 时间戳会比出现倒退 —— 按倒退点切成几段
    segments = []
    current = []
    previous = -1.0
    for line in lines:
        if line["start"] <= previous:
            if current:
                segments.append(current)
            current = []
            previous = -1.0
        current.append(line)
        previous = line["start"]
    if current:
        segments.append(current)
    return segments


def is_plausible(lines):
    #时间戳必须严格递增、跨度合理 —— 挡掉窗口拼接出来的垃圾
    if len(lines) < 4 or len(lines) > 800:
        return False
    previous = -1.0
    for line in lines:
        if line["start"] <= previous:
            return False
        previous = line["start"]
    span = lines[-1]["start"] - lines[0]["start"]
    if span < 10 or span > 3600:
        return False
    gap = span / max(1, len(lines) - 1)
    if gap > 30:
        return False
    for line in lines:
        text = line["text"]
        if not text or len(text) > 120:
            return False
        if any(ord(char) < 32 for char in text):
            return False
    return True


def parse_krc(text):
    lines = []
    for raw in text.split("\n"):
        raw = raw.strip()
        if not raw:
            continue
        match = KRC_LINE.match(raw)
        if not match:
            continue
        start_ms, duration_ms = int(match.group(1)), int(match.group(2))
        content = match.group(3)
        words = KRC_CHAR.findall(content)
        lyric = "".join(word[3] for word in words) if words else content
        lyric = lyric.strip()
        if not lyric:
            continue
        lines.append({"start": start_ms / 1000, "end": (start_ms + duration_ms) / 1000,
"text": lyric})
    return lines


def parse_lrc(text):
    lines = []
    for raw in text.split("\n"):
        raw = raw.strip()
        if not raw:
            continue
        match = LRC_LINE.match(raw)
        if not match:
            continue
        minute, second = int(match.group(1)), int(match.group(2))
        fraction = match.group(3) or "0"
        millisecond = int(fraction.ljust(3, "0")[:3])
        lyric = match.group(4).strip()
        if not lyric:
            continue
        start = minute * 60 + second + millisecond / 1000
        lines.append({"start": start, "end": start + 10.0, "text": lyric})
    for index in range(len(lines) - 1):
        lines[index]["end"] = lines[index + 1]["start"]
    return lines


TITLE_NEEDLE = '"name":"{}"'
#曲目 id 和时长在不同结构里键名不一样(分享链接里是 track_id=, 曲目对象里是 "duration":)
ID_PATTERNS = [re.compile(r'"track_id":"(\d{6,25})"'), re.compile(r"track_id=(\d{6,25})"),
re.compile(r'"id":"(\d{6,25})"')]
DURATION_PATTERNS = [re.compile(r'"duration_ms":(\d{4,9})'), re.compile(r'"duration":(\d{4,9})')]


TRACK_ID_CACHE = "track_ids.json"


def title_variants(title):
    #SMTC 给的歌名可能带后缀(比如 "xxx (Cover)"), 内存里的 JSON 往往是干净歌名
    variants = [title]
    for separator in (" (", " （", " - ", " feat", "【"):
        if separator in title:
            variants.append(title.split(separator)[0].strip())
    return [variant for variant in dict.fromkeys(variants) if variant]


def track_id_cache_path():
    paths.ensure("soda")
    return f"{paths.platform_dir('soda')}/{TRACK_ID_CACHE}"


def load_track_id(title, artist):
    #歌名+艺术家 -> track_id 的磁盘缓存, 命中就不再扫内存
    import json
    path = track_id_cache_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding = "utf-8") as f:
            data = json.load(f)
    except Exception:
        return None
    return data.get(f"{title}|{artist}")


def save_track_id(title, artist, track_id):
    import json
    path = track_id_cache_path()
    data = {}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding = "utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
    data[f"{title}|{artist}"] = track_id
    with open(path, "w", encoding = "utf-8") as f:
        json.dump(data, f, ensure_ascii = False, indent = 1)
    logging.debug(f"记住曲目ID: {title} - {artist} -> {track_id}")


def find_track(handle, title, timeout = 60.0):
    #用歌名(来自 SMTC)当锚点, 在它附近抓曲目 id 和时长 —— 比"猜时长"可靠得多
    #歌名在内存里有好几种落点: 分享信息(share_title + track_id=)、曲目对象("duration":...,"name":...)
    variants = title_variants(title)
    if not variants:
        return None
    needles = [variant.encode("utf-8") for variant in variants]
    start_time = time.time()
    fallback = None
    for base, size in mem.iter_heap_regions(handle):
        if time.time() - start_time > timeout:
            break
        offset = 0
        while offset < size:
            chunk_size = min(CHUNK, size - offset)
            raw = mem.read_mem(handle, base + offset, chunk_size)
            offset += chunk_size
            if not raw:
                continue
            position = -1
            for needle in needles:
                position = raw.find(needle)
                if position >= 0:
                    break
            if position < 0:
                continue
            window = raw[max(0, position - 1200):position + 1200].decode("utf-8", "ignore")
            track_id = None
            for pattern in ID_PATTERNS:
                match = pattern.search(window)
                if match:
                    track_id = match.group(1)
                    break
            if not track_id:
                continue
            duration = 0.0
            for pattern in DURATION_PATTERNS:
                match = pattern.search(window)
                if match:
                    duration = int(match.group(1)) / 1000
                    break
            track = {"id": track_id, "duration": duration, "name": title}
            if duration > 5:
                logging.debug(f"定位到曲目: {title} id={track_id} 时长={duration:.1f}s "
f"(耗时 {time.time() - start_time:.2f}s)")
                return track
            if fallback is None:
                fallback = track
    if fallback:
        logging.debug(f"定位到曲目(无时长): {title} id={fallback['id']}")
    else:
        logging.debug(f"没定位到曲目 {title!r}")
    return fallback


def load_cached(song_id):
    #按 id 读缓存, 命中就不用碰内存了
    normal_path = paths.lyric_path("soda", song_id, "normal")
    if not os.path.exists(normal_path):
        return None
    lines = read_lines(normal_path)
    trans_lines = read_lines(paths.lyric_path("soda", song_id, "trans"))
    if not lines:
        return None
    logging.debug(f"歌词命中缓存: {song_id} ({len(lines)} 行, 翻译 {len(trans_lines)} 行)")
    return lines, trans_lines


def read_lines(path):
    lines = []
    if not os.path.exists(path):
        return lines
    with open(path, "r", encoding = "utf-8") as f:
        for raw in f:
            parts = raw.rstrip("\n").split("\t")
            if len(parts) < 3:
                continue
            lines.append({"start": float(parts[0]), "end": float(parts[1]),
"text": "\t".join(parts[2:])})
    return lines


def save_cached(song_id, lines, trans_lines):
    paths.ensure("soda")
    write_lines(paths.lyric_path("soda", song_id, "normal"), lines)
    write_lines(paths.lyric_path("soda", song_id, "trans"), trans_lines)


def write_lines(path, lines):
    with open(path, "w", encoding = "utf-8") as f:
        for line in lines or []:
            f.write(f"{line['start']:.3f}\t{line['end']:.3f}\t{line['text']}\n")


def parse_any(text):
    #KRC 和 LRC 都试, 谁解出来的行多用谁
    krc = parse_krc(text)
    lrc = parse_lrc(text)
    if len(krc) >= len(lrc):
        return krc, "KRC"
    return lrc, "LRC"


def collect(handle, duration = 0.0, timeout = 25.0, exact = False):
    #把候选歌词都捞出来; 一旦有候选的末尾时间和真实时长吻合, 立刻收工
    #注意: 汽水的歌词既有 UTF-8 也有 UTF-16LE(JS 双字节字符串), 两种都得试
    start_time = time.time()
    tolerance = 2.0 if exact else max(5.0, duration * 0.05)
    by_tail = {}
    for base, size in mem.iter_heap_regions(handle):
        if time.time() - start_time > timeout:
            break
        offset = 0
        while offset < size:
            chunk_size = min(CHUNK, size - offset)
            raw = mem.read_mem(handle, base + offset, chunk_size)
            offset += chunk_size
            if not raw:
                continue
            for encoding in ("utf-8", "utf-16le"):
                text = raw.decode(encoding, "ignore")
                if not text:
                    continue
                for match in LINE_MARK.finditer(text):
                    window = text[max(0, match.start() - BACK_WINDOW): match.start() + MAX_STRING]
                    #KRC(原文)和 LRC(翻译)都要试 —— 同一段里可能两种都有
                    for parser, kind in ((parse_krc, "KRC"), (parse_lrc, "LRC")):
                        for lines in split_monotonic(parser(window)):
                            if not is_plausible(lines):
                                continue
                            #同一份歌词会被每个行首各匹配一次, 尾巴一样的就是同一份, 只留最长的
                            tail = (round(lines[-1]["start"], 2), lines[-1]["text"])
                            existing = by_tail.get(tail)
                            if existing is not None:
                                if len(lines) > len(existing["lines"]):
                                    existing["lines"] = lines
                                    existing["kind"] = kind
                                continue
                            by_tail[tail] = {"kind": kind, "lines": lines, "encoding": encoding,
"address": base + offset - len(raw) + match.start()}
                            if duration > 5 and abs(lines[-1]["end"] - duration) <= tolerance:
                                logging.debug(f"歌词与时长吻合: {kind}/{encoding} {len(lines)} 行, "
f"末尾 {lines[-1]['end']:.1f}s vs {duration:.1f}s "
f"(扫了 {time.time() - start_time:.2f}s)")
                                return list(by_tail.values())
                            if len(by_tail) >= MAX_CANDIDATES:
                                break
                        if len(by_tail) >= MAX_CANDIDATES:
                            break
                    if len(by_tail) >= MAX_CANDIDATES:
                        break
                if len(by_tail) >= MAX_CANDIDATES:
                    break
            if len(by_tail) >= MAX_CANDIDATES:
                break
        if len(by_tail) >= MAX_CANDIDATES:
            break
    candidates = list(by_tail.values())
    logging.debug(f"内存里找到 {len(candidates)} 份歌词候选, 耗时 {time.time() - start_time:.2f}s")
    return candidates


def overlap_ratio(lines_a, lines_b, tolerance = 0.08):
    #两份歌词有多少行的起始时间能对上(窗口可能把开头截掉几行, 所以不能要求完全一致)
    if len(lines_b) < 4:
        return 0.0
    starts_b = [line["start"] for line in lines_b]
    hit = 0
    for line in lines_a:
        for start in starts_b:
            if abs(line["start"] - start) <= tolerance:
                hit += 1
                break
    return hit / len(lines_a)


def same_timing(lines_a, lines_b, tolerance = 0.08):
    #翻译和原文的时间戳基本一一对应
    if len(lines_a) != len(lines_b) or len(lines_a) < 4:
        return False
    return all(abs(a["start"] - b["start"]) <= tolerance for a, b in zip(lines_a, lines_b))


def pick_original(candidates, duration, exact = False):
    #总时长最接近 SMTC 报的时长的那份, 才是当前这首; 返回 (候选, 是否吻合)
    if not candidates:
        return None, False
    if duration and duration > 5:
        #时长最接近的; 差得不多时优先 KRC(汽水的原文是逐字 KRC, 翻译才是普通 LRC)
        scored = sorted(candidates, key = lambda item: (abs(item["lines"][-1]["end"] - duration),
0 if item["kind"] == "KRC" else 1))
        best = scored[0]
        error = abs(best["lines"][-1]["end"] - duration)
        logging.debug(f"按时长({duration:.1f}s)挑歌词: 误差 {error:.1f}s, "
f"{best['kind']} {len(best['lines'])} 行")
        limit = 2.0 if exact else max(10.0, duration * 0.15)
        if error <= limit:
            return best, True
        logging.debug(f"没有跟时长吻合的歌词(容差 {limit:.1f}s), 退回最长的候选")
    return max(candidates, key = lambda item: len(item["lines"])), False


def normalize_text(text):
    return "".join(text.split())


def is_duplicate(candidate, original, threshold = 0.8):
    #同一份歌词从不同行首解出来会得到错位副本: 它的每一行都能在原文里找到
    pairs = {(round(line["start"], 2), normalize_text(line["text"])) for line in original["lines"]}
    lines = candidate["lines"]
    same = sum(1 for line in lines if (round(line["start"], 2), normalize_text(line["text"])) in pairs)
    return same >= len(lines) * threshold


def differs_from(original, candidate, tolerance = 0.08, threshold = 0.7):
    #对齐之后文字必须大部分不一样, 否则就是原文自己的副本/另一种写法
    aligned = 0
    different = 0
    for line in original["lines"]:
        for other in candidate["lines"]:
            if abs(line["start"] - other["start"]) <= tolerance:
                aligned += 1
                if normalize_text(line["text"]) != normalize_text(other["text"]):
                    different += 1
                break
    if not aligned:
        return False
    return different / aligned >= threshold


def extract(handle, duration = 0.0, timeout = 20.0, exact = False):
    #返回 (原文行, 翻译行, 是否与时长吻合)
    candidates = collect(handle, duration, timeout, exact)
    original, matched = pick_original(candidates, duration, exact)
    if original is None:
        return [], [], False
    #翻译: 时间戳能对上、文字又确实不同的那一份
    best = None
    best_ratio = 0.0
    for candidate in candidates:
        if candidate is original or is_duplicate(candidate, original):
            continue
        if not differs_from(original, candidate):
            continue
        ratio = overlap_ratio(original["lines"], candidate["lines"])
        if ratio > best_ratio:
            best = candidate
            best_ratio = ratio
    if best is not None and best_ratio >= 0.6:
        logging.debug(f"配上翻译: {len(best['lines'])} 行, 重合度 {best_ratio:.0%} ({best['encoding']})")
        return original["lines"], best["lines"], matched
    if best is not None:
        logging.debug(f"翻译重合度只有 {best_ratio:.0%}, 先不用")
    return original["lines"], [], matched


def find_current(lines, position, cursor = None):
    if not lines or position is None:
        return None
    if cursor is None:
        return _scan(lines, position)
    return _scan(lines, position, cursor)


def _scan(lines, position, cursor = None):
    index = cursor[0] if cursor else 0
    if index >= len(lines):
        index = 0
    while index < len(lines) - 1 and lines[index + 1]["start"] <= position:
        index += 1
    while index > 0 and lines[index]["start"] > position:
        index -= 1
    if cursor is not None:
        cursor[0] = index
    return lines[index]["text"]


def line_index(lines, position, cursor = None):
    #给翻译对行用: 先定位原文的序号, 翻译按同一个序号取
    if not lines or position is None:
        return None
    index = cursor[0] if cursor else 0
    if index >= len(lines):
        index = 0
    while index < len(lines) - 1 and lines[index + 1]["start"] <= position:
        index += 1
    while index > 0 and lines[index]["start"] > position:
        index -= 1
    if cursor is not None:
        cursor[0] = index
    return index
