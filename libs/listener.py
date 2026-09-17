import time
import os
import logging
import asyncio

import requests
from PIL import Image

from .process import get_window_titles_by_pid
from .cloudmusic import get_player_time, get_offset_address, get_mem_info
from .lyric import find_current_lyric, parse_lrc

def format_time(time):
    return f"{time//60%60:02d}:{time%60:02d}"

def cloudmusic_listener_task(stop_event, listener_queue, base_addr, position_addr,
end_addr, song_id_offset):
    last_played_song = None
    last_song_id = None
    last_song_trans_lyric = None
    last_song_trans_lyric_time = None
    last_song_normal_lyric = None
    last_song_normal_lyric_time = None
    while not stop_event.is_set():
        #从窗口标题获取歌名以及艺术家
        try:
            temp_window_title = get_window_titles_by_pid(base_addr[0])
            for title in temp_window_title:
                if title not in ["桌面歌词", "桌面歌词解锁", "迷你播放器", "GDI+ Window (cloudmusic.exe)", "MSCTFIME UI", "Default IME"]:
                    temp_window_title = title
                    break
            song_name, song_artist = temp_window_title.split(" - ", 1)
        except:
            song_name = "获取歌名失败"
            song_artist = "获取艺术家失败"
        #获取播放器播放时间信息
        play_time_list = get_player_time(base_addr[1] + position_addr, base_addr[1] + end_addr)
        #获取歌曲ID信息
        song_id_addr = get_offset_address(base_addr[1], song_id_offset, "OrpheusBrowserHost")
        song_id = get_mem_info(song_id_addr, "OrpheusBrowserHost", 17, "utf-8").split("_")[0]
        song_changed = (song_name != last_played_song)
        #检测切歌
        if song_changed:
            #新建文件
            if not os.path.exists("./data/pic"):
                os.makedirs("./data/pic")
            if not os.path.exists("./data/lyric"):
                os.makedirs("./data/lyric")
            #让用户去调用Tuna的缩略图获取, 此处代码删除
            if not os.path.exists("./data/lyric.txt"):
                with open("./data/lyric.txt", "w") as f:
                    f.close()
            if not os.path.exists("./data/lyric.txt"):
                with open("./data/lyric.txt", "w") as f:
                    f.close()
            #强制刷新歌曲ID以保证歌曲ID始终是内存中最新的ID
            while last_song_id == song_id:
                song_id = get_mem_info(song_id_addr, "OrpheusBrowserHost", 17, "utf-8").split("_")[0]
            #下载封面并检测状态
            download_stat =  start_download_cover(song_id)
            if download_stat == "cached_cover" or download_stat == "download_ok":
                cover_stat = True
                logging.debug(f"{song_id}封面下载完毕或已缓存")
            else:
                cover_stat = False
                logging.error(f"下载{song_id}封面失败!")
            #获取歌曲翻译歌词并存储信息
            normal_lyric, trans_lyric = get_lyric(song_id)
            if normal_lyric == None:
                last_song_normal_lyric = None
                last_song_normal_lyric_time = None
            else:
                formatted_normal_lyric, cache_time = parse_lrc(normal_lyric)
                last_song_normal_lyric = formatted_normal_lyric
                last_song_normal_lyric_time = cache_time
                
            if trans_lyric == None:
                last_song_trans_lyric = None
                last_song_trans_lyric_time = None
            else:
                formatted_trans_lrc, cache_time = parse_lrc(trans_lyric)
                last_song_trans_lyric = formatted_trans_lrc
                last_song_trans_lyric_time = cache_time
        #读取歌词和翻译
        if last_song_normal_lyric == None:
            song_normal_lyric = None
        else:
            if song_changed:
                song_normal_lyric = find_current_lyric(last_song_normal_lyric, 
last_song_normal_lyric_time, play_time_list[0], cursor = [0])
            else:
                song_normal_lyric = find_current_lyric(last_song_normal_lyric, 
last_song_normal_lyric_time, play_time_list[0])
        if last_song_trans_lyric == None:
            song_trans_lyric = None
        else:
            if song_changed:
                song_trans_lyric = find_current_lyric(last_song_trans_lyric,
last_song_trans_lyric_time, play_time_list[0], cursor = [0])
            else:
                song_trans_lyric = find_current_lyric(last_song_trans_lyric,
    last_song_trans_lyric_time, play_time_list[0])
        #将歌词写入data下的lyric.txt中
        with open("./data/lyric.txt", "w", encoding = "UTF-8") as f:
            f.writelines(f"正在播放:{song_name}-{song_artist}  {format_time(play_time_list[0])}:{format_time(play_time_list[1])}\n{song_normal_lyric}\n{song_trans_lyric}")
        last_played_song = song_name
        last_song_id = song_id
        listener_queue.put({"status":song_changed, "song_name": song_name, "song_artist": song_artist,
"play_progress":[format_time(play_time_list[0]), format_time(play_time_list[1])],
"cover_ready": cover_stat, "song_id": song_id,
"lyric": song_normal_lyric, "trans_lyric": song_trans_lyric})
        time.sleep(0.25)

