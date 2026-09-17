"""
In-memory and persistent state manager for VimCord server (users, rooms, channels, direct calls).
Integrates with Database (SQLite).
"""

import time
import uuid
from typing import Dict, Optional, Set, Tuple, List, Any
from vimcord.server.db import Database


class User:
    def __init__(self, user_id: str, username: str, tcp_writer=None, avatar_color: str = "#5865F2", status_text: str = "В сети", avatar_image: str = "", bio: str = "", display_name: str = "", banner_color: str = "#5865F2", banner_image: str = ""):
        self.user_id = user_id
        self.username = username
        self.display_name = display_name or username
        self.avatar_color = avatar_color
        self.avatar_image = avatar_image
        self.bio = bio
        self.banner_color = banner_color or "#5865F2"
        self.banner_image = banner_image or ""
        self.status_text = status_text
        self.tcp_writer = tcp_writer
        self.udp_addr: Optional[Tuple[str, int]] = None
        self.current_room_id: Optional[str] = None
        self.current_voice_channel_id: Optional[str] = None
        self.active_call_id: Optional[str] = None
        self.is_muted: bool = False
        self.is_deafened: bool = False
        self.last_seen: float = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "display_name": self.display_name,
            "avatar_color": self.avatar_color,
            "avatar_image": self.avatar_image,
            "bio": self.bio,
            "banner_color": self.banner_color,
            "banner_image": self.banner_image,
            "status_text": self.status_text,
            "current_room_id": self.current_room_id,
            "current_voice_channel_id": self.current_voice_channel_id,
            "in_call": bool(self.active_call_id),
            "is_muted": self.is_muted,
            "is_deafened": self.is_deafened,
            "online": True
        }


class Channel:
    def __init__(self, channel_id: str, name: str, channel_type: str):
        self.channel_id = channel_id
        self.name = name
        self.channel_type = channel_type  # "text" or "voice"
        self.voice_users: Set[str] = set()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "channel_id": self.channel_id,
            "name": self.name,
            "channel_type": self.channel_type,
            "voice_users": list(self.voice_users)
        }


class Room:
    def __init__(self, room_id: str, name: str, owner_id: str):
        self.room_id = room_id
        self.name = name
        self.owner_id = owner_id
        self.channels: Dict[str, Channel] = {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "room_id": self.room_id,
            "name": self.name,
            "owner_id": self.owner_id,
            "channels": [ch.to_dict() for ch in self.channels.values()]
        }


class CallSession:
    def __init__(self, call_id: str, caller_id: str, callee_id: str):
        self.call_id = call_id
        self.caller_id = caller_id
        self.callee_id = callee_id
        self.state = "ringing"  # "ringing", "active", "ended"
        self.started_at: float = time.time()


