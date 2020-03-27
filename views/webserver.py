from uuid import uuid4
import asyncio
from time import time
from isodate import parse_duration
from sqlalchemy import select, insert, update, delete, func
from googleapiclient.discovery import build
from nejma.layers import channel_layer
from nejma.ext.starlette import WebSocketEndpoint
from starlette.websockets import WebSocket
from starlette.types import Receive, Scope, Send
from config import DATABASE, YOUTUBE_KEY
from models import Room, Song, RoomType


YOUTUBE = build('youtube', 'v3', developerKey=YOUTUBE_KEY)
USER_VOTES = {
    'downed': {

    },
    'voted': {

    }
}
ROOMS = {}


class RoomSong():
    def __init__(self, room_id: int, group: str):
        self.room_id = room_id
        self.group = group
        self.playing: Song = None
        self.time = 0
        self.play = True
        self.paused = -1
        self.task: asyncio.Task = None
        self.users = []
    
    def join(self, name: str) -> None:
        self.users.append(name)
    
    def leave(self, name: str) -> None:
        if name in self.users:
            self.users.remove(name)
    
    def get_song(self):
        return self.playing, int(time()) - self.time
    
    def set_task(self, task: asyncio.Task):
        self.task = task
    
    async def stop(self):
        if self.play:
            self.task.cancel()
            self.play = False
            self.paused = int(time()) - self.time
            await internal_channel_propagate(self.group, {'action': 'stop_song'})
    
    def next(self):
        if self.task:
            self.task.cancel()
        self.play = True
        self.paused = -1
        self.set_task(asyncio.create_task(self.start()))
    
    def do_play(self):
        self.play = True
        self.set_task(asyncio.create_task(self.start()))
    
    async def start(self):
        self.play = True
        while self.play:
            query = select([Room]).where(Room.id == self.room_id)
            room = await DATABASE.fetch_one(query)
            songs_query = select([Song]).where(Song.room_id == self.room_id)
            if room.room_type == RoomType.simple:
                songs_query = songs_query.order_by(Song.order)
            elif room.room_type == RoomType.random:
                songs_query = songs_query.order_by(func.random())
            else:
                songs_query = songs_query.order_by(Song.upvotes.desc(), Song.order)
            songs = await DATABASE.fetch_all(songs_query)
            if len(songs):
                to_play = songs[0] if self.paused == -1 else self.playing
                data = YOUTUBE.videos().list(
                    part='contentDetails',
                    id=to_play.url
                )
                content = data.execute()
                if content.get('items', []):
                    duration_iso = content['items'][0].get('contentDetails', {}).get('duration')
                    duration = parse_duration(duration_iso).total_seconds()
                    if self.paused == -1:
                        query = update(Song).where(Song.room_id == to_play.room_id).values(order=Song.order - 1)
                        await DATABASE.execute(query)
                        query = update(Song).where(Song.id == to_play.id).values(
                            upvotes=0,
                            order=len(songs)
                        )
                        await DATABASE.execute(query)
                        for user in USER_VOTES['voted']:
                            if to_play.id in USER_VOTES['voted']:
                                USER_VOTES['voted'][user].remove(to_play.id)
                        await internal_channel_propagate(self.group, {'action': 'refresh_songs'})
                    self.playing = to_play
                    self.time = int(time())
                    await internal_channel_propagate(self.group, {
                        'action': 'play_song',
                        'id': to_play.url,
                        'start': 0 if self.paused == -1 else self.paused
                    })
                    if self.paused != -1:
                        self.time = int(time()) - self.paused
                        duration -= self.paused
                    self.paused = -1
                    await asyncio.sleep(int(duration))
                else:
                    query = delete(Song).where(Song.id == to_play.id)
                    await DATABASE.execute(query)
            else:
                self.play = False


async def internal_channel_propagate(group: str, message: dict):
    for channel in channel_layer.groups.get(group, {}):
        try:
            await channel.send_internal(message)
        except:
            pass
        


