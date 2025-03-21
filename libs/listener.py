import os
import time
import asyncio
import requests
import logging
from .logger import setup_colored_log
setup_colored_log()

from multiprocessing import Process

from PIL import Image

from .process import get_window_titles_by_pid
from .cloudmusic import get_player_time, get_offset_address, get_mem_info
from .lyric import find_current_lyric, parse_lrc

def listener_task(stop_event, listener_queue, base_addr, position_addr,
end_addr, song_id_offset):
    last_played_song = None
    last_song_id = None
    last_song_trans_lyric = None
    last_song_normal_lyric = None
    while not stop_event.is_set():
        #从窗口标题获取歌名以及艺术家
        #FIXME: 后续需观察酷狗音乐是否也为相同格式, 若不同需要重写
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
        song_id = get_mem_info(song_id_addr, "OrpheusBrowserHost", 20, "utf-8").split("_")[0]
        song_changed = (song_name != last_played_song)
        #检测切歌
        if song_changed:
            if not os.path.exists("./cache"):
                os.makedirs("./cache")
            if not os.path.exists("./data"):
                os.makedirs("./data")
            if not os.path.exists("./data/cover.jpg"):
                img = Image.new('RGB', (500, 500), (255, 255, 255))
                with open("./data/cover.jpg", "wb") as f:
                    img.save(f)
            if not os.path.exists("./data/lyric.txt"):
                with open("./data/lyric.txt", "w") as f:
                    f.close()
            #强制刷新歌曲ID以保证歌曲ID始终是内存中最新的ID
            while last_song_id == song_id:
                song_id = get_mem_info(song_id_addr, "OrpheusBrowserHost", 20, "utf-8").split("_")[0]
            download_stat =  start_download_cover(song_id)
            #将封面写入data下的cover.jpg
            if download_stat == "cached_cover" or download_stat == "dl_ok":
                cover_stat = True
                img = Image.open(f"./cache/{song_id}.jpg").convert("RGB")
                with open("./data/cover.jpg", "wb") as f:
                    img.save(f)
            else:
                cover_stat = False
                img = Image.new('RGB', (500, 500), (255, 255, 255))
                with open("./data/cover.jpg", "wb") as f:
                    img.save(f)
            #获取歌曲翻译歌词并存储信息
            normal_lyric, trans_lyric = get_lyric(song_id)
            if normal_lyric == None:
                last_song_normal_lyric = None
            else:
                formatted_normal_lyric = parse_lrc(normal_lyric)
                last_song_normal_lyric = formatted_normal_lyric
            if trans_lyric == None:
                last_song_trans_lyric = None
            else:
                formatted_trans_lrc = parse_lrc(trans_lyric)
                last_song_trans_lyric = formatted_trans_lrc
        #读取歌词和翻译并使用二分法读取最近的歌词
        if last_song_normal_lyric == None:
            song_normal_lyric = None
        else:
            song_normal_lyric = find_current_lyric(last_song_normal_lyric, play_time_list[0])
        if last_song_trans_lyric == None:
            song_trans_lyric = None
        else:
            song_trans_lyric = find_current_lyric(last_song_trans_lyric, play_time_list[0])
        #将歌词写入data下的lyric.txt中
        with open("./data/lyric.txt", "w", encoding = "UTF-8") as f:
            f.write(f"{song_normal_lyric}\n{song_trans_lyric}")
        listener_queue.put({"status":song_changed, "song_name": song_name, "song_artist": song_artist,
"play_progress":[format_time(play_time_list[0]), format_time(play_time_list[1])],
"original_progress": [play_time_list[0], play_time_list[1]],
"lyric": song_normal_lyric, "trans_lyric": song_trans_lyric, "cover_ready": cover_stat,
"song_id": song_id})
        #更新最后播放的歌曲名信息
        last_played_song = song_name
        last_song_id = song_id
        time.sleep(0.5)

def get_lyric(song_id):
    try:
        lyric_info = requests.get(f"https://music.163.com/api/song/lyric?os=pc&id={song_id}&lv=-1&tv=-1")
        lyric_data_dict = lyric_info.json()
        normal_lyric = lyric_data_dict["lrc"]["lyric"]
        trans_lyric = lyric_data_dict["tlyric"]["lyric"]
    except requests.exceptions.RequestException:
        logging.warning("无网络, 无法获得翻译!")
        return "", ""
    except KeyError:
        logging.debug("该歌曲无翻译或暂未翻译!")
        return normal_lyric, ""
    return normal_lyric, trans_lyric

async def download_task(song_id):
    song_info = requests.get(f"https://music.163.com/api/song/detail?ids=[{song_id}]")
    song_info_dict = song_info.json()
    song_cover_url = song_info_dict["songs"][0]["album"]["picUrl"] + "?param=500y500"
    img_data = requests.get(song_cover_url).content
    with open(f"./cache/{song_id}.jpg", "wb") as f:
        f.write(img_data)

def start_download_cover(song_id):
    file_path = f"./cache/{song_id}.jpg"
    if os.path.exists(file_path):
        logging.debug(f"{song_id}封面已缓存, 无需下载")
        return "cached_cover"
    else:
        logging.debug(f"开始下载{song_id}封面")
        try:
            asyncio.run(download_task(song_id))
        except:
            logging.error(f"下载{song_id}封面失败!")
            return "dl_error"
        logging.debug(f"下载{song_id}封面成功!")
        return "dl_ok"

def format_time(time):
    return f"{time//60%60:02d}:{time%60:02d}"

def start_listener(stop_event, listener_queue, base_addr, position_addr,
end_addr, song_id_offset):
    p = Process(target = listener_task, args = (stop_event, listener_queue, base_addr, position_addr,
end_addr, song_id_offset))
    p.start()
    return p