class ServerState:
    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()
        self.users: Dict[str, User] = {}
        self.udp_addr_to_user_id: Dict[Tuple[str, int], str] = {}
        self.rooms: Dict[str, Room] = {}
        self.calls: Dict[str, CallSession] = {}
        
        # Load rooms and channels from database
        self._load_from_db()

    def _load_from_db(self):
        loaded_rooms = self.db.load_all_rooms_and_channels()
        for r_data in loaded_rooms:
            r = Room(room_id=r_data["room_id"], name=r_data["name"], owner_id=r_data["owner_id"])
            for ch_data in r_data.get("channels", []):
                ch = Channel(
                    channel_id=ch_data["channel_id"],
                    name=ch_data["name"],
                    channel_type=ch_data["channel_type"]
                )
                r.channels[ch.channel_id] = ch
            self.rooms[r.room_id] = r

    def add_user(self, user_id: str, username: str, tcp_writer, avatar_color: str = "#5865F2", status_text: str = "В сети", avatar_image: str = "", bio: str = "", display_name: str = "", banner_color: str = "#5865F2", banner_image: str = "") -> User:
        user = User(
            user_id=user_id,
            username=username,
            tcp_writer=tcp_writer,
            avatar_color=avatar_color,
            status_text=status_text,
            avatar_image=avatar_image,
            bio=bio,
            display_name=display_name,
            banner_color=banner_color,
            banner_image=banner_image
        )
        self.users[user_id] = user
        return user

    def remove_user(self, user_id: str) -> Optional[User]:
        user = self.users.pop(user_id, None)
        if not user:
            return None
        
        if user.udp_addr:
            self.udp_addr_to_user_id.pop(user.udp_addr, None)
            
        self.leave_voice(user_id)
        
        if user.active_call_id:
            self.end_call(user.active_call_id)
            
        return user

    def register_udp(self, user_id: str, ip: str, port: int):
        user = self.users.get(user_id)
        if not user:
            return
        
        if user.udp_addr and user.udp_addr in self.udp_addr_to_user_id:
            del self.udp_addr_to_user_id[user.udp_addr]
            
        user.udp_addr = (ip, port)
        self.udp_addr_to_user_id[(ip, port)] = user_id

    def create_room(self, name: str, owner_id: str) -> Room:
        room_id = "room-" + uuid.uuid4().hex[:8]
        room = Room(room_id=room_id, name=name, owner_id=owner_id)
        
        # Add default text and voice channels
        ch_text_id = "ch-" + uuid.uuid4().hex[:6]
        ch_voice_id = "vch-" + uuid.uuid4().hex[:6]
        
        ch_text = Channel(channel_id=ch_text_id, name="основной", channel_type="text")
        ch_voice = Channel(channel_id=ch_voice_id, name="🔊 Голосовой", channel_type="voice")
        room.channels[ch_text_id] = ch_text
        room.channels[ch_voice_id] = ch_voice
        
        self.rooms[room_id] = room
        
        # Persist in DB
        self.db.save_room(room_id, name, owner_id)
        self.db.save_channel(ch_text_id, room_id, "основной", "text")
        self.db.save_channel(ch_voice_id, room_id, "🔊 Голосовой", "voice")
        
        return room

    def delete_room(self, room_id: str) -> bool:
        if room_id == "room-default":
            return False  # Protect default room
        if room_id in self.rooms:
            room = self.rooms[room_id]
            for ch in room.channels.values():
                for uid in list(ch.voice_users):
                    self.leave_voice(uid)
            del self.rooms[room_id]
            self.db.delete_room(room_id)
            return True
        return False

    def create_channel(self, room_id: str, name: str, channel_type: str) -> Optional[Channel]:
        room = self.rooms.get(room_id)
        if not room:
            return None
        prefix = "vch-" if channel_type == "voice" else "ch-"
        channel_id = prefix + uuid.uuid4().hex[:6]
        channel = Channel(channel_id=channel_id, name=name, channel_type=channel_type)
        room.channels[channel_id] = channel
        
        # Persist in DB
        self.db.save_channel(channel_id, room_id, name, channel_type)
        return channel

    def delete_channel(self, room_id: str, channel_id: str) -> bool:
        room = self.rooms.get(room_id)
        if not room or channel_id not in room.channels:
            return False
        ch = room.channels[channel_id]
        for uid in list(ch.voice_users):
            self.leave_voice(uid)
        del room.channels[channel_id]
        self.db.delete_channel(channel_id)
        return True

    def join_voice(self, user_id: str, room_id: str, channel_id: str) -> Tuple[bool, Optional[Tuple[str, str]]]:
        user = self.users.get(user_id)
        room = self.rooms.get(room_id)
        if not user or not room or channel_id not in room.channels:
            return False, None
        
        channel = room.channels[channel_id]
        if channel.channel_type != "voice":
            return False, None
            
        prev_voice = self.leave_voice(user_id)
        
        channel.voice_users.add(user_id)
        user.current_room_id = room_id
        user.current_voice_channel_id = channel_id
        return True, prev_voice

    def leave_voice(self, user_id: str) -> Optional[Tuple[str, str]]:
        user = self.users.get(user_id)
        if not user or not user.current_voice_channel_id:
            return None
        
        room_id = user.current_room_id
        channel_id = user.current_voice_channel_id
        
        if room_id and room_id in self.rooms:
            room = self.rooms[room_id]
            if channel_id in room.channels:
                room.channels[channel_id].voice_users.discard(user_id)
                
        user.current_voice_channel_id = None
        return room_id, channel_id

    def get_channel_voice_recipients(self, sender_id: str, channel_id: str) -> List[Tuple[str, int]]:
        recipients = []
        for room in self.rooms.values():
            if channel_id in room.channels:
                ch = room.channels[channel_id]
                for uid in ch.voice_users:
                    if uid != sender_id:
                        user = self.users.get(uid)
                        if user and user.udp_addr:
                            recipients.append(user.udp_addr)
                break
        return recipients

    def create_call(self, caller_id: str, callee_id: str) -> Optional[CallSession]:
        caller = self.users.get(caller_id)
        callee = self.users.get(callee_id)
        if not caller or not callee:
            return None
        if caller.active_call_id or callee.active_call_id:
            return None
        
        call_id = "call-" + uuid.uuid4().hex[:8]
        session = CallSession(call_id=call_id, caller_id=caller_id, callee_id=callee_id)
        self.calls[call_id] = session
        caller.active_call_id = call_id
        callee.active_call_id = call_id
        return session

    def accept_call(self, call_id: str) -> Optional[CallSession]:
        session = self.calls.get(call_id)
        if not session or session.state != "ringing":
            return None
        session.state = "active"
        return session

    def end_call(self, call_id: str) -> Optional[CallSession]:
        session = self.calls.pop(call_id, None)
        if not session:
            return None
        
        session.state = "ended"
        caller = self.users.get(session.caller_id)
        if caller and caller.active_call_id == call_id:
            caller.active_call_id = None
            
        callee = self.users.get(session.callee_id)
        if callee and callee.active_call_id == call_id:
            callee.active_call_id = None
            
        return session

    def get_call_peer_udp(self, sender_id: str, call_id: str) -> Optional[Tuple[str, int]]:
        session = self.calls.get(call_id)
        if not session or session.state != "active":
            return None
        peer_id = session.callee_id if sender_id == session.caller_id else session.caller_id
        peer = self.users.get(peer_id)
        if peer and peer.udp_addr:
            return peer.udp_addr
        return None

    def get_all_rooms_dict(self) -> List[Dict[str, Any]]:
        return [room.to_dict() for room in self.rooms.values()]

    def get_all_users_dict(self) -> List[Dict[str, Any]]:
        db_users = self.db.get_all_users()
        user_map = {}
        for du in db_users:
            uid = du["user_id"]
            user_map[uid] = {
                "user_id": uid,
                "username": du["username"],
                "avatar_color": du.get("avatar_color", "#5865F2"),
                "avatar_image": du.get("avatar_image", ""),
                "bio": du.get("bio", ""),
                "status_text": du.get("status_text", "Не в сети"),
                "current_room_id": None,
                "current_voice_channel_id": None,
                "in_call": False,
                "is_muted": False,
                "is_deafened": False,
                "online": False
            }

        # Override with active online user sessions
        for uid, user in self.users.items():
            user_map[uid] = user.to_dict()

        return list(user_map.values())
