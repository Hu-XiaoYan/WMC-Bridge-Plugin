import asyncio
import logging
import os
from datetime import timedelta

from winrt.windows.media import (MediaPlaybackStatus, MediaPlaybackType,
SystemMediaTransportControlsTimelineProperties)
from winrt.windows.media.playback import MediaPlayer
from winrt.windows.storage.streams import (DataWriter, InMemoryRandomAccessStream,
RandomAccessStreamReference)

class SmtcPublisher():
    #我们自己的媒体会话: 网易云那个残缺会话(SMTC 关掉的话连会话都没有)由这里补全
    #关键: 属性+缩略图只在换歌时推一次, 时间线走 update_timeline_properties 单独推
    #这样图片流不会被动, 消费端(Tuna)也就不会反复去读封面
    def __init__(self):
        self.player = MediaPlayer()
        self.smtc = self.player.system_media_transport_controls
        self.updater = self.smtc.display_updater
        self.timeline = SystemMediaTransportControlsTimelineProperties()
        self.hold = []              #保住流和引用, 否则缩略图会失效
        self.last_song = None
        self.last_status = None

        self.player.command_manager.is_enabled = False      #不抢媒体键
        self.smtc.is_enabled = True
        self.smtc.is_play_enabled = True
        self.smtc.is_pause_enabled = True
        self.smtc.is_next_enabled = False
        self.smtc.is_previous_enabled = False
        self.updater.type = MediaPlaybackType.MUSIC
        logging.info("SMTC 会话已建立")

    def set_active(self, active):
        #停止监听时把会话关掉, 免得一直占着媒体面板
        self.smtc.is_enabled = active
        self.smtc.is_play_enabled = active
        self.smtc.is_pause_enabled = active
        if not active:
            self.smtc.playback_status = MediaPlaybackStatus.CLOSED

    async def build_thumbnail(self, image_path):
        with open(image_path, "rb") as f:
            image_data = f.read()
        stream = InMemoryRandomAccessStream()
        writer = DataWriter(stream)
        writer.write_bytes(image_data)
        await writer.store_async()
        await stream.flush_async()
        stream.seek(0)                      #不 seek 的话消费端读不到缩略图
        self.hold = [stream, writer]
        return RandomAccessStreamReference.create_from_stream(stream)

    def set_song(self, song_name, song_artist, image_path = None):
        self.updater.music_properties.title = song_name
        self.updater.music_properties.artist = song_artist
        if image_path and os.path.exists(image_path):
            try:
                self.updater.thumbnail = asyncio.run(self.build_thumbnail(image_path))
            except Exception as err:
                logging.error(f"设置SMTC缩略图失败! {err}")
        self.updater.update()               #整包只推这一次
        self.last_song = f"{song_name}-{song_artist}"
        logging.debug(f"SMTC 歌曲信息已更新: {self.last_song}")

    def set_timeline(self, position, duration):
        if duration and duration > 0:
            self.timeline.end_time = timedelta(seconds = duration)
            self.timeline.max_seek_time = timedelta(seconds = duration)
        self.timeline.start_time = timedelta(seconds = 0)
        self.timeline.min_seek_time = timedelta(seconds = 0)
        self.timeline.position = timedelta(seconds = max(0.0, position))
        self.smtc.update_timeline_properties(self.timeline)     #只动时间线

    def set_playing(self, playing):
        status = MediaPlaybackStatus.PLAYING if playing else MediaPlaybackStatus.PAUSED
        if status != self.last_status:
            self.smtc.playback_status = status
            self.last_status = status
