import os
import threading
import logging
from libs.logger import setup_colored_log
setup_colored_log()
from threading import Event
from queue import Queue

import tomli
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from PIL import Image, ImageTk
# 使用的第三方模块有:
# ttkbootstrap--图形界面支持
# colorlog--彩色Log支持
# tomli--toml配置读取
# psutil--加速基址获取
# win32api--进程相关
# requests--网络相关

from libs.watchdog import watchdog_task
from libs.listener import cloudmusic_listener_task

#读取配置文件并持续化加载
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
            logging.critical("找不到配置文件! 已在当前目录下新建配置文件, 请前往Github复制相关配置!")
            exit()
        try:
            with open("./config.toml", "rb") as f:
                logging.info("首次读取配置完成!")
                return tomli.load(f)
        except:
            logging.critical("无法读取配置文件! 请确保你复制的配置内容符合Toml配置文件格式!")
            exit()
        
    def get_config(self, key):
        if self._data == None:
            logging.critical("无法读取配置文件! 请确保你复制的配置内容符合Toml配置文件格式!")
            exit()
        if self._data.get(key) == None:
            logging.error("无法读取键值对! 请确认Toml配置文件!")
            return None
        else:
            logging.info(f"读取成功! 键: {key} --> 值: {self._data.get(key)}")
            return self._data.get(key)       
config = ReadConfig()
#配置索引
platform_eng_name = {"网易云音乐": "cloudmusic", "酷狗音乐": "kugoumusic"}

