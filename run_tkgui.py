import requests
import tkinter as tk
from io import BytesIO
from PIL import Image, ImageTk
from tkinter import messagebox
from multiprocessing import Event, Queue, freeze_support

from libs.listener import start_listener

def format_time(time):
    return f"{time//60%60:02d}:{time%60:02d}"

class MainApp:
    def __init__(self):
        self.root = tk.Tk()
        self.setup_ui()
        self.setup_sub_process()
        self.setup_update_ui_loop()

    def setup_ui(self):
        self.root.title("WMC-Bridge-Plugin indev 0.0.2")
        self.root.geometry("400x300")
        self.root.resizable(0, 0)

        main_window_menu_bar = tk.Menu(self.root)
        main_help_menu = tk.Menu(main_window_menu_bar, tearoff = 0)
        main_help_menu.add_command(label = "关于", command = lambda: messagebox.showinfo("关于 WMC-Bridge-Plugin",
        """WMC-Bridge-Plugin是一个将不支持Windows Media Control的音乐播放器内的音乐信息转换为Windows Media Control信息的插件, 以便其他软件进行读取. 目前该插件处于Indev阶段, 敬请期待."""))
        main_window_menu_bar.add_cascade(label = "帮助", menu = main_help_menu)
        self.root.config(menu = main_window_menu_bar)

        self.now_play_song = tk.Label(self.root, text = "当前播放乐曲:未开始监听")
        self.play_progress = tk.Label(self.root, text = "播放进度:未开始监听")
        self.start_listen_btn = tk.Button(self.root, text = "开始监听", command = self.toggle_listener)
        self.open_idle = Image.open("./libs/music_cover_idle.jpg").resize((175, 175))
        self.cover_idle = ImageTk.PhotoImage(self.open_idle)
        self.music_cover = tk.Label(self.root, image = self.cover_idle)

        self.now_play_song.grid(column = 0, row = 0)
        self.play_progress.grid(column = 1, row = 0)
        self.music_cover.grid(column = 0, row = 1)
        self.start_listen_btn.grid(column = 0, row = 2)

    def setup_sub_process(self):
        self.stop_event = Event()
        self.process_queue = Queue()
        self.listener_process = None

    def setup_update_ui_loop(self):
        def update():
            cover_tk = None
            if not self.process_queue.empty():
                listener_data = self.process_queue.get()
                progress = f"{format_time(int(listener_data[0]))} / {format_time(int(listener_data[1]))}" if self.is_listener_running() else "未开始监听"
                self.play_progress.config(text = f"播放进度:{progress}")
                listener_data = self.process_queue.get()
                song_name = f"{listener_data}" if self.is_listener_running() else "未开始监听"
                self.now_play_song.config(text = f"当前播放乐曲:{song_name}")
                listener_data = self.process_queue.get()
                if listener_data[0] == True:
                    result = requests.get(f"https://music.163.com/api/search/get?s={listener_data[0]} {listener_data[1]}/CubesCollective&type=1&offset=0&limit=1")
                    result_dict = result.json()
                    song_id = result_dict["result"]["songs"][0]["id"]
                    music_info = requests.get(f"https://music.163.com/api/song/detail?ids=[{song_id}]")
                    music_info_dict = music_info.json()
                    music_cover_url = music_info_dict["songs"][0]["album"]["picUrl"]
                    response = requests.get(music_cover_url)
                    image_data = BytesIO(response.content)
                    original_image = Image.open(image_data)
                    resized_image = original_image.resize((175, 175)).convert("RGB")
                    cover_tk = ImageTk.PhotoImage(resized_image) 
                    self.music_cover.config(image = cover_tk)
                    self.music_cover.image = cover_tk

            self.root.after(500, update) 
        self.root.after(500, update)

    def is_listener_running(self):
        return self.listener_process and self.listener_process.is_alive()
    
    def toggle_listener(self):
        if self.is_listener_running():
            self.stop_listener()
            self.start_listen_btn.config(text = "开始监听")
        else:
            self.start_listener()
            self.start_listen_btn.config(text = "停止监听")

    def start_listener(self):
        if not self.is_listener_running():
            self.stop_event.clear()
            self.listener_process = start_listener(self.stop_event, self.process_queue)

    def stop_listener(self):
        if self.is_listener_running():
            self.stop_event.set()
            self.listener_process.join(timeout = 1)
            if self.listener_process.is_alive():
                self.listener_process.terminate()
            self.listener_process = None

    def on_close(self):
        self.stop_listener()
        self.root.destroy()

if __name__ == "__main__":
    freeze_support()
    app = MainApp()
    app.root.mainloop()
