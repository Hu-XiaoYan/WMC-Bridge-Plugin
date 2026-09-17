import re

def parse_time(time_str):
    m, s = map(float, time_str.split(':'))
    return int(m) * 60 + s

def parse_lrc(lrc_text):
    by_pattern = re.compile(r'^\[by:.*\]$', re.IGNORECASE)
    line_pattern = re.compile(r'^\[(\d+:\d+\.\d+)\](.*)$')
    lyrics = []
    times = []
    for line in lrc_text.strip().split('\n'):
        line = line.strip()
        if not line or by_pattern.match(line):
            continue
        match = line_pattern.match(line)
        if match:
            time_str, text = match.groups()
            try:
                time = parse_time(time_str)
                lyrics.append((time, text))
                times.append(time)
            except ValueError:
                continue
    return lyrics, times

def find_current_lyric(lyrics, times, current_time, cursor = None):
    if cursor is None:
        cursor = [0]
    if not lyrics:
        return ""
    while cursor[0] < len(lyrics) - 1 and times[cursor[0] + 1] <= current_time:
        cursor[0] += 1
    while cursor[0] > 0 and times[cursor[0]] > current_time:
        cursor[0] -= 1
    return lyrics[cursor[0]][1] if cursor[0] >= 0 else ""