import tomli
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from io import BytesIO
from multiprocessing import freeze_support, Queue, Event
from PIL import Image, ImageTk

from datetime import timedelta
import winsdk.windows.media
import winsdk.windows.media.playback
import winsdk.windows.storage.streams
player = winsdk.windows.media.playback.MediaPlayer()
timeline = winsdk.windows.media.SystemMediaTransportControlsTimelineProperties()
smtc = player.system_media_transport_controls
updater = smtc.display_updater
#initialize smtc

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

def format_original_time(time):
    return [int(f"{time//60%60:02d}"), int(f"{time%60:02d}")]
    
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

class MainApp():
    def __init__(self):
        self.root = ttk.Window(themename = "minty")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.set_sub_process()
        self.setup_ui()
        self.main_window_loop()

    def setup_ui(self):
        self.root.title("WMC-Bridge-Plugin alpha 0.2")
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

        self.start_watchdog()
        #open the watchdog process

    def main_window_loop(self):
        self.player_address = None
        def update():
            if not self.watchdog_queue.empty():
                detect_player = self.watchdog_queue.get()
                if detect_player["status"] == False:
                    self.now_playing_song.config(text = "当前播放歌曲:未开启音乐软件")
                    self.now_play_progress.config(text = "当前播放进度:未开启音乐软件")
                    self.music_lyric.config(text = "未开启音乐软件")
                    self.music_cover.config(text = "未开启音乐软件")
                    self.start_listen.config(state = ttk.DISABLED)
                elif detect_player["status"] == True and self.is_watchdog_running() == True:
                    self.now_playing_song.config(text = "当前播放歌曲:未开始监听")
                    self.now_play_progress.config(text = "当前播放进度:未开始监听")
                    self.music_lyric.config(text = "未开始监听")
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
                self.now_playing_song.config(text = f"当前播放歌曲:{listener_data['song_name']}")
                self.now_play_progress.config(text = 
f"当前播放进度:{listener_data['play_progress'][0]} / {listener_data['play_progress'][1]}")
                position_time = int(listener_data["original_progress"][0])
                end_time = int(listener_data["original_progress"][1])

                updater.type = winsdk.windows.media.MediaPlaybackType.MUSIC
                updater.app_media_id = "WMC-Bridge-Plugin"
                updater.music_properties.title = listener_data['song_name']
                updater.music_properties.artist = listener_data['song_artist']
                
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

                timeline.start_time = timedelta(seconds = 0)
                timeline.position = timedelta(seconds = position_time)
                timeline.end_time = timedelta(seconds = end_time)
                smtc.update_timeline_properties(timeline)
                updater.update()

                if listener_data["status"]:
                    if listener_data["cover_ready"]:
                        original_cover_data = Image.open(f"./cache/{listener_data['song_id']}.jpg")
                        cover_tk_data = ImageTk.PhotoImage(original_cover_data)
                        self.music_cover.config(image = cover_tk_data, text = None)
                        self.music_cover.image = cover_tk_data
                    else:
                        self.music_cover.config(image = None, text = "未获取到封面")
                if listener_data["lyric"] == None:
                    self.music_lyric.config(text = "暂未获取到歌词")
                else:
                    self.music_lyric.config(text = listener_data["lyric"])
            #listener
            self.root.after(250, update)
        self.root.after(250, update)

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