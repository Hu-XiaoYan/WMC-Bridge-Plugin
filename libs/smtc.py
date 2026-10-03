import asyncio
import logging
import os
from datetime import timedelta

from winrt.windows.media import (MediaPlaybackStatus, MediaPlaybackType,
SystemMediaTransportControlsTimelineProperties)
from winrt.windows.media.control import \
GlobalSystemMediaTransportControlsSessionManager, \
GlobalSystemMediaTransportControlsSessionPlaybackStatus
from winrt.windows.media.playback import MediaPlayer
from winrt.windows.storage.streams import (DataWriter, InMemoryRandomAccessStream,
RandomAccessStreamReference)

class SmtcReader():
    #读取别人的媒体会话(汽水音乐的元数据/状态都在这里, 只有位置得我们自己算)
    def __init__(self):
        self.manager = asyncio.run(self.get_manager())
        self.sessions = {}

    async def get_manager(self):
        return await GlobalSystemMediaTransportControlsSessionManager.request_async()

    def find_session(self, app_id):
        for session in self.manager.get_sessions():
            if app_id in session.source_app_user_model_id:
                return session
        return None

    def snapshot(self, app_id):
        #返回 {position, duration, playing, last_updated} 或 None
        session = self.sessions.get(app_id)
        if session is None:
            session = self.find_session(app_id)
            if session is None:
                return None
            self.sessions[app_id] = session
        try:
            timeline = session.get_timeline_properties()
            playback = session.get_playback_info()
        except Exception as err:
            logging.debug(f"读会话失败, 重新查找: {err}")
            self.sessions.pop(app_id, None)
            return None
        last_updated = timeline.last_updated_time
        if last_updated is not None and last_updated.year < 2000:
            last_updated = None                  #1601 之类的没意义
        #注意: 这是会话的 playback_status, 枚举和 MediaPlaybackStatus 不是一回事
        #(会话的 PLAYING=4, 而 windows.media 的 PLAYING=3, 比错了会永远判定没在播)
        session_status = playback.playback_status
        return {"position": timeline.position.total_seconds(),
"duration": timeline.end_time.total_seconds(),
"playing": session_status == GlobalSystemMediaTransportControlsSessionPlaybackStatus.PLAYING,
"last_updated": last_updated}

    def media_properties(self, app_id):
        #标题/艺术家要异步取, 换歌时才用得上
        session = self.sessions.get(app_id) or self.find_session(app_id)
        if session is None:
            return None, None
        self.sessions[app_id] = session
        try:
            properties = asyncio.run(self.fetch_properties(session))
        except Exception as err:
            logging.debug(f"取媒体属性失败: {err}")
            return None, None
        return properties.title, properties.artist

    async def fetch_properties(self, session):
        #asyncio.run 只接受协程, WinRT 的异步对象得先 await 一层
        return await session.try_get_media_properties_async()

    def thumbnail_bytes(self, app_id):
        #把会话的封面读成字节(汽水的封面只在这个流里, 没有URL)
        session = self.sessions.get(app_id) or self.find_session(app_id)
        if session is None:
            return None
        self.sessions[app_id] = session
        try:
            properties = asyncio.run(self.fetch_properties(session))
            if properties.thumbnail is None:
                return None
            return asyncio.run(self.read_stream(properties.thumbnail))
        except Exception as err:
            logging.debug(f"读取封面失败: {err}")
            return None

    async def read_stream(self, reference):
        from winrt.windows.storage.streams import DataReader
        stream = await reference.open_read_async()
        size = stream.size
        if not size:
            return None
        reader = DataReader(stream.get_input_stream_at(0))
        await reader.load_async(size)
        #PyWinRT 把 ReadBytes 投影成"传入可写缓冲区就地填充", 返回值是 None
        buffer = bytearray(size)
        reader.read_bytes(buffer)
        return bytes(buffer)

class SmtcPublisher():
    #我们自己的媒体会话
    #属性+缩略图只在换歌时推一次, 时间线走 update_timeline_properties 单独推
    def __init__(self):
        self.player = MediaPlayer()
        self.smtc = self.player.system_media_transport_controls
        self.updater = self.smtc.display_updater
        self.timeline = SystemMediaTransportControlsTimelineProperties()
        self.hold = []              #保住流和引用, 否则缩略图会失效
        self.last_song = None
        self.last_status = None

        self.player.command_manager.is_enabled = False
        #不抢媒体键, 我们本身并不参与操控媒体, 只是作为桥插件使用
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
        stream.seek(0)
        #不seek的话消费端读不到缩略图
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
        self.updater.update()
        #整包只推这一次
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
