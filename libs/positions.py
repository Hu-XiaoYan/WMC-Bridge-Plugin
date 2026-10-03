"""位置来源: 每个平台一种, 上层只认 position()/duration()/playing()。

- MemoryPosition: 网易云这种内存里有连续变量的, 直接读(带AOB自愈)
- SmtcAnchorPosition: 汽水这种只在事件时给锚点的, 锚点 + 自建时钟
"""

import logging
import time
from datetime import datetime, timezone

class PositionSource():
    def position(self):
        raise NotImplementedError

    def duration(self):
        raise NotImplementedError

    def playing(self):
        raise NotImplementedError

    def title_artist(self):
        return None, None

    def close(self):
        pass

class SmtcAnchorPosition(PositionSource):
    #汽水音乐的 SMTC 只在 拖动/暂停/恢复/换歌 时推一次位置, 而且值很准
    #所以: 拿到锚点后自己按壁钟累加, 暂停时冻结
    def __init__(self, reader, app_id):
        self.reader = reader
        self.app_id = app_id
        self.anchor_position = 0.0
        self.anchor_clock = None
        self.is_playing = False
        self.last_duration = 0.0
        self.last_key = None
        self.last_title = None
        self.last_artist = None
        logging.debug(f"位置来源: SMTC 锚点({app_id})")

    def update(self):
        snapshot = self.reader.snapshot(self.app_id)
        if snapshot is None:
            return False
        was_playing = self.is_playing
        self.is_playing = snapshot["playing"]
        if snapshot["duration"] > 0:
            self.last_duration = snapshot["duration"]
        key = (round(snapshot["position"], 3), snapshot["last_updated"])
        if key != self.last_key:
            self.last_key = key
            self.anchor_position = snapshot["position"]
            #LastUpdatedTime 只在"刚发生"时可信, 太旧的一律当作刚刚
            #(汽水恢复播放时不一定会推新锚点, 拿旧时间当基准会把暂停的时间也累加进去)
            delay = 0.0
            if snapshot["last_updated"] is not None:
                gap = (datetime.now(timezone.utc) - snapshot["last_updated"]).total_seconds()
                if 0 <= gap <= 3.0:
                    delay = gap
            self.anchor_clock = time.monotonic() - delay
            logging.debug(f"新锚点: {self.anchor_position:.3f}s (延迟 {delay*1000:.0f}ms, "
f"时长 {self.last_duration:.1f}s)")
        elif self.is_playing != was_playing and self.anchor_clock is not None:
            #播放/暂停状态变了却没有新位置: 以当前算出来的位置重新起算
            self.anchor_position = self.position()
            self.anchor_clock = time.monotonic()
            logging.debug(f"状态变了({was_playing}->{self.is_playing}), "
f"以 {self.anchor_position:.3f}s 重新锚定")
        return True

    def position(self):
        if self.anchor_clock is None:
            return None
        if not self.is_playing:
            return self.anchor_position
        return self.anchor_position + (time.monotonic() - self.anchor_clock)

    def duration(self):
        return self.last_duration

    def playing(self):
        return self.is_playing

    def title_artist(self):
        return self.last_title, self.last_artist

    def refresh_media_properties(self):
        title, artist = self.reader.media_properties(self.app_id)
        self.last_title, self.last_artist = title, artist
        return title, artist

class MemoryPosition(PositionSource):
    #网易云: 内存里的全局 float64, 靠 AOB 定位(失效时差分扫描自愈)
    def __init__(self, pid, stop_event = None):
        from . import mem
        self.mem = mem
        self.pid = pid
        self.handle = mem.open_player(pid)
        self.address = None
        self.duration = 0.0
        if self.handle:
            base, size, module_path = mem.get_module(self.handle)
            if base is not None:
                address, rva, source = mem.resolve_position(self.handle, base, module_path, stop_event)
                self.address = address
                logging.debug(f"位置来源: 内存 AOB(pid={pid}, 来源={source})")

    def position(self):
        if self.address is None:
            return None
        value = self.mem.read_double(self.handle, self.address)
        if value is None or value < 0:
            return None
        return value

    def duration(self):
        return self.duration

    def playing(self):
        return None

    def close(self):
        if self.handle:
            self.mem.close_player(self.handle)
