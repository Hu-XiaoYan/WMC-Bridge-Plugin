import asyncio
import logging
import os

import requests

LYRIC_URL = "https://music.163.com/api/song/lyric?os=pc&id={}&lv=-1&tv=-1"
DETAIL_URL = "https://music.163.com/api/song/detail?ids=[{}]"
COVER_DIR = "./data/pic"
LYRIC_DIR = "./data/lyric"

def get_lyric(song_id):
    #先读本地缓存, 没有再走接口; 返回 (原歌词, 翻译歌词), 都没有就是 (None, None)
    normal_path = f"{LYRIC_DIR}/{song_id}_normal.txt"
    trans_path = f"{LYRIC_DIR}/{song_id}_trans.txt"
    if os.path.exists(normal_path):
        with open(normal_path, "r", encoding = "utf-8") as f:
            normal_lyric = f.read()
        trans_lyric = None
        if os.path.exists(trans_path):
            with open(trans_path, "r", encoding = "utf-8") as f:
                trans_lyric = f.read()
        logging.debug(f"读取本地缓存歌词成功! {song_id}")
        return normal_lyric, trans_lyric
    try:
        logging.debug(f"尝试下载 {song_id} 的歌词!")
        lyric_info = requests.get(LYRIC_URL.format(song_id), timeout = 5)
        lyric_data_dict = lyric_info.json()
        normal_lyric = lyric_data_dict["lrc"]["lyric"]
        trans_lyric = lyric_data_dict["tlyric"]["lyric"]
    except requests.exceptions.RequestException:
        logging.warning("无网络, 无法获得歌词!")
        return None, None
    except (KeyError, ValueError):
        logging.debug(f"{song_id} 无歌词/翻译或接口返回异常")
        return None, None
    os.makedirs(LYRIC_DIR, exist_ok = True)
    with open(normal_path, "w", encoding = "utf-8") as f:
        f.writelines(normal_lyric)
    with open(trans_path, "w", encoding = "utf-8") as f:
        f.writelines(trans_lyric)
    logging.debug(f"下载并缓存歌词成功! {song_id}")
    return normal_lyric, trans_lyric

def get_song_detail(song_id):
    #拿歌曲详情: 用来验证ID对不对(名字/艺术家), 顺便取封面地址和准确时长
    try:
        response = requests.get(DETAIL_URL.format(song_id), timeout = 5)
        songs = response.json().get("songs") or []
    except Exception as err:
        logging.debug(f"获取 {song_id} 详情失败: {err}")
        return None
    if not songs:
        return None
    song = songs[0]
    return {"name": song.get("name", ""), "duration": song.get("duration", 0),
"artists": [artist.get("name", "") for artist in song.get("artists", [])],
"cover_url": (song.get("album") or {}).get("picUrl", "")}

async def download_cover_cloudmusic(song_id, cover_url):
    img_data = requests.get(f"{cover_url}?param=500y500", timeout = 10).content
    with open(f"{COVER_DIR}/{song_id}.jpg", "wb") as f:
        f.write(img_data)

def start_download_cover(song_id, cover_url):
    #返回 True/False, 表示界面上能不能拿到封面
    if os.path.exists(f"{COVER_DIR}/{song_id}.jpg"):
        logging.debug(f"{song_id} 封面已缓存")
        return True
    if not cover_url:
        logging.error(f"{song_id} 没有封面地址")
        return False
    os.makedirs(COVER_DIR, exist_ok = True)
    try:
        asyncio.run(download_cover_cloudmusic(song_id, cover_url))
    except Exception as err:
        logging.error(f"下载 {song_id} 封面失败! {err}")
        return False
    logging.debug(f"{song_id} 封面下载完毕")
    return True
