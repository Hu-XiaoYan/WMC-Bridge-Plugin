import time
import tomli
import tkinter as tk
from tkinter import messagebox
from multiprocessing import freeze_support, Event, Queue
from PIL import Image, ImageTk

from libs.new_listener import start_watchdog

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
        self.start_listen_process = tk.Button(self.root, text = "开始监听", command = lambda:print("link start! (bushi)"))
        self.open_cover_idle_image = Image.open("./libs/music_cover_idle.jpg").resize((175, 175))
        self.idle_image_to_tk= ImageTk.PhotoImage(self.open_cover_idle_image)
        self.music_cover = tk.Label(self.root, image = self.idle_image_to_tk)
        #set elements

        self.now_playing_song.grid(column = 0, row = 0)
        self.play_progress.grid(column = 1, row = 0)
        self.music_cover.grid(column = 0, row = 1)
        self.start_listen_process.grid(column = 0, row = 2)
        #set grid

        self.start_watchdog()

    def main_window_loop(self):
        def update():
            print("update ui")
            detect_player = self.watchdog_queue.get()
            if detect_player["status"] == False:
                self.start_listen_process.config(state = tk.DISABLED)
            else:
                self.start_listen_process.config(state = tk.NORMAL)
            self.root.after(500, update)
        self.root.after(500, update)

    def is_watchdog_running(self):
        return self.watchdog_process and self.watchdog_process.is_alive()

    def set_sub_process(self):
        self.watchdog_queue = Queue()
        self.stop_watchdog = Event()
        self.watchdog_process = None

    def start_watchdog(self):
        self.watchdog_process = start_watchdog(self.stop_watchdog, self.watchdog_queue)

    def on_close(self):
        if self.is_watchdog_running():
            self.stop_watchdog.set()
            self.watchdog_process.join(timeout = 1)
            if self.watchdog_process.is_alive():
                self.watchdog_process.terminate()
            self.watchdog_process = None
        self.root.destroy()

if __name__ == "__main__":
    freeze_support()
    app = MainApp()
    app.root.mainloop()