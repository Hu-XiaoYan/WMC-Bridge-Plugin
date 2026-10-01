import logging
import threading
from queue import Queue

from libs.logger import setup_colored_log
setup_colored_log()

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from libs.watchdog import watchdog_task
from libs.listener import listener_task
from libs.smtc import SmtcPublisher
from ui.window import MainWindow

#平台与候选窗口的对应关系: [(窗口类名, 标题关键字), ...]
#网易云 3.0+ 是 CEF 外壳, 用类名就能认; 将来若换外壳, 在这里加一条(类名, 标题关键字)即可
platform_dict = {"网易云音乐 3.0+": [("OrpheusBrowserHost", None)],
                 "酷狗音乐-暂未支持": [("TXGuiFoundation", None)]}

class MainApp():
    def __init__(self):
        #初始化窗口及窗口退出动作
        self.ui = MainWindow()
        self.root = self.ui.root
        self.root.protocol("WM_DELETE_WINDOW", self.on_exit)
        #初始化子线程队列及线程句柄
        self.set_sub_thread()
        #建立我们自己的SMTC会话
        self.start_smtc()
        #初始化界面按钮回调
        self.ui.start_listen.config(command = self.toggle_listener)
        #启动watchdog
        self.start_watchdog()
        #进入主窗口循环
        self.main_window_loop()

    def set_sub_thread(self):
        self.watchdog_queue = Queue()
        self.watchdog_thread = None
        self.player_pid = None
        self.listener_queue = Queue()
        self.listener_thread = None
        self.stop_listener_event = threading.Event()

    def start_smtc(self):
        try:
            self.smtc = SmtcPublisher()
        except Exception as err:
            self.smtc = None
            logging.error(f"SMTC 会话建立失败, 只输出文本文件! 错误信息: {err}")

    def start_watchdog(self):
        try:
            target_platform = self.ui.music_platform.get()
            #认不出的平台就按网易云的候选列表找, 不让它把watchdog搞挂
            matchers = platform_dict.get(target_platform, platform_dict["网易云音乐 3.0+"])
            self.watchdog_thread = threading.Thread(target = watchdog_task,
args = (self.watchdog_queue, target_platform, matchers))
            self.watchdog_thread.daemon = True
            self.watchdog_thread.start()
            logging.debug("Watchdog 顺利启动!")
        except Exception as err:
            logging.critical(f"Watchdog 无法启动! 错误信息: {err}")

    def main_window_loop(self):
        logging.info("进入主窗口循环!")
        def update():
            if not self.watchdog_queue.empty():
                player_data = self.watchdog_queue.get()
                #监测音乐播放器进程状态
                if player_data["status"]:
                    self.player_pid = player_data["pid"]
                    self.ui.now_playing_song.config(text = "当前播放歌曲:未开始监听")
                    self.ui.now_play_progress.config(text = "当前播放进度:未开始监听")
                    self.ui.music_lyric.config(text = "未开始监听")
                    self.ui.music_cover.config(image = "", text = "未获取到封面")
                    self.ui.start_listen.config(state = ttk.NORMAL)
                else:
                    self.player_pid = None
                    self.ui.now_playing_song.config(text = "当前播放歌曲:未开启音乐软件")
                    self.ui.now_play_progress.config(text = "当前播放进度:未开启音乐软件")
                    self.ui.music_lyric.config(text = "未开启音乐软件")
                    self.ui.music_cover.config(image = "", text = "未开启音乐软件")
                    self.ui.start_listen.config(state = ttk.DISABLED)

            if not self.listener_queue.empty():
                #只保留最新的一帧, 顺便把"换过歌"这个标记带上
                listener_data = None
                song_changed = False
                while not self.listener_queue.empty():
                    listener_data = self.listener_queue.get()
                    song_changed = song_changed or listener_data["status"]
                listener_data["status"] = song_changed
                #刷新播放歌曲/进度
                self.ui.now_playing_song.config(text = f"当前播放歌曲:{listener_data['song_name']}")
                self.ui.now_play_progress.config(text =
f"当前播放进度:{listener_data['play_progress'][0]} / {listener_data['play_progress'][1]}")
                #换歌时刷新封面
                if listener_data["status"]:
                    if listener_data["cover_ready"]:
                        self.ui.set_cover(f"./data/pic/{listener_data['song_id']}.jpg")
                    else:
                        self.ui.music_cover.config(image = "", text = "未获取到封面")
                #刷新歌词
                if listener_data["lyric"] is None:
                    self.ui.music_lyric.config(text = "暂未获取到歌词")
                elif listener_data["trans_lyric"]:
                    self.ui.music_lyric.config(text =
f"{listener_data['lyric']}\n{listener_data['trans_lyric']}")
                else:
                    self.ui.music_lyric.config(text = listener_data["lyric"])
                #发布到我们自己的SMTC会话: 换歌才推属性+封面, 时间线每轮单独推
                if self.smtc:
                    if listener_data["status"]:
                        cover_path = (f"./data/pic/{listener_data['song_id']}.jpg"
if listener_data["cover_ready"] else None)
                        self.smtc.set_song(listener_data["song_name"], listener_data["song_artist"],
cover_path)
                    self.smtc.set_timeline(*listener_data["progress_seconds"])
                    self.smtc.set_playing(listener_data["playing"])

            #开始定时循环, 250ms一次
            self.root.after(250, update)
        self.root.after(250, update)

    def is_listener_running(self):
        return self.listener_thread is not None and self.listener_thread.is_alive()

    def start_listener(self):
        if self.player_pid is None:
            logging.warning("还没检测到播放器, 不能开始监听")
            return
        if not self.is_listener_running():
            self.stop_listener_event.clear()
            if self.smtc:
                self.smtc.set_active(True)
            self.listener_thread = threading.Thread(target = listener_task,
args = (self.stop_listener_event, self.listener_queue, self.player_pid))
            self.listener_thread.daemon = True
            self.listener_thread.start()
            logging.debug("Listener 顺利启动!")

    def stop_listener(self):
        if self.is_listener_running():
            self.stop_listener_event.set()
            self.listener_thread.join(timeout = 2)
            self.listener_thread = None
        if self.smtc:
            self.smtc.set_active(False)
        logging.debug("Listener 顺利退出!")

    def toggle_listener(self):
        if self.is_listener_running():
            self.stop_listener()
            self.ui.start_listen.config(text = "开始监听")
        else:
            self.start_listener()
            self.ui.start_listen.config(text = "停止监听")

    def on_exit(self):
        #由于子进程皆为守护线程, 因此窗口关闭时可不用手动终结线程
        self.root.destroy()

if __name__=="__main__":
    app=MainApp()
    app.root.mainloop()
