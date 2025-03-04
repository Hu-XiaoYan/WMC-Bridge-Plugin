import tomli
import requests
import tkinter as tk
from io import BytesIO
from tkinter import messagebox
from multiprocessing import freeze_support, Event, Queue
from PIL import Image, ImageTk

from libs.listener import start_watchdog, start_listener
#used 3rd party modules
#pillow, tomli

class ReadConfig:
    _instance = None
    _data = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._data = cls.load_config()
        return cls._instance
    
    @classmethod
    def load_config(cls):
        with open("./libs/config.toml", "rb") as f:
            return tomli.load(f)

    def get_config(self, key):
        return self._data.get(key)

config = ReadConfig()

class MainApp():
    def __init__(self):
        self.root = tk.Tk()
        self.set_sub_process()
        self.setup_ui()
        self.main_window_loop()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def setup_ui(self):
        self.root.title("WMC-Bridge-Plugin indev 0.1.0")
        self.root.geometry("400x300")
        self.root.resizable(0, 0)
        #window basic setting

        main_window_menu_bar = tk.Menu(self.root)
        main_help_menu = tk.Menu(main_window_menu_bar, tearoff = 0)
        main_help_menu.add_command(label = "关于", command = lambda: messagebox.showinfo("关于 WMC-Bridge-Plugin",
        """WMC-Bridge-Plugin是一个将不支持Windows Media Control的音乐播放器内的音乐信息转换为Windows Media Control信息的插件, 以便其他软件进行读取. 目前该插件处于Indev阶段, 敬请期待."""))
        main_window_menu_bar.add_cascade(label = "帮助", menu = main_help_menu)
        self.root.config(menu = main_window_menu_bar)
        #set menu bar

        self.now_playing_song = tk.Label(self.root, text = "当前播放乐曲:未开始监听")
        self.play_progress = tk.Label(self.root, text = "播放进度:未开始监听")
        self.start_listen_process = tk.Button(self.root, text = "开始监听", command = self.toggle_listener)
        self.open_cover_idle_image = Image.open("./libs/music_cover_idle.jpg").resize((175, 175))
        self.idle_image_to_tk= ImageTk.PhotoImage(self.open_cover_idle_image)
        self.music_cover = tk.Label(self.root, image = self.idle_image_to_tk)
        #set elements

        self.now_playing_song.grid(column = 0, row = 0)
        self.play_progress.grid(column = 0, row = 1)
        self.music_cover.grid(column = 0, row = 2)
        self.start_listen_process.grid(column = 0, row = 3)
        #set grid

        self.start_watchdog()

    def main_window_loop(self):
        self.player_address = None
        def update():
            if not self.watchdog_queue.empty():
                detect_player = self.watchdog_queue.get()
                if detect_player["status"] == False:
                    self.now_playing_song.config(text = "当前播放乐曲:未开启音乐软件")
                    self.play_progress.config(text = "播放进度:未开启音乐软件")
                    self.start_listen_process.config(state = tk.DISABLED)
                else:
                    self.now_playing_song.config(text = "当前播放乐曲:未开始监听")
                    self.play_progress.config(text = "播放进度:未开始监听")
                    self.start_listen_process.config(state = tk.NORMAL)
                if detect_player["base_address"] == None:
                    self.player_address = None
                    self.start_listen_process.config(text = "开始监听")
                    self.stop_listener()
                else:
                    self.player_address = detect_player["base_address"]
            if not self.listener_queue.empty():
                listener_data = self.listener_queue.get()
                print(listener_data)
                self.now_playing_song.config(text = f"当前播放乐曲:{listener_data['song_name']}")
                self.play_progress.config(text = f"播放进度:{listener_data['play_progress'][0]} / {listener_data['play_progress'][1]}")
                if listener_data["image_url"] == None:
                    self.music_cover = tk.Label(self.root, image = self.idle_image_to_tk)
                    self.music_cover.image = self.idle_image_to_tk
                elif listener_data["image_url"] != None and listener_data["status"] == True:
                    response = requests.get(listener_data["image_url"])
                    image_data = BytesIO(response.content)
                    original_image = Image.open(image_data)
                    resized_image = original_image.resize((175, 175)).convert("RGB")
                    cover_tk = ImageTk.PhotoImage(resized_image) 
                    self.music_cover.config(image = cover_tk)
                    self.music_cover.image = cover_tk
            self.root.after(500, update)
        self.root.after(500, update)
        #flash ui

    def set_sub_process(self):
        self.watchdog_queue = Queue()
        self.listener_queue = Queue()
        self.stop_watchdog_event = Event()
        self.stop_listener_event = Event()
        self.watchdog_process = None
        self.listener_process = None

    def is_listener_running(self):
        return self.listener_process and self.listener_process.is_alive()

    def is_watchdog_running(self):
        return self.watchdog_process and self.watchdog_process.is_alive()

    def toggle_listener(self):
        if self.is_listener_running():
            self.stop_listener()
            self.start_listen_process.config(text = "开始监听")
        else:
            self.start_listener()
            self.start_listen_process.config(text = "停止监听")

    def start_listener(self):
        if not self.is_listener_running():
            self.stop_listener_event.clear()
            self.listener_process = start_listener(self.stop_listener_event, self.listener_queue,
config.get_config("cloudmusic_play_time_offset"), config.get_config("cloudmusic_play_end_time_offset"), self.player_address)

    def stop_listener(self):
        if self.is_listener_running():
            self.stop_listener_event.set()
            self.listener_process.join(timeout = 1)
            if self.listener_process.is_alive():
                self.listener_process.terminate()
            self.listener_process = None

    def start_watchdog(self):
        self.watchdog_process = start_watchdog(self.stop_watchdog_event, self.watchdog_queue)

    def on_close(self):
        if self.is_watchdog_running():
            self.stop_watchdog_event.set()
            self.watchdog_process.join(timeout = 1)
            if self.watchdog_process.is_alive():
                self.watchdog_process.terminate()
            self.watchdog_process = None
        if self.is_listener_running():
            self.stop_listener_event.set()
            self.listener_process.join(timeout = 1)
            if self.listener_process.is_alive():
                self.listener_process.terminate()
            self.listener_process = None
        self.root.destroy()
    #when main process quit
    #kill all sub process

if __name__ == "__main__":
    freeze_support()
    app = MainApp()
    app.root.mainloop()