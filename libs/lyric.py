import re
from bisect import bisect_right

def parse_time(time_str):
    parts = time_str.split(':')
    m, s = parts
    return int(m) * 60 + float(s)

def parse_lrc(lrc_text):
    by_pattern = re.compile(r'^\[by:.*\]$', re.IGNORECASE)
    line_pattern = re.compile(r'^\[(\d+:\d+\.\d+)\](.*)$')
    lyrics = []
    lines = lrc_text.strip().split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if by_pattern.match(line):
            continue
        match = line_pattern.match(line)
        if not match:
            continue
        time_str, text = match.groups()
        try:
            time = parse_time(time_str)
        except ValueError:
            continue
        lyrics.append((time, text.strip()))
    lyrics.sort(key=lambda x: x[0])
    return lyrics

def find_current_lyric(lyrics, current_time):
    if not lyrics:
        return ""
    times = [t for t, _ in lyrics]
    index = bisect_right(times, current_time) - 1
    return lyrics[index][1] if index >= 0 else ""