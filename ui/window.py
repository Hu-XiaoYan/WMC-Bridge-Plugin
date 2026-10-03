import logging
import queue
import tkinter as tk
from tkinter.scrolledtext import ScrolledText

import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from PIL import Image, ImageTk

from ui.about_image import load_about_image

#日志文本的格式(和终端那份保持一致, 只是不带颜色)
LOG_FORMAT = logging.Formatter(
fmt = '%(asctime)s [%(levelname)s] %(funcName)s -> %(message)s', datefmt = '%H:%M:%S')

class WindowLogHandler(logging.Handler):
    #子线程不能直接碰控件, 所以塞队列里由界面定时取
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        try:
            self.log_queue.put(self.format(record))
        except Exception:
            pass

#界面: 窗口和所有控件的创建/刷新都集中在这个类里
class MainWindow():
    def __init__(self):
        self.root = ttk.Window(themename = "minty")
        self.cover_data = None
        self.about_image = None
        self.log_queue = queue.Queue()
        self.log_window = None
        self.log_handler = None
        self.about_window = None
        self.setup_ui()

    def setup_ui(self):
        #基础窗口设置
        self.root.title("WMC-Bridge-Plugin beta 1.0")
        self.root.geometry("400x310")
        self.root.resizable(False, False)
        #高DPI适配(测试)
        dpi_scaling = self.root.winfo_fpixels('1i') / 75.0
        self.root.tk.call("tk", "scaling", dpi_scaling)
        self.setup_menu()

        #设置歌曲信息
        self.now_playing_frame = ttk.Labelframe(self.root, text = "歌曲信息", bootstyle = "primary")
        self.now_playing_frame.place(x = 5, y = 5, width = 390, height = 85)
        self.now_playing_song = ttk.Label(self.now_playing_frame, text = "当前播放歌曲:请先选择播放器",
wraplength = 380)
        self.now_playing_song.pack(fill = X)
        self.now_play_progress = ttk.Label(self.now_playing_frame, text = "当前播放进度:请先选择播放器")
        self.now_play_progress.pack(fill = X)

        #设置歌曲封面
        self.music_cover_frame = ttk.Labelframe(self.root, text = "歌曲封面", bootstyle = "primary")
        self.music_cover_frame.place(x = 5, y = 95, width = 186, height = 202)
        self.music_cover = ttk.Label(self.music_cover_frame, text = "未获取到封面")
        self.music_cover.pack(fill = BOTH)

        #设置实时歌词
        self.music_lyric_frame = ttk.Labelframe(self.root, text = "实时歌词", bootstyle = "primary")
        self.music_lyric_frame.place(x = 204, y = 95, width = 190, height = 122)
        self.music_lyric = ttk.Label(self.music_lyric_frame, text = "请先选择播放器", wraplength = 185)
        self.music_lyric.pack(fill = X)

        #设置其他控件(平台默认不选, 让用户自己挑)
        self.music_platform = ttk.Combobox(self.root, values = ["网易云音乐 3.0+", "汽水音乐"],
state = "readonly", width = 23)
        self.music_platform.place(x = 205, y = 227)
        self.start_listen = ttk.Button(self.root, text = "开始监听", bootstyle = "primary-outline",
width = 23)
        self.start_listen.config(state = ttk.DISABLED)
        self.start_listen.place(x = 206, y = 266)
        logging.info("设置UI完成!")

    def setup_menu(self):
        #菜单栏: 目前只有 debug, 以后可以往里加
        menubar = tk.Menu(self.root)
        debug_menu = tk.Menu(menubar, tearoff = 0)
        debug_menu.add_command(label = "日志", command = self.open_log_window)
        debug_menu.add_separator()
        debug_menu.add_command(label = "关于", command = self.open_about_window)
        menubar.add_cascade(label = "debug", menu = debug_menu)
        self.root.config(menu = menubar)

    #日志窗口: 把根 logger 再挂一个 Handler 到界面上
    def open_log_window(self):
        if self.log_window is not None and self.log_window.winfo_exists():
            self.log_window.lift()
            return
        self.log_window = ttk.Toplevel(self.root)
        self.log_window.title("日志")
        self.log_window.geometry("760x420")
        self.log_text = ScrolledText(self.log_window, wrap = "word", font = ("Consolas", 9))
        self.log_text.pack(fill = BOTH, expand = True)
        self.log_handler = WindowLogHandler(self.log_queue)
        self.log_handler.setFormatter(LOG_FORMAT)
        logging.getLogger().addHandler(self.log_handler)
        self.log_window.protocol("WM_DELETE_WINDOW", self.close_log_window)
        self.pump_log()

    def pump_log(self):
        #把队列里的日志刷到控件上
        while not self.log_queue.empty():
            self.log_text.insert(END, self.log_queue.get() + "\n")
            self.log_text.see(END)
        if self.log_handler is not None and self.log_window is not None:
            self.log_window.after(200, self.pump_log)

    def close_log_window(self):
        if self.log_handler is not None:
            logging.getLogger().removeHandler(self.log_handler)
            self.log_handler = None
        self.log_window.destroy()
        self.log_window = None

    #关于窗口: 内嵌的图片 + 版权信息
    def open_about_window(self):
        if self.about_window is not None and self.about_window.winfo_exists():
            self.about_window.lift()
            return
        self.about_window = ttk.Toplevel(self.root)
        self.about_window.title("关于")
        self.about_window.resizable(False, False)

        image_stream = load_about_image()
        if image_stream is not None:
            image = Image.open(image_stream).convert("RGB")
            image.thumbnail((200, 200), resample = Image.Resampling.LANCZOS)
            self.about_image = ImageTk.PhotoImage(image)
            ttk.Label(self.about_window, image = self.about_image).grid(row = 0, column = 0, rowspan = 3,
padx = 14, pady = 14)

        about_lines = ["WMC-Bridge-Plugin By: 晓炎", "©晓炎 2020-2026", "*本插件部分代码使用AIGC"]
        for index, text in enumerate(about_lines):
            ttk.Label(self.about_window, text = text,
font = ("Microsoft YaHei UI", 11 if index == 0 else 9,
"bold" if index == 0 else "normal")).grid(row = index, column = 1, sticky = "w",
padx = (0, 18), pady = 3)

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
