import os
import logging
from io import BytesIO
from libs.logger import setup_colored_log
setup_colored_log()
import multiprocessing
from multiprocessing import freeze_support, Queue, Event

import tomli
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from PIL import Image, ImageTk
#使用的第三方模块有:
#tomli, ttkbootstrap, win32api, requests, colorlog, pillow
#win32api, winsdk

#初始化SMTC
from datetime import timedelta
import winsdk.windows.media
import winsdk.windows.media.playback
import winsdk.windows.storage.streams
player = winsdk.windows.media.playback.MediaPlayer()
timeline = winsdk.windows.media.SystemMediaTransportControlsTimelineProperties()
smtc = player.system_media_transport_controls
updater = smtc.display_updater
#FIXME: 有没有大佬知道怎么异步刷新SMTC缩略图啊啊啊, 真的看不懂windows api

from libs.watchdog import start_watchdog
from libs.listener import start_listener

class ReadConfig():
    _instance = None
    _data = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._data = cls.load_config()

        return cls._instance
    
    @classmethod
    def load_config(cls):
        if not os.path.exists("./config.toml"):
            with open("./config.toml", "w") as f:
                f.close()
            logging.warning("找不到配置文件! 已在当前目录下新建配置文件, 请前往Github复制相关配置!")
            exit()
        try:
            with open("./config.toml", "rb") as f:
                logging.info("读取配置完成!")
                return tomli.load(f)
        except:
            logging.error("无法读取配置文件! 请确保你复制的配置内容符合Toml配置文件格式!")
            return None
        
    def get_config(self, key):
        if self._data == None:
            logging.error("无法读取配置文件! 请确保你复制的配置内容符合Toml配置文件格式!")
            return None
        if self._data.get(key) == None:
            logging.error("无法读取键值对! 请确认Toml配置文件!")
            return None
        else:
            logging.info(f"读取成功! 键: {key} --> 值: {self._data.get(key)}")
            return self._data.get(key)       
config = ReadConfig()
player_platform_addr_tran = {"网易云音乐": ["cloudmusic_play_time_offset", "cloudmusic_play_end_time_offset",
"cloudmusic_song_id_offset"]}

def open_smtc():
    player.command_manager.is_enabled = False
    smtc = player.system_media_transport_controls
    smtc.is_enabled = True
    smtc.is_play_enabled = True
    smtc.is_pause_enabled = True
    smtc.is_next_enabled = True
    smtc.is_previous_enabled = True
    smtc.playback_status = 3
    smtc.is_enabled = True
    logging.debug("SMTC 顺利启动!")

def close_smtc():
    player.command_manager.is_enabled = True
    smtc = player.system_media_transport_controls
    smtc.is_enabled = False
    smtc.is_play_enabled = False
    smtc.is_pause_enabled = False
    smtc.is_next_enabled = False
    smtc.is_previous_enabled = False
    smtc.playback_status = 0
    smtc.is_enabled = False
    logging.debug("SMTC 顺利关闭!")

