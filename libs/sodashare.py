"""汽水音乐的歌词: 走它公开的分享页, 免签名。

分享页把整首歌的 KRC 内嵌在 _ROUTER_DATA 里:
  loaderData.track_page.audioWithLyricsOption.lyrics.sentences
  [{startMs, endMs, text, words:[{text, startMs, endMs}], type}, ...]

这条路比挖内存稳得多(公开页面、不用签名、不受版本影响), 也是"只做接口"该有的样子;
内存只用来拿一个 track_id。
"""

import json
import logging
import os
import re

import requests

from . import paths

SHARE_URL = "https://music.douyin.com/qishui/share/track?track_id={}"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
"(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
"Accept-Language": "zh-CN,zh;q=0.9"}
ROUTER_DATA = re.compile(r"_ROUTER_DATA\s*=\s*(\{.*?\})\s*</script>", re.DOTALL)
PLATFORM = "soda"


def fetch(track_id, timeout = 15):
    #抓分享页并解析出 track_page; 失败返回 None
    try:
        response = requests.get(SHARE_URL.format(track_id), headers = HEADERS, timeout = timeout)
    except Exception as err:
        logging.debug(f"抓分享页失败: {err}")
        return None
    match = ROUTER_DATA.search(response.text)
    if not match:
        logging.debug(f"分享页里没有 _ROUTER_DATA (track_id={track_id})")
        return None
    try:
        data, _ = json.JSONDecoder().raw_decode(match.group(1))
    except Exception as err:
        logging.debug(f"解析 _ROUTER_DATA 失败: {err}")
        return None
    return (data.get("loaderData") or {}).get("track_page")


def parse_sentences(sentences):
    #转成我们内部统一的行结构 {start, end, text}
    lines = []
    for sentence in sentences or []:
        text = (sentence.get("text") or "").strip()
        if not text:
            continue
        start = (sentence.get("startMs") or 0) / 1000
        end = (sentence.get("endMs") or 0) / 1000
        if end <= start:
            end = start + 5.0
        lines.append({"start": start, "end": end, "text": text})
    for index in range(len(lines) - 1):
        if lines[index]["end"] > lines[index + 1]["start"]:
            lines[index]["end"] = lines[index + 1]["start"]
    return lines


def get_lyrics(track_id):
    #带缓存: 命中就直接读盘(哪怕是"这首歌没歌词"的空结果, 也存下来避免反复请求)
    cached = read_cache(track_id)
    if cached is not None:
        logging.debug(f"歌词命中分享页缓存: {track_id} ({len(cached)} 行)")
        return cached
    page = fetch(track_id)
    if page is None:
        return []
    option = page.get("audioWithLyricsOption") or {}
    lyrics = option.get("lyrics") or {}
    lines = parse_sentences(lyrics.get("sentences"))
    if not lines:
        logging.debug(f"分享页没给出歌词 (track_id={track_id})")
        write_cache(track_id, [])
        return []
    logging.debug(f"分享页取到歌词: {track_id} {len(lines)} 行, "
f"{option.get('trackName')!r} - {option.get('artistName')!r}, "
f"时长 {(option.get('duration') or 0) / 1000:.1f}s")
    write_cache(track_id, lines)
    return lines


def read_cache(track_id):
    #没有缓存文件返回 None, 有(哪怕是空的)返回行列表
    path = paths.lyric_path(PLATFORM, track_id, "share")
    if not os.path.exists(path):
        return None
    lines = []
    with open(path, "r", encoding = "utf-8") as f:
        for raw in f:
            parts = raw.rstrip("\n").split("\t")
            if len(parts) < 3:
                continue
            lines.append({"start": float(parts[0]), "end": float(parts[1]),
"text": "\t".join(parts[2:])})
    return lines


def write_cache(track_id, lines):
    paths.ensure(PLATFORM)
    with open(paths.lyric_path(PLATFORM, track_id, "share"), "w", encoding = "utf-8") as f:
        for line in lines:
            f.write(f"{line['start']:.3f}\t{line['end']:.3f}\t{line['text']}\n")