def get_lyric(song_id):
    #如果存在缓存文件则读取缓存文件
    if os.path.exists(f"./data/lyric/{song_id}_normal.txt") and os.path.exists(f"./data/lyric/{song_id}_trans.txt"):
        normal_lyric = ""
        trans_lyric = ""
        with open(f"./data/lyric/{song_id}_normal.txt", "r", encoding = "UTF-16le") as f:
            normal_lyric = f.read()
        with open(f"./data/lyric/{song_id}_trans.txt", "r", encoding = "UTF-16le") as f:
            trans_lyric = f.read()
        logging.debug("读取本地缓存歌词成功! 双语")
        return normal_lyric, trans_lyric
    elif os.path.exists(f"./data/lyric/{song_id}_normal.txt"):
        normal_lyric = ""
        with open(f"./data/lyric/{song_id}_normal.txt", "r", encoding = "UTF-16le") as f:
            normal_lyric = f.read()
        logging.debug("读取本地缓存歌词成功! 原语言")
        return normal_lyric, None
    else:
        try:
            logging.debug(f"尝试下载{song_id}歌词!")
            lyric_info = requests.get(f"https://music.163.com/api/song/lyric?os=pc&id={song_id}&lv=-1&tv=-1")
            lyric_data_dict = lyric_info.json()
            normal_lyric = lyric_data_dict["lrc"]["lyric"]
            trans_lyric = lyric_data_dict["tlyric"]["lyric"]
        except requests.exceptions.RequestException:
            logging.warning("无网络, 无法获得歌词!")
            return "", ""
        except KeyError:
            logging.debug("该歌曲无翻译/歌词或暂未翻译/上传!")
            with open(f"./data/lyric/{song_id}_normal.txt", "w", encoding = "UTF-16le") as f:
                f.writelines(normal_lyric)
            logging.debug("下载本地缓存歌词成功! 原语言")
            return normal_lyric, ""
        with open(f"./data/lyric/{song_id}_normal.txt", "w", encoding = "UTF-16le") as f:
            f.writelines(normal_lyric)
        with open(f"./data/lyric/{song_id}_trans.txt", "w", encoding = "UTF-16le") as f:
            f.writelines(trans_lyric)
        logging.debug("下载本地缓存歌词成功! 双语")
        return normal_lyric, trans_lyric

async def download_cover_cloudmusic(song_id):
    song_info = requests.get(f"https://music.163.com/api/song/detail?ids=[{song_id}]")
    song_info_dict = song_info.json()
    song_cover_url = song_info_dict["songs"][0]["album"]["picUrl"] + "?param=500y500"
    img_data = requests.get(song_cover_url).content
    with open(f"./data/pic/{song_id}.jpg", "wb") as f:
        f.write(img_data)

def start_download_cover(song_id):
    if os.path.exists(f"./data/pic/{song_id}.jpg"):
        return "cached_cover"
    else:
        try:
            asyncio.run(download_cover_cloudmusic(song_id))
        except:
            return "download_error"
        return "download_ok"