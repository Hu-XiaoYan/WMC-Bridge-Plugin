"""按平台分开的落盘路径。不同软件的歌曲ID体系不一样, 混在一起会撞车。"""

import hashlib
import os

BASE = "./data"


def platform_dir(platform):
    return f"{BASE}/{platform}"


def ensure(platform):
    for sub in ("pic", "lyric"):
        os.makedirs(f"{platform_dir(platform)}/{sub}", exist_ok = True)


def cover_path(platform, key, ext = "jpg"):
    return f"{platform_dir(platform)}/pic/{key}.{ext}"


def lyric_path(platform, key, kind = "normal"):
    return f"{platform_dir(platform)}/lyric/{key}_{kind}.txt"


def output_path(platform):
    return f"{platform_dir(platform)}/lyric.txt"


def song_key(title, artist):
    #汽水这类拿不到数字ID的, 用歌名+艺术家做键
    digest = hashlib.md5(f"{title}|{artist}".encode("utf-8")).hexdigest()[:16]
    return digest
