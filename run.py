import logging
import threading
import time
from queue import Queue

from libs.logger import setup_colored_log
setup_colored_log()

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from libs.watchdog import watchdog_task
from libs.listener import listener_task
from libs.sodalistener import listener_task as soda_listener_task
from libs.smtc import SmtcPublisher
from ui.window import MainWindow

#平台配置: 候选窗口 + 用哪个监听实现(位置来源/歌词来源都在各自实现里)
platform_dict = {
    "网易云音乐 3.0+": {"window": [("OrpheusBrowserHost", None)], "listener": listener_task},
    "汽水音乐": {"window": [("Chrome_WidgetWin_1", "汽水音乐")], "listener": soda_listener_task},
}

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
        self.ui.music_platform.bind("<<ComboboxSelected>>", self.on_platform_change)
        #启动watchdog
        self.start_watchdog()
        #进入主窗口循环
        self.main_window_loop()

    def set_sub_thread(self):
        self.watchdog_queue = Queue()
        self.watchdog_thread = None
        self.watchdog_stop = threading.Event()
        self.watchdog_platform = None
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

    def current_profile(self):
        #没选平台就是 None, 由调用方决定怎么办
        return platform_dict.get(self.ui.music_platform.get())

    def start_watchdog(self, restart = False):
        profile = self.current_profile()
        if profile is None:
            logging.warning("还没选择播放器, 不启动 Watchdog")
            return
        try:
            if restart and self.watchdog_thread is not None:
                self.watchdog_stop.set()
                self.watchdog_thread.join(timeout = 1)
            self.watchdog_stop = threading.Event()
            target_platform = self.ui.music_platform.get()
            matchers = profile["window"]
            self.watchdog_platform = target_platform
            self.watchdog_thread = threading.Thread(target = watchdog_task,
args = (self.watchdog_queue, target_platform, matchers, self.watchdog_stop))
            self.watchdog_thread.daemon = True
            self.watchdog_thread.start()
            logging.debug(f"Watchdog 顺利启动! 目标平台: {target_platform}")
        except Exception as err:
            logging.critical(f"Watchdog 无法启动! 错误信息: {err}")

    def ensure_watchdog(self):
        #换了平台就得换 watchdog, 否则它还在找上一个播放器的窗口; 没选平台就把它停掉
        target_platform = self.ui.music_platform.get()
        if self.current_profile() is None:
            if self.watchdog_thread is not None and self.watchdog_thread.is_alive():
                self.watchdog_stop.set()
                self.watchdog_thread.join(timeout = 1)
            self.watchdog_thread = None
            self.watchdog_platform = None
            self.player_pid = None
            while not self.watchdog_queue.empty():
                self.watchdog_queue.get()
            return
        if (self.watchdog_platform == target_platform and self.watchdog_thread is not None
and self.watchdog_thread.is_alive()):
            return
        logging.debug(f"平台切到 {target_platform}, 重启 Watchdog")
        while not self.watchdog_queue.empty():
            self.watchdog_queue.get()
        self.player_pid = None
        self.start_watchdog(restart = True)

    def drain_watchdog(self):
        #把队列里最后一条播放器状态吃掉, 返回有没有 pid
        latest = None
        while not self.watchdog_queue.empty():
            latest = self.watchdog_queue.get()
        if latest is None:
            return self.player_pid
        if latest["status"]:
            self.player_pid = latest["pid"]
        else:
            self.player_pid = None
        return self.player_pid

    def main_window_loop(self):
        logging.info("进入主窗口循环!")
        def update():
            if not self.watchdog_queue.empty():
                #只认最新一条, 免得切换平台时吃到旧消息
                player_data = {"status": self.drain_watchdog() is not None,
"pid": self.player_pid}
                #监测音乐播放器进程状态
                if player_data["status"]:
                    pid_changed = self.player_pid != player_data["pid"]
                    self.player_pid = player_data["pid"]
                    if self.is_listener_running() and pid_changed:
                        #播放器重启了, 跟着新pid重新监听, 别把界面擦掉
                        logging.debug(f"播放器进程变了(新pid={self.player_pid}), 重新开始监听")
                        self.stop_listener()
                        self.start_listener()
                    elif not self.is_listener_running():
                        self.ui.now_playing_song.config(text = "当前播放歌曲:未开始监听")
                        self.ui.now_play_progress.config(text = "当前播放进度:未开始监听")
                        self.ui.music_lyric.config(text = "未开始监听")
                        self.ui.music_cover.config(image = "", text = "未获取到封面")
                    self.ui.start_listen.config(state = ttk.NORMAL)
                else:
                    if self.is_listener_running():
                        self.stop_listener()
                        self.ui.start_listen.config(text = "开始监听")
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
                    if listener_data["cover_path"]:
                        self.ui.set_cover(listener_data["cover_path"])
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
                        self.smtc.set_song(listener_data["song_name"], listener_data["song_artist"],
listener_data["cover_path"])
                    self.smtc.set_timeline(*listener_data["progress_seconds"])
                    self.smtc.set_playing(listener_data["playing"])

            #开始定时循环, 250ms一次
            self.root.after(250, update)
        self.root.after(250, update)

    def is_listener_running(self):
        return self.listener_thread is not None and self.listener_thread.is_alive()

    def start_listener(self):
        #先保证 watchdog 盯的是当前选的平台, 再等它报一次 pid
        if self.current_profile() is None:
            logging.warning("还没选择播放器, 不能开始监听")
            self.ui.now_playing_song.config(text = "当前播放歌曲:请先选择播放器")
            return False
        self.ensure_watchdog()
        if self.player_pid is None:
            deadline = time.time() + 2
            while time.time() < deadline and self.player_pid is None:
                self.root.update()          #保持界面不假死
                self.drain_watchdog()
                time.sleep(0.05)
        if self.player_pid is None:
            logging.warning("还没检测到播放器, 不能开始监听")
            self.ui.now_playing_song.config(text = "当前播放歌曲:未检测到播放器")
            return False
        if not self.is_listener_running():
            self.stop_listener_event.clear()
            if self.smtc:
                self.smtc.set_active(True)
            target = self.current_profile()["listener"]
            self.listener_thread = threading.Thread(target = target,
args = (self.stop_listener_event, self.listener_queue, self.player_pid))
            self.listener_thread.daemon = True
            self.listener_thread.start()
            logging.debug("Listener 顺利启动!")
        return True

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
        elif self.start_listener():
            self.ui.start_listen.config(text = "停止监听")

    def on_platform_change(self, event = None):
        #换平台就把监听停掉、watchdog 换过去、界面状态复位
        self.stop_listener()
        self.ui.start_listen.config(text = "开始监听")
        self.ensure_watchdog()
        if self.current_profile() is None:
            #没选平台: 回到初始状态并禁用按钮
            self.ui.now_playing_song.config(text = "当前播放歌曲:请先选择播放器")
            self.ui.now_play_progress.config(text = "当前播放进度:请先选择播放器")
            self.ui.music_lyric.config(text = "请先选择播放器")
            self.ui.music_cover.config(image = "", text = "未获取到封面")
            self.ui.start_listen.config(state = ttk.DISABLED)
            return
        self.ui.now_playing_song.config(text = "当前播放歌曲:未开始监听")
        self.ui.now_play_progress.config(text = "当前播放进度:未开始监听")
        self.ui.music_lyric.config(text = "未开始监听")
        self.ui.music_cover.config(image = "", text = "未获取到封面")
        self.ui.start_listen.config(state = ttk.NORMAL)

    def on_exit(self):
        #由于子进程皆为守护线程, 因此窗口关闭时可不用手动终结线程
        self.root.destroy()

if __name__=="__main__":
    app=MainApp()
    app.root.mainloop()
