import tomli
import os
import asyncio
import ttkbootstrap as ttk
from io import BytesIO
from ttkbootstrap.constants import *
from multiprocessing import freeze_support, Queue, Event
from PIL import Image, ImageTk

from datetime import timedelta
import winsdk.windows.media
import winsdk.windows.media.playback
import winsdk.windows.storage.streams
player = winsdk.windows.media.playback.MediaPlayer()
timeline = winsdk.windows.media.SystemMediaTransportControlsTimelineProperties()
#initialize stmc

from libs.listener import start_watchdog, start_listener
#used 3rd party modules
#pillow, tomli, winsdk, win32api, requests

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
player_platform_addr_tran = {"网易云音乐": ["cloudmusic_play_time_offset", "cloudmusic_play_end_time_offset",
"cloudmusic_lyric_address_offset_list", "cloudmusic_song_id_offset"]}

async def set_smtc_info(song_title, song_artist, pil_img):
    smtc = player.system_media_transport_controls
    updater = smtc.display_updater
    updater.type = winsdk.windows.media.MediaPlaybackType.MUSIC
    updater.app_media_id = "WMC-Bridge-Plugin"
    updater.music_properties.title = song_title
    updater.music_properties.artist = song_artist
    byte_stream = BytesIO()
    pil_img.save(byte_stream, format="PNG")
    mem_stream = winsdk.windows.storage.streams.InMemoryRandomAccessStream()
    writer = winsdk.windows.storage.streams.DataWriter(mem_stream)
    writer.write_bytes(byte_stream.getvalue())
    writer.store_async()
    mem_stream.seek(0)
    updater.thumbnail = winsdk.windows.storage.streams.RandomAccessStreamReference.create_from_stream(mem_stream)
    updater.update()

def update_smtc(song_title, song_artist, pil_img):
    asyncio.run(set_smtc_info(song_title, song_artist, pil_img))

def open_smtc():
    global player, timeline
    player.command_manager.is_enabled = False
    smtc = player.system_media_transport_controls

    smtc.is_enabled = True
    smtc.is_play_enabled = True
    smtc.is_pause_enabled = True
    smtc.is_next_enabled = True
    smtc.is_previous_enabled = True
    smtc.playback_status = winsdk.windows.media.MediaPlaybackStatus.PLAYING
    smtc.is_enabled = True

def close_smtc():
    global player, timeline
    player.command_manager.is_enabled = True
    smtc = player.system_media_transport_controls

    smtc.is_enabled = False
    smtc.is_play_enabled = False
    smtc.is_pause_enabled = False
    smtc.is_next_enabled = False
    smtc.is_previous_enabled = False
    smtc.playback_status = winsdk.windows.media.MediaPlaybackStatus.CLOSED
    smtc.is_enabled = False

    timeline.start_time = timedelta(0)
    timeline.end_time = timedelta(0)
    timeline.position = timedelta(0)
    #clear timeline