class MainApp():
    def __init__(self):
        self.root = ttk.Window(themename = "minty")
        self.root.protocol("WM_DELETE_WINDOW", self.main_window_close)
        self.set_sub_process()
        self.setup_ui()
        self.main_window_loop()
        self.start_watchdog()
    
    def setup_ui(self):
        self.root.title("WMC-Bridge-Plugin beta 0.1")
        self.root.geometry("400x310")
        self.root.resizable(0, 0)
        #window basic setting

        self.now_playing_frame = ttk.Labelframe(self.root, text = "歌曲信息", bootstyle = "primary")
        self.now_playing_frame.place(x = 5, y = 5, width = 390, height = 85)
        self.now_playing_song = ttk.Label(self.now_playing_frame, text = "当前播放歌曲:未开始监听",
wraplength = 380)
        self.now_playing_song.pack(fill = X)
        self.now_play_progress = ttk.Label(self.now_playing_frame, text = "当前播放进度:未开始监听")
        self.now_play_progress.pack(fill = X)
        #set song_info labelframe
        
        self.music_cover_frame = ttk.Labelframe(self.root, text = "歌曲封面", bootstyle = "primary")
        self.music_cover_frame.place(x = 5, y = 95, width = 186, height = 202)
        self.music_cover = ttk.Label(self.music_cover_frame, text = "未获取到封面")
        self.music_cover.pack(fill = BOTH)
        #set player cover idle

        self.music_lyric_frame = ttk.Labelframe(self.root, text = "实时歌词", bootstyle = "primary",)
        self.music_lyric_frame.place(x = 204, y = 95, width = 190, height = 122)
        self.music_lyric = ttk.Label(self.music_lyric_frame, text = "未开始监听", wraplength = 185)
        self.music_lyric.pack(fill = X)
        #set song lyrics

        self.music_platform = ttk.Combobox(self.root, values = ["网易云音乐", "酷狗音乐-暂未支持"],
state = "readonly", width = 23)
        self.music_platform.set("网易云音乐")
        self.music_platform.place(x = 205, y = 227)
        self.start_listen = ttk.Button(self.root, text = "开始监听", bootstyle = "primary-outline", width = 23,
command = self.toggle_listener)
        self.start_listen.config(state = ttk.DISABLED)
        self.start_listen.place(x = 206, y = 266)
        #set other things
        logging.info("设置UI完成!")

    def set_sub_process(self):
        self.watchdog_queue = Queue()
        self.stop_watchdog_event = Event()
        self.watchdog_process = None
        self.listener_queue = Queue()
        self.stop_listener_event = Event()
        self.listener_process = None

    def main_window_loop(self):
        #该变量存储当前目标音乐播放器的基址
        #FIXME: 由于获取函数较慢(详见./libs/process.py/get_process_info), 后续修复应注重精确获取基址提升速度
        self.player_base_address = None
        logging.info("进入主窗口循环!")
        def update():
            if not self.watchdog_queue.empty():
                player_data = self.watchdog_queue.get()
                #监测音乐播放器进程状态
                if not player_data["status"]:
                    self.now_playing_song.config(text = "当前播放歌曲:未开启音乐软件")
                    self.now_play_progress.config(text = "当前播放进度:未开启音乐软件")
                    self.music_lyric.config(text = "未开启音乐软件")
                    self.music_cover.config(text = "未开启音乐软件")
                    self.start_listen.config(state = ttk.DISABLED)
                else:
                    self.now_playing_song.config(text = "当前播放歌曲:未开始监听")
                    self.now_play_progress.config(text = "当前播放进度:未开始监听")
                    self.music_lyric.config(text = "未开始监听")
                    self.music_cover.config(text = "未获取到封面", image = "")
                    self.start_listen.config(state = ttk.NORMAL)
                #当基址获取异常时, 退出listener进程并调整主窗口按钮状态
                if player_data["base_address"] == None:
                    self.player_address = None
                    self.start_listen.config(text = "开始监听")
                    self.now_playing_song.config(text = "当前播放歌曲:播放器已退出")
                    self.now_play_progress.config(text = "当前播放进度:播放器已退出")
                    self.music_lyric.config(text = "播放器已退出")
                    self.music_cover.config(text = "播放器已退出", image = "")
                    self.stop_listener()
                else:
                    self.player_address = player_data["base_address"]

            if not self.listener_queue.empty():
                listener_data = self.listener_queue.get()
                #刷新播放乐曲/时间
                self.now_playing_song.config(text = f"当前播放歌曲:{listener_data['song_name']}")
                self.now_play_progress.config(text = 
f"当前播放进度:{listener_data['play_progress'][0]} / {listener_data['play_progress'][1]}")
                #刷新歌词
                if listener_data["lyric"] == None:
                    self.music_lyric.config(text = "暂未获取到歌词")
                else:
                    self.music_lyric.config(text = f"{listener_data['lyric']}\n{listener_data['trans_lyric']}")
                #刷新图片
                if listener_data["status"]:
                    if listener_data["cover_ready"]:
                        original_cover_data = Image.open(f"./cache/{listener_data['song_id']}.jpg").convert("RGB")
                        resized_img = original_cover_data.resize((185, 185), resample = Image.Resampling.LANCZOS)
                        cover_tk_data = ImageTk.PhotoImage(resized_img)
                        self.music_cover.config(image = cover_tk_data, text = None)
                        self.music_cover.image = cover_tk_data
                    else:
                        self.music_cover.config(image = "", text = "未获取到封面")
                #刷新SMTC
                updater.type = winsdk.windows.media.MediaPlaybackType.MUSIC
                updater.app_media_id = "WMC-Bridge-Plugin"
                #设置标题和艺术家
                updater.music_properties.title = listener_data['song_name']
                updater.music_properties.artist = listener_data['song_artist']
                #向BytesIO写入图片信息并刷新至SMTC
                original_cover_data = Image.open(f"./cache/{listener_data['song_id']}.jpg").convert("RGB")
                byte_stream = BytesIO()
                original_cover_data.save(byte_stream, format="JPEG")
                image_bytes = byte_stream.getvalue()
                mem_stream = winsdk.windows.storage.streams.InMemoryRandomAccessStream()
                writer = winsdk.windows.storage.streams.DataWriter(mem_stream)
                writer.write_bytes(image_bytes)
                writer.store_async()
                mem_stream.flush_async()
                updater.thumbnail = winsdk.windows.storage.streams.RandomAccessStreamReference.create_from_stream(mem_stream)
                #修改SMTC时间线数据
                timeline.start_time = timedelta(seconds = 0)
                timeline.position = timedelta(seconds = int(listener_data["original_progress"][0]))
                timeline.end_time = timedelta(seconds = int(listener_data["original_progress"][1]))
                #更新信息
                smtc.update_timeline_properties(timeline)
                updater.update()
            self.root.after(250, update)
        #开始定时循环, 250ms一次
        self.root.after(250, update)

    def is_listener_running(self):
        return self.listener_process and self.listener_process.is_alive()

    def start_listener(self):
        if not self.is_listener_running():
            open_smtc()
            platform = self.music_platform.get()
            self.stop_listener_event.clear()
            self.listener_process = start_listener(self.stop_listener_event, self.listener_queue, self.player_address,
config.get_config(player_platform_addr_tran[platform][0]),
config.get_config(player_platform_addr_tran[platform][1]),
config.get_config(player_platform_addr_tran[platform][2]))
            logging.debug("Listener 顺利启动!")

    def stop_listener(self):
        if self.is_listener_running():
            close_smtc()
            self.stop_listener_event.set()
            self.listener_process.join(timeout = 1)
            if self.listener_process.is_alive():
                self.listener_process.terminate()
            self.listener_process = None
        logging.debug("Listener 顺利退出!")

    def is_watchdog_running(self):
        return self.watchdog_process and self.watchdog_process.is_alive()
    
    def start_watchdog(self):
        try:
            self.watchdog_process = start_watchdog(self.stop_watchdog_event, self.watchdog_queue, self.music_platform.get())
            logging.debug("Watchdog 顺利启动!")
        except Exception as err:
            logging.critical(f"Watchdog 无法启动! 错误信息: {err}")

    def toggle_listener(self):
        try:
            if self.is_listener_running():
                self.stop_listener()
                self.start_listen.config(text = "开始监听")
            else:
                self.start_listener()
                self.start_listen.config(text = "停止监听")
        except Exception as err:
            logging.critical(f"Listener 无法启动! 错误信息: {err}")

    def main_window_close(self):
        close_smtc()
        if self.is_watchdog_running():
            self.stop_watchdog_event.set()
            self.watchdog_process.join(timeout = 1)
            if self.watchdog_process.is_alive():
                self.watchdog_process.terminate()
            self.watchdog_process = None
        logging.debug("Watchdog 顺利退出!")
        if self.is_listener_running():
            self.stop_listener_event.set()
            self.listener_process.join(timeout = 1)
            if self.listener_process.is_alive():
                self.listener_process.terminate()
            self.listener_process = None
        logging.debug("Listener 顺利退出!")
        img = Image.new('RGB', (500, 500), (255, 255, 255))
        with open("./data/cover.jpg", "wb") as f:
            img.save(f)
        with open("./data/lyric.txt", "w", encoding = "UTF-8") as f:
            f.write("")
        self.root.destroy()

if __name__ == "__main__":
    multiprocessing.set_start_method('spawn') 
    freeze_support()
    app = MainApp()
    app.root.mainloop()