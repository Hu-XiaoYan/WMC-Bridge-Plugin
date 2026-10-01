import logging
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from PIL import Image, ImageTk

#界面: 窗口和所有控件的创建/刷新都集中在这个类里
class MainWindow():
    def __init__(self):
        self.root = ttk.Window(themename = "minty")
        self.cover_data = None
        self.setup_ui()

    def setup_ui(self):
        #基础窗口设置
        self.root.title("WMC-Bridge-Plugin beta 1.0")
        self.root.geometry("400x310")
        self.root.resizable(False, False)
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
        self.music_lyric_frame = ttk.Labelframe(self.root, text = "实时歌词", bootstyle = "primary")
        self.music_lyric_frame.place(x = 204, y = 95, width = 190, height = 122)
        self.music_lyric = ttk.Label(self.music_lyric_frame, text = "未开始监听", wraplength = 185)
        self.music_lyric.pack(fill = X)

        #设置其他控件
        self.music_platform = ttk.Combobox(self.root, values = ["网易云音乐 3.0+", "酷狗音乐-暂未支持"],
state = "readonly", width = 23)
        self.music_platform.set("网易云音乐 3.0+")
        self.music_platform.place(x = 205, y = 227)
        self.start_listen = ttk.Button(self.root, text = "开始监听", bootstyle = "primary-outline",
width = 23)
        self.start_listen.config(state = ttk.DISABLED)
        self.start_listen.place(x = 206, y = 266)
        logging.info("设置UI完成!")

    #刷新封面(图片引用必须留着, 不然会被回收掉)
    def set_cover(self, image_path):
        if not image_path:
            self.cover_data = None
            self.music_cover.config(image = "", text = "未获取到封面")
            return
        original_cover_data = Image.open(image_path).convert("RGB")
        resized_img = original_cover_data.resize((185, 185), resample = Image.Resampling.LANCZOS)
        self.cover_data = ImageTk.PhotoImage(resized_img)
        self.music_cover.config(image = self.cover_data, text = None)