class MainApp():
    def __init__(self):
        self.root = ttk.Window(themename = "minty")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.set_sub_process()
        self.setup_ui()
        self.main_window_loop()

    def setup_ui(self):
        self.root.title("WMC-Bridge-Plugin alpha 0.1")
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
        #set songinfo labelframe
        
        self.music_cover_frame = ttk.Labelframe(self.root, text = "歌曲封面", bootstyle = "primary")
        self.music_cover_frame.place(x = 5, y = 95, width = 186, height = 202)
        self.music_cover = ttk.Label(self.music_cover_frame, text = "未获取到封面")
        self.music_cover.pack(fill = BOTH)
        #set player cover idle

        self.music_lryic_frame = ttk.Labelframe(self.root, text = "实时歌词", bootstyle = "primary",)
        self.music_lryic_frame.place(x = 204, y = 95, width = 190, height = 122)
        self.music_lryic = ttk.Label(self.music_lryic_frame, text = "未开始监听", wraplength = 185)
        self.music_lryic.pack(fill = X)
        #set song lryics

        self.music_platform = ttk.Combobox(self.root, values = ["网易云音乐", "QQ音乐-暂未支持", "酷狗音乐-暂未支持"],
state = "readonly", width = 23)
        self.music_platform.set("网易云音乐")
        self.music_platform.place(x = 205, y = 227)
        self.start_listen = ttk.Button(self.root, text = "开始监听", bootstyle = "primary-outline", width = 23,
command = self.toggle_listener)
        self.start_listen.config(state = ttk.DISABLED)
        self.start_listen.place(x = 206, y = 266)
        #set other things

        self.start_watchdog()
        #open the watchdog process

    def main_window_loop(self):
        self.player_address = None
        self.pil_data = None
        def update():
            if not self.watchdog_queue.empty():
                detect_player = self.watchdog_queue.get()
                if detect_player["status"] == False:
                    self.now_playing_song.config(text = "当前播放歌曲:未开启音乐软件")
                    self.now_play_progress.config(text = "当前播放进度:未开启音乐软件")
                    self.music_lryic.config(text = "未开启音乐软件")
                    self.music_cover.config(text = "未开启音乐软件")
                    self.start_listen.config(state = ttk.DISABLED)
                elif detect_player["status"] == True and self.is_watchdog_running() == True:
                    self.now_playing_song.config(text = "当前播放歌曲:未开始监听")
                    self.now_play_progress.config(text = "当前播放进度:未开始监听")
                    self.music_lryic.config(text = "未开始监听")
                    self.music_cover.config(text = "未获取到封面")
                    self.start_listen.config(state = ttk.NORMAL)
                if detect_player["base_address"] == None:
                    self.player_address = None
                    self.start_listen.config(text = "开始监听")
                    self.stop_listener()
                else:
                    self.player_address = detect_player["base_address"]
            #Watchdog

            if not self.listener_queue.empty():
                listener_data = self.listener_queue.get()
                print(listener_data)
                self.now_playing_song.config(text = f"当前播放歌曲:{listener_data['song_name']}")
                self.now_play_progress.config(text = 
f"当前播放进度:{listener_data['play_progress'][0]} / {listener_data['play_progress'][1]}")
                if listener_data["cover_status"]:
                    cover_tk_data = ImageTk.PhotoImage(listener_data["cover_img"])
                    self.music_cover.config(image = cover_tk_data, text = None)
                    self.music_cover.image = cover_tk_data
                    print(f"flash! img:{listener_data['cover_img']}")
                    update_smtc(listener_data['song_name'], listener_data['song_artist'], listener_data["cover_img"])
                else:
                    self.music_cover.config(image = None, text = "未获取到封面")
                if listener_data["lryic"] == None:
                    self.music_lryic.config(text = "暂未获取到歌词")
                else:
                    self.music_lryic.config(text = listener_data["lryic"])
            #listener
            self.root.after(250, update)
        self.root.after(250, update)

    def check_cover_availability(self):
        def check():
            if self.current_song_id is None:
                return
            cover_path = f"./cache/{self.current_song_id}.jpg"
            if os.path.exists(cover_path):
                try:
                    original_inage_data = Image.open(cover_path)
                    cover_tk_data = ImageTk.PhotoImage(original_inage_data)
                    self.music_cover.config(image = cover_tk_data, text = None)
                    self.music_cover.image = cover_tk_data
                except:
                    self.music_cover.config(image = None, text = "未获取到封面")
            else:
                self.root.after(250, check)
        self.root.after(0, check)

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
            self.start_listen.config(text = "开始监听")
        else:
            self.start_listener()
            self.start_listen.config(text = "停止监听")
    
    def start_listener(self):
        if not self.is_listener_running():
            open_smtc()
            platform = self.music_platform.get()
            self.stop_listener_event.clear()
            self.listener_process = start_listener(self.stop_listener_event, self.listener_queue, self.player_address,
config.get_config(player_platform_addr_tran[platform][0]),
config.get_config(player_platform_addr_tran[platform][1]),
config.get_config(player_platform_addr_tran[platform][2]),
config.get_config(player_platform_addr_tran[platform][3]))
    
    def stop_listener(self):
        if self.is_listener_running():
            close_smtc()
            self.stop_listener_event.set()
            self.listener_process.join(timeout = 1)
            if self.listener_process.is_alive():
                self.listener_process.terminate()
            self.listener_process = None

    def start_watchdog(self):
        self.watchdog_process = start_watchdog(self.stop_watchdog_event, self.watchdog_queue, self.music_platform.get())

    def on_close(self):
        close_smtc()
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

if __name__ == "__main__":
    freeze_support()
    app = MainApp()
    app.root.mainloop()