class MainApp():
    def __init__(self):
        #初始化窗口及窗口退出动作
        self.root = ttk.Window(themename = "minty")
        self.root.protocol("WM_DELETE_WINDOW", self.on_exit)
        #初始化子线程队列及停止事件
        self.set_sub_thread()
        #UI初始化
        self.setup_ui()
        #启动窗口循环
        self.main_window_loop()
        #启动watchdog
        self.start_watchdog()

    def setup_ui(self):
        #基础窗口设置
        self.root.title("WMC-Bridge-Plugin beta 0.2")
        self.root.geometry("400x310")
        self.root.resizable(0, 0)
        #高DPI适配(测试)
        dpi_scaling = self.root.winfo_fpixels('1i') / 75.0
        self.root.tk.call("tk", "scaling", dpi_scaling)

        #设置歌曲信息
        self.now_playing_frame = ttk.Labelframe(self.root, text = "歌曲信息", bootstyle = "primary")
        self.now_playing_frame.place(x = 5, y = 5, width = 390, height = 85)
        self.now_playing_song = ttk.Label(self.now_playing_frame, text = "当前播放歌曲:未开始监听",
wraplength = 380)
        self.now_playing_song.pack(fill = X)
        self.now_play_progress = ttk.Label(self.now_playing_frame, text = "当前播放进度:未开始监听")
        self.now_play_progress.pack(fill = X)
        
        #设置歌曲封面
        self.music_cover_frame = ttk.Labelframe(self.root, text = "歌曲封面", bootstyle = "primary")
        self.music_cover_frame.place(x = 5, y = 95, width = 186, height = 202)
        self.music_cover = ttk.Label(self.music_cover_frame, text = "未获取到封面")
        self.music_cover.pack(fill = BOTH)

        #设置实时歌词
        self.music_lyric_frame = ttk.Labelframe(self.root, text = "实时歌词", bootstyle = "primary",)
        self.music_lyric_frame.place(x = 204, y = 95, width = 190, height = 122)
        self.music_lyric = ttk.Label(self.music_lyric_frame, text = "未开始监听", wraplength = 185)
        self.music_lyric.pack(fill = X)

        #设置其他控件
        self.music_platform = ttk.Combobox(self.root, values = ["网易云音乐", "酷狗音乐-暂未支持"],
state = "readonly", width = 23)
        self.music_platform.set("网易云音乐")
        self.music_platform.place(x = 205, y = 227)
        self.start_listen = ttk.Button(self.root, text = "开始监听", bootstyle = "primary-outline", width = 23,
command = self.toggle_listener)
        self.start_listen.config(state = ttk.DISABLED)
        self.start_listen.place(x = 206, y = 266)
        logging.info("设置UI完成!")
    
    def main_window_loop(self):
        #该变量存储当前目标音乐播放器的基址
        self.player_address = None
        logging.info("进入主窗口循环!")
        def update():
            if not self.watchdog_queue.empty():
                player_data = self.watchdog_queue.get()
                #监测音乐播放器进程状态
                if player_data["status"]:
                    self.now_playing_song.config(text = "当前播放歌曲:未开始监听")
                    self.now_play_progress.config(text = "当前播放进度:未开始监听")
                    self.music_lyric.config(text = "未开始监听")
                    self.music_cover.config(text = "未获取到封面", image = "")
                    self.start_listen.config(state = ttk.NORMAL)
                else:
                    self.now_playing_song.config(text = "当前播放歌曲:未开启音乐软件")
                    self.now_play_progress.config(text = "当前播放进度:未开启音乐软件")
                    self.music_lyric.config(text = "未开启音乐软件")
                    self.music_cover.config(text = "未开启音乐软件")
                    self.start_listen.config(state = ttk.DISABLED)
                #当基址获取异常时, 退出listener进程并调整主窗口按钮状态
                if player_data["base_address"] == None:
                    self.player_address = None
                else:
                    self.player_address = player_data["base_address"]

            if not self.listener_queue.empty():
                listener_data = self.listener_queue.get()
                #刷新播放乐曲/时间
                self.now_playing_song.config(text = f"当前播放歌曲:{listener_data['song_name']}")
                self.now_play_progress.config(text = 
f"当前播放进度:{listener_data['play_progress'][0]} / {listener_data['play_progress'][1]}")
                #刷新图片
                if listener_data["status"]:
                    if listener_data["cover_ready"]:
                        original_cover_data = Image.open(f"./data/pic/{listener_data['song_id']}.jpg").convert("RGB")
                        resized_img = original_cover_data.resize((185, 185), resample = Image.Resampling.LANCZOS)
                        cover_tk_data = ImageTk.PhotoImage(resized_img)
                        self.music_cover.config(image = cover_tk_data, text = None)
                        self.music_cover.image = cover_tk_data
                    else:
                        self.music_cover.config(image = "", text = "未获取到封面")
                #刷新歌词
                if listener_data["lyric"] == None:
                    self.music_lyric.config(text = "暂未获取到歌词")
                else:
                    self.music_lyric.config(text = f"{listener_data['lyric']}\n{listener_data['trans_lyric']}")
            self.root.after(250, update)
        #开始定时循环, 250ms一次
        self.root.after(250, update)

    def set_sub_thread(self):
        self.watchdog_queue = Queue()
        self.watchdog_thread = None
        self.listener_queue = Queue()
        self.listener_thread = None
        self.stop_listener_event = Event()
    
    def start_watchdog(self):
        try:
            target_platform = self.music_platform.get()
            process_filename_list = config.get_config(platform_eng_name[target_platform])["process_filename"]
            self.watchdog_thread = threading.Thread(target = watchdog_task,
args = (self.watchdog_queue, process_filename_list, target_platform))
            self.watchdog_thread.daemon = True
            self.watchdog_thread.start()
            logging.debug("Watchdog 顺利启动!")
        except Exception as err:
            logging.critical(f"Watchdog 无法启动! 错误信息: {err}")

    def is_listener_running(self):
        return self.listener_thread and self.listener_thread.is_alive()

    def start_listener(self):
        if not self.is_listener_running():
            self.stop_listener_event.clear()
            try:
                target_platform = self.music_platform.get()
                offset_dict = config.get_config(platform_eng_name[target_platform])["offset"]
                if target_platform == "网易云音乐":
                    self.listener_thread = threading.Thread(target = cloudmusic_listener_task,
    args = (self.stop_listener_event, self.listener_queue, self.player_address,
offset_dict["position"], offset_dict["end"], offset_dict["song_id"]))
                else:
                    logging.critical("该平台暂未支持!")
                    exit()
                self.listener_thread.daemon = True
                self.listener_thread.start()
                logging.debug("Listener 顺利启动!")
            except Exception as err:
                logging.critical(f"Listener 无法启动! 错误信息: {err}")
    
    def stop_listener(self):
        if self.is_listener_running():
            self.stop_listener_event.set()
            self.listener_thread.join(timeout = 1)
            self.listener_thread = None
        logging.debug("Listener 顺利退出!")

    def toggle_listener(self):
        if self.is_listener_running():
            self.stop_listener()
            self.start_listen.config(text = "开始监听")
        else:
            self.start_listener()
            self.start_listen.config(text = "停止监听")

    def on_exit(self):
        #由于子进程皆为守护线程, 因此窗口关闭时可不用手动终结线程
        self.root.destroy()

if __name__=="__main__":
    app=MainApp()
    app.root.mainloop()