class Server(WebSocketEndpoint):
    def __init__(self, scope: Scope, receive: Receive, send: Send):
        super().__init__(scope, receive, send)
        self.user = {}
        self.room = None

    async def on_connect(self, websocket: WebSocket, **kwargs) -> None:
        await super().on_connect(websocket, **kwargs)
        self.channel_layer.expires = 86400 * 31
        self.channel.expires = 86400 * 31
        self.channel.send_internal = self.on_internal_message

    async def on_disconnect(self, websocket: WebSocket, close_code: int):
        await super().on_disconnect(websocket, close_code)
        if self.room:
            ROOMS[self.room.id].leave(self.user['name'])
            self.channel_layer.group_send(self.room_key, {
                'action': 'leave',
                'user': self.user['name']
            })

    async def on_internal_message(self, command: dict) -> None:
        action = f"internal_{command.get('action', '')}"
        if hasattr(self, action):
            func = getattr(self, action)
            await func(command)
    
    async def on_receive(self, websocket: WebSocket, command: dict) -> None:
        action = command.get('action', '')
        if action[:9] == 'internal_':
            return
        if hasattr(self, action):
            func = getattr(self, action)
            await func(command)
    
    async def internal_play_song(self, command: dict) -> None:
        await self.channel.send({
            'action': 'play',
            'id': command['id'],
            'start': command['start']
        })
    
    async def login(self, command: dict) -> None:
        self.user['id'] = command.get('id', str(uuid4()))
        self.user['name'] = command.get('name', 'Anonymous')

        if self.user['id'] is None:
            self.user['id'] = str(uuid4())
        
        if self.user['id'] not in USER_VOTES['downed']:
            USER_VOTES['downed'][self.user['id']] = []
            USER_VOTES['voted'][self.user['id']] = []

        await self.channel.send({
            'action': 'set_id',
            'id': self.user['id']
        })
    
    async def create_room(self, command: dict) -> None:
        room_key = str(f'room{uuid4().hex}')
        room_name = command.get('name', 'Anonymous room')
        query = insert(Room).values(
            key=room_key,
            name=room_name,
            admin=self.user.get('id', 'Error'),
            room_type=RoomType.simple,
            allow_downvote=True,
            downvote_threeshold=3
        )
        await DATABASE.execute(query)
        self.channel_layer.add(room_key, self.channel)
        await self.channel.send({
            'action': 'room_created',
            'key': room_key
        })

    async def join_room(self, command: dict) -> None:
        self.room_key = command.get('room', str(uuid4()))
        query = select([Room]).where(Room.key == self.room_key)
        self.room = await DATABASE.fetch_one(query)
        if self.room.id not in ROOMS:
            ROOMS[self.room.id] = RoomSong(self.room.id, self.room_key)
        self.channel_layer.add(self.room_key, self.channel)
        await self.channel.send({
            'action': 'users',
            'list': ROOMS[self.room.id].users
        })
        ROOMS[self.room.id].join(self.user['name'])
        await self.channel_layer.group_send(self.room_key, {
            'action': 'join',
            'user': self.user['name']
        })
        await self.channel.send({
            'action': 'room_joined',
            'key': self.room_key,
            'name': self.room.name,
            'admin': str(self.user.get('id', 'None')) == self.room.admin,
            'room_type': str(self.room.room_type.name),
            'allow_downvote': self.room.allow_downvote,
            'downvote_threeshold': self.room.downvote_threeshold
        })
        await self.internal_refresh_songs({})
    
    async def internal_stop_song(self, command: dict) -> None:
        await self.channel.send({
            'action': 'stop'
        })
    
    async def refresh(self, command: dict) -> None:
        if ROOMS[self.room.id].playing and ROOMS[self.room.id].paused == -1:
            await self.channel.send({
                'action': 'play',
                'id': ROOMS[self.room.id].playing.url,
                'start': int(time()) - ROOMS[self.room.id].time
            })
    
    async def internal_refresh_songs(self, command: dict) -> None:
        songs_query = select([Song]).where(Song.room_id == self.room.id)
        if self.room.room_type == RoomType.simple:
            songs_query = songs_query.order_by(Song.order)
        elif self.room.room_type == RoomType.random:
            songs_query = songs_query.order_by(func.random())
        else:
            songs_query = songs_query.order_by(Song.upvotes.desc(), Song.order)
        self.songs = await DATABASE.fetch_all(songs_query)
        songs = [{
            'id': song.id,
            'title': song.name,
            'by': song.added_by,
            'upvotes': song.upvotes,
            'voted': song.id in USER_VOTES['voted'][self.user['id']],
            'downed': song.id in USER_VOTES['downed'][self.user['id']],
            'downvotes': song.downvotes,
            'url': song.url
        } for song in self.songs]
        await self.channel.send({
            'action': 'songs_list',
            'songs': songs
        })
    
    async def update_room(self, command: dict) -> None:
        if not self.room or self.room.admin != self.user.get('id', 'None'):
            return
        values = {}
        values['name'] = command.get('name', 'Anonymous room')
        values['allow_downvote'] = command.get('allow_downvote', True)
        values['downvote_threeshold'] = int(command.get('downvote_threeshold', 3))
        room_type = command.get('room_type', 'simple')
        if room_type == 'simple':
            values['room_type'] = RoomType.simple
        elif room_type == 'random':
            values['room_type'] = RoomType.random
        else:
            values['room_type'] = RoomType.fav
        query = update(Room).where(Room.id == self.room.id).values(**values)
        await DATABASE.execute(query)
        await internal_channel_propagate(self.room_key, {'action': 'update_room'})
        await internal_channel_propagate(self.room_key, {'action': 'refresh_songs'})
    
    async def internal_update_room(self, command: dict) -> None:
        query = select([Room]).where(Room.id == self.room.id)
        self.room = await DATABASE.fetch_one(query)
        await self.channel.send({
            'action': 'room_updated',
            'name': self.room.name,
            'room_type': str(self.room.room_type.name),
            'allow_downvote': self.room.allow_downvote,
            'downvote_threeshold': self.room.downvote_threeshold
        })
    
    async def search(self, command: dict) -> None:
        keyword = command.get('keyword', '')
        query = YOUTUBE.search().list(part='snippet', q=keyword, maxResults=50)
        videos = query.execute()
        results = [
            {
                'id': video['id']['videoId'],
                'title': video['snippet']['title'],
                'thumbnail': video['snippet']['thumbnails']['medium']['url'],
            } for video in videos['items'] if video['id']['kind'] == 'youtube#video'
        ]
        await self.channel.send({
            'action': 'search_results',
            'result': results
        })

    async def add_song(self, command: dict) -> None:
        key = command.get('key', '')
        title = command.get('title', '')
        query = insert(Song).values(
            url=key,
            name=title,
            added_by=self.user['name'],
            order=len(self.songs),
            played=-1,
            upvotes=0,
            downvotes=0,
            room_id=self.room.id
        )
        await DATABASE.execute(query)
        await internal_channel_propagate(self.room_key, {'action': 'refresh_songs'})
    
    async def play(self, command: dict) -> None:
        if not self.room or self.room.admin != self.user.get('id', 'None'):
            return
        ROOMS[self.room.id].do_play()
    
    async def stop(self, command: dict) -> None:
        if not self.room or self.room.admin != self.user.get('id', 'None'):
            return
        await ROOMS[self.room.id].stop()
    
    async def skip(self, command: dict) -> None:
        if not self.room or self.room.admin != self.user.get('id', 'None'):
            return
        ROOMS[self.room.id].next()

    async def vote_song(self, command: dict) -> None:
        song_id = command.get('id', -1)
        song = next(song for song in self.songs if song.id == song_id)
        if song:
            if song_id not in USER_VOTES['voted'][self.user['id']]:
                query = update(Song).where(Song.id == song_id).values(upvotes=song.upvotes + 1)
                USER_VOTES['voted'][self.user['id']].append(song_id)
            else:
                query = update(Song).where(Song.id == song_id).values(upvotes=song.upvotes - 1)
                USER_VOTES['voted'][self.user['id']].remove(song_id)
            await DATABASE.execute(query)
            await internal_channel_propagate(self.room_key, {'action': 'refresh_songs'})

    async def downvote_song(self, command: dict) -> None:
        song_id = command.get('id', -1)
        song = next(song for song in self.songs if song.id == song_id)
        if song:
            if song_id not in USER_VOTES['downed'][self.user['id']]:
                query = update(Song).where(Song.id == song_id).values(downvotes=song.downvotes + 1)
                USER_VOTES['downed'][self.user['id']].append(song_id)
                if song.downvotes + 1 >= self.room.downvote_threeshold:
                    query = delete(Song).where(Song.id == song_id)
            else:
                query = update(Song).where(Song.id == song_id).values(downvotes=song.downvotes - 1)
                USER_VOTES['downed'][self.user['id']].remove(song_id)
            await DATABASE.execute(query)
            await internal_channel_propagate(self.room_key, {'action': 'refresh_songs'})

    async def delete_song(self, command: dict) -> None:
        if not self.room or self.room.admin != self.user.get('id', 'None'):
            return
        song_id = command.get('id', -1)
        song = next(song for song in self.songs if song.id == song_id)
        if song:
            query = delete(Song).where(Song.id == song_id)
            await DATABASE.execute(query)
            await internal_channel_propagate(self.room_key, {'action': 'refresh_songs'})

