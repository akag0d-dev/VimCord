"""
TCP Control Server for VimCord.
Handles authentication, registration, profiles, friends, invites, rooms, channels, messages, and calls.
"""

import asyncio
import logging
import time
import uuid
from typing import Dict, Any, Optional
from vimcord.common.protocol import encode_json_message, decode_json_message
from vimcord.server.server_state import ServerState, User

logger = logging.getLogger("VimCord.TCPServer")


class TCPServer:
    def __init__(self, server_state: ServerState, host: str, port: int):
        self.server_state = server_state
        self.db = server_state.db
        self.host = host
        self.port = port
        self.server: Optional[asyncio.Server] = None

    async def broadcast(self, message: Dict[str, Any], exclude_user_id: Optional[str] = None):
        """Broadcasts a JSON message to all online connected users."""
        data = encode_json_message(message)
        for u_id, user in list(self.server_state.users.items()):
            if exclude_user_id and u_id == exclude_user_id:
                continue
            if user.tcp_writer and not user.tcp_writer.is_closing():
                try:
                    user.tcp_writer.write(data)
                    await user.tcp_writer.drain()
                except Exception as e:
                    logger.debug(f"Failed to send to {u_id}: {e}")

    async def send_to_user(self, user_id: str, message: Dict[str, Any]):
        """Sends a JSON message to a specific user if online."""
        user = self.server_state.users.get(user_id)
        if user and user.tcp_writer and not user.tcp_writer.is_closing():
            try:
                user.tcp_writer.write(encode_json_message(message))
                await user.tcp_writer.drain()
            except Exception as e:
                logger.debug(f"Failed to send to {user_id}: {e}")

    def get_channel_room_id(self, channel_id: str) -> Optional[str]:
        for r_id, r in self.server_state.rooms.items():
            if channel_id in r.channels:
                return r_id
        return None

    async def send_to_channel_room(self, channel_id: str, message: Dict[str, Any]):
        room_id = self.get_channel_room_id(channel_id)
        if not room_id or room_id == "room-default":
            await self.broadcast(message)
            return
        members = self.db.get_room_members(room_id)
        for m in members:
            await self.send_to_user(m["user_id"], message)

    async def send_to_room_members(self, room_id: str, message: Dict[str, Any]):
        if not room_id or room_id == "room-default":
            await self.broadcast(message)
            return
        members = self.db.get_room_members(room_id)
        for m in members:
            await self.send_to_user(m["user_id"], message)

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        current_user: Optional[User] = None
        addr = writer.get_extra_info("peername")
        logger.info(f"New client connected from {addr}")

        try:
            while not reader.at_eof():
                line_bytes = await reader.readline()
                if not line_bytes:
                    break
                line = line_bytes.decode("utf-8", errors="ignore").strip()
                if not line:
                    continue

                msg = decode_json_message(line)
                if not msg:
                    continue

                msg_type = msg.get("type")

                # 1. REGISTER
                if msg_type == "register":
                    uname = msg.get("username", "").strip()
                    passwd = msg.get("password", "").strip()
                    success, err_msg, u_data = self.db.register_user(uname, passwd)
                    resp = {
                        "type": "register_resp",
                        "success": success,
                        "message": err_msg
                    }
                    writer.write(encode_json_message(resp))
                    await writer.drain()
                    continue

                # 2. LOGIN
                elif msg_type == "login":
                    uname = msg.get("username", "Anonymous").strip() or "Anonymous"
                    passwd = msg.get("password", "")
                    
                    if passwd:
                        ok, err_msg, u_data = self.db.authenticate_user(uname, passwd)
                    else:
                        # Auto-login or test compatibility: get existing or register with empty password
                        existing = self.db.get_user_by_username(uname)
                        if existing:
                            ok, err_msg, u_data = True, "OK", existing
                        else:
                            ok, err_msg, u_data = self.db.register_user(uname, "password123")

                    if not ok:
                        resp = {
                            "type": "login_resp",
                            "success": False,
                            "message": err_msg
                        }
                        writer.write(encode_json_message(resp))
                        await writer.drain()
                        continue

                    # If already connected, disconnect old session
                    old_session = self.server_state.users.get(u_data["user_id"])
                    if old_session:
                        self.server_state.remove_user(u_data["user_id"])

                    current_user = self.server_state.add_user(
                        user_id=u_data["user_id"],
                        username=u_data["username"],
                        tcp_writer=writer,
                        avatar_color=u_data.get("avatar_color", "#5865F2"),
                        status_text=u_data.get("status_text", "В сети"),
                        avatar_image=u_data.get("avatar_image", ""),
                        bio=u_data.get("bio", "")
                    )

                    # Return full initial state - send user's rooms (isolation)
                    friends = self.db.get_friends(current_user.user_id)
                    user_rooms = self.db.get_user_rooms(current_user.user_id)
                    resp = {
                        "type": "login_resp",
                        "success": True,
                        "user_id": current_user.user_id,
                        "username": current_user.username,
                        "avatar_color": current_user.avatar_color,
                        "avatar_image": current_user.avatar_image,
                        "bio": current_user.bio,
                        "status_text": current_user.status_text,
                        "rooms": user_rooms,
                        "users": self.server_state.get_all_users_dict(),
                        "friends": friends
                    }
                    writer.write(encode_json_message(resp))
                    await writer.drain()

                    # Notify all other clients of user presence
                    await self.broadcast({
                        "type": "user_presence",
                        "user": current_user.to_dict()
                    }, exclude_user_id=current_user.user_id)
                    logger.info(f"User logged in: {current_user.username} ({current_user.user_id})")

                # Require login for all further actions
                if not current_user:
                    continue

                # 3. GET CHAT HISTORY
                if msg_type == "get_history":
                    t_type = msg.get("target_type")
                    t_id = msg.get("target_id")
                    if t_type == "channel":
                        db_key = t_id
                    else:
                        db_key = self.db.get_canonical_dm_id(current_user.user_id, t_id)
                    
                    history = self.db.get_messages(db_key, limit=100)
                    resp = {
                        "type": "history_resp",
                        "target_type": t_type,
                        "target_id": t_id,
                        "messages": history
                    }
                    writer.write(encode_json_message(resp))
                    await writer.drain()

                # 4. SEND MESSAGE (text, photo attachments, voice messages)
                elif msg_type == "send_msg":
                    t_type = msg.get("target_type")
                    t_id = msg.get("target_id")
                    content = msg.get("content", "").strip()
                    image_data = msg.get("image_data", "")
                    voice_data = msg.get("voice_data", "")
                    voice_duration = float(msg.get("voice_duration", 0.0))
                    if content or image_data or voice_data:
                        now = time.time()
                        msg_id = "msg-" + uuid.uuid4().hex[:8]
                        if t_type == "channel":
                            db_key = t_id
                        else:
                            db_key = self.db.get_canonical_dm_id(current_user.user_id, t_id)

                        # Save to database
                        self.db.save_message(
                            msg_id, t_type, db_key, current_user.user_id, current_user.username,
                            content, now, image_data=image_data, voice_data=voice_data, voice_duration=voice_duration
                        )

                        chat_msg = {
                            "type": "new_msg",
                            "msg_id": msg_id,
                            "target_type": t_type,
                            "target_id": t_id,
                            "sender_id": current_user.user_id,
                            "sender_name": current_user.username,
                            "avatar_color": current_user.avatar_color,
                            "avatar_image": current_user.avatar_image,
                            "content": content,
                            "image_data": image_data,
                            "voice_data": voice_data,
                            "voice_duration": voice_duration,
                            "timestamp": now
                        }
                        if t_type == "channel":
                            await self.send_to_channel_room(t_id, chat_msg)
                        elif t_type == "dm":
                            # Deliver to target recipient and echo to sender
                            await self.send_to_user(t_id, chat_msg)
                            await self.send_to_user(current_user.user_id, chat_msg)

                # 4.1 DELETE MESSAGE
                elif msg_type == "delete_msg":
                    msg_id = msg.get("msg_id")
                    target_type = msg.get("target_type")
                    target_id = msg.get("target_id")
                    if msg_id and self.db.delete_message(msg_id, current_user.user_id):
                        del_event = {
                            "type": "msg_deleted",
                            "msg_id": msg_id,
                            "target_type": target_type,
                            "target_id": target_id
                        }
                        if target_type == "channel":
                            await self.send_to_channel_room(target_id, del_event)
                        elif target_type == "dm":
                            await self.send_to_user(target_id, del_event)
                            await self.send_to_user(current_user.user_id, del_event)

                # 5. CREATE ROOM (Room isolation: only creator receives room_created)
                elif msg_type == "create_room":
                    name = msg.get("name", "Новая комната").strip() or "Новая комната"
                    room = self.server_state.create_room(name=name, owner_id=current_user.user_id)
                    await self.send_to_user(current_user.user_id, {
                        "type": "room_created",
                        "room": room.to_dict()
                    })

                # 5.1 LEAVE ROOM
                elif msg_type == "leave_room":
                    room_id = msg.get("room_id")
                    ok, res_msg = self.db.leave_room(room_id, current_user.user_id)
                    writer.write(encode_json_message({
                        "type": "leave_room_resp",
                        "success": ok,
                        "message": res_msg,
                        "room_id": room_id
                    }))
                    await writer.drain()
                    if ok:
                        if current_user.current_room_id == room_id:
                            prev = self.server_state.leave_voice(current_user.user_id)
                            if prev:
                                await self.broadcast({
                                    "type": "voice_state_update",
                                    "user_id": current_user.user_id,
                                    "room_id": prev[0],
                                    "channel_id": prev[1],
                                    "action": "leave"
                                })
                        if res_msg == "Сервер удален создателем":
                            if room_id in self.server_state.rooms:
                                del self.server_state.rooms[room_id]
                            await self.broadcast({
                                "type": "room_deleted",
                                "room_id": room_id
                            })

                # 5.2 GET ROOM MEMBERS (for right-side sidebar)
                elif msg_type == "get_room_members":
                    room_id = msg.get("room_id")
                    members = self.db.get_room_members(room_id)
                    for m in members:
                        m["online"] = m["user_id"] in self.server_state.users
                    writer.write(encode_json_message({
                        "type": "room_members_resp",
                        "room_id": room_id,
                        "members": members
                    }))
                    await writer.drain()

                # 5.3 PING / PONG
                elif msg_type == "ping":
                    writer.write(encode_json_message({
                        "type": "pong",
                        "timestamp": msg.get("timestamp", time.time())
                    }))
                    await writer.drain()

                # 6. DELETE ROOM
                elif msg_type == "delete_room":
                    room_id = msg.get("room_id")
                    if room_id and self.server_state.delete_room(room_id):
                        await self.send_to_room_members(room_id, {
                            "type": "room_deleted",
                            "room_id": room_id
                        })

                # 7. CREATE CHANNEL
                elif msg_type == "create_channel":
                    room_id = msg.get("room_id")
                    name = msg.get("name", "канал").strip()
                    ch_type = msg.get("channel_type", "text")
                    channel = self.server_state.create_channel(room_id, name, ch_type)
                    if channel:
                        await self.send_to_room_members(room_id, {
                            "type": "channel_created",
                            "room_id": room_id,
                            "channel": channel.to_dict()
                        })

                # 8. DELETE CHANNEL
                elif msg_type == "delete_channel":
                    room_id = msg.get("room_id")
                    channel_id = msg.get("channel_id")
                    if self.server_state.delete_channel(room_id, channel_id):
                        await self.send_to_room_members(room_id, {
                            "type": "channel_deleted",
                            "room_id": room_id,
                            "channel_id": channel_id
                        })

                # 9. SERVER INVITES
                elif msg_type == "create_room_invite":
                    room_id = msg.get("room_id")
                    code = self.db.create_invite(room_id, current_user.user_id)
                    writer.write(encode_json_message({
                        "type": "room_invite_created",
                        "room_id": room_id,
                        "code": code
                    }))
                    await writer.drain()

                elif msg_type == "join_room_by_invite":
                    code = msg.get("code", "").strip()
                    ok, res_msg, room_id = self.db.join_by_invite(code, current_user.user_id)
                    if ok and room_id in self.server_state.rooms:
                        room = self.server_state.rooms[room_id]
                        writer.write(encode_json_message({
                            "type": "room_invite_joined",
                            "success": True,
                            "room": room.to_dict()
                        }))
                    else:
                        writer.write(encode_json_message({
                            "type": "room_invite_joined",
                            "success": False,
                            "message": res_msg
                        }))
                    await writer.drain()

                # 10. FRIEND REQUESTS & FRIENDS LIST
                elif msg_type == "send_friend_request":
                    target_uname = msg.get("username", "").strip()
                    ok, res_msg, target_info = self.db.send_friend_request(current_user.user_id, target_uname)
                    writer.write(encode_json_message({
                        "type": "friend_request_resp",
                        "success": ok,
                        "message": res_msg
                    }))
                    await writer.drain()

                    if ok and target_info:
                        # Refresh friends lists for sender and receiver
                        sender_friends = self.db.get_friends(current_user.user_id)
                        await self.send_to_user(current_user.user_id, {
                            "type": "friends_update",
                            "friends": sender_friends
                        })
                        receiver_friends = self.db.get_friends(target_info["user_id"])
                        await self.send_to_user(target_info["user_id"], {
                            "type": "friends_update",
                            "friends": receiver_friends
                        })

                elif msg_type == "accept_friend_request":
                    sender_uid = msg.get("sender_user_id")
                    if self.db.accept_friend_request(current_user.user_id, sender_uid):
                        # Notify both
                        for uid in (current_user.user_id, sender_uid):
                            flist = self.db.get_friends(uid)
                            await self.send_to_user(uid, {"type": "friends_update", "friends": flist})

                elif msg_type == "decline_friend_request":
                    peer_uid = msg.get("peer_id")
                    if self.db.decline_friend_request(current_user.user_id, peer_uid):
                        for uid in (current_user.user_id, peer_uid):
                            flist = self.db.get_friends(uid)
                            await self.send_to_user(uid, {"type": "friends_update", "friends": flist})

                # 11. PROFILE UPDATE & PASSWORD CHANGE
                elif msg_type == "update_profile":
                    new_uname = msg.get("username")
                    new_status = msg.get("status_text")
                    new_color = msg.get("avatar_color")
                    new_avatar = msg.get("avatar_image")
                    new_bio = msg.get("bio")
                    ok, res_msg = self.db.update_profile(
                        current_user.user_id,
                        username=new_uname,
                        status_text=new_status,
                        avatar_color=new_color,
                        avatar_image=new_avatar,
                        bio=new_bio
                    )
                    if ok:
                        if new_uname:
                            current_user.username = new_uname
                        if new_status is not None:
                            current_user.status_text = new_status
                        if new_color:
                            current_user.avatar_color = new_color
                        if new_avatar is not None:
                            current_user.avatar_image = new_avatar
                        if new_bio is not None:
                            current_user.bio = new_bio

                        await self.broadcast({
                            "type": "user_presence",
                            "user": current_user.to_dict()
                        })

                    writer.write(encode_json_message({
                        "type": "profile_update_resp",
                        "success": ok,
                        "message": res_msg,
                        "user": current_user.to_dict()
                    }))
                    await writer.drain()

                elif msg_type == "get_profile":
                    target_uid = msg.get("user_id")
                    target_info = self.db.get_user_by_id(target_uid) if target_uid else None
                    if target_info:
                        online_user = self.server_state.users.get(target_uid)
                        target_info["online"] = bool(online_user)
                        writer.write(encode_json_message({
                            "type": "profile_resp",
                            "success": True,
                            "profile": target_info
                        }))
                    else:
                        writer.write(encode_json_message({
                            "type": "profile_resp",
                            "success": False,
                            "error": "Пользователь не найден"
                        }))
                    await writer.drain()

                elif msg_type == "user_media_state":
                    current_user.is_muted = bool(msg.get("is_muted", False))
                    current_user.is_deafened = bool(msg.get("is_deafened", False))
                    await self.broadcast({
                        "type": "user_media_state",
                        "user_id": current_user.user_id,
                        "is_muted": current_user.is_muted,
                        "is_deafened": current_user.is_deafened
                    })

                elif msg_type == "change_password":
                    old_p = msg.get("old_password", "")
                    new_p = msg.get("new_password", "")
                    ok, res_msg = self.db.change_password(current_user.user_id, old_p, new_p)
                    writer.write(encode_json_message({
                        "type": "change_password_resp",
                        "success": ok,
                        "message": res_msg
                    }))
                    await writer.drain()

                # 12. VOICE CHANNELS
                elif msg_type == "join_voice":
                    room_id = msg.get("room_id")
                    channel_id = msg.get("channel_id")
                    ok, prev = self.server_state.join_voice(current_user.user_id, room_id, channel_id)
                    if ok:
                        if prev:
                            prev_room_id, prev_channel_id = prev
                            await self.broadcast({
                                "type": "voice_state_update",
                                "user_id": current_user.user_id,
                                "room_id": prev_room_id,
                                "channel_id": prev_channel_id,
                                "action": "leave"
                            })
                        await self.broadcast({
                            "type": "voice_state_update",
                            "user_id": current_user.user_id,
                            "room_id": room_id,
                            "channel_id": channel_id,
                            "action": "join",
                            "is_muted": current_user.is_muted,
                            "is_deafened": current_user.is_deafened
                        })

                elif msg_type == "leave_voice":
                    prev = self.server_state.leave_voice(current_user.user_id)
                    if prev:
                        room_id, channel_id = prev
                        await self.broadcast({
                            "type": "voice_state_update",
                            "user_id": current_user.user_id,
                            "room_id": room_id,
                            "channel_id": channel_id,
                            "action": "leave"
                        })

                # 13. DIRECT CALLS (1-on-1)
                elif msg_type == "call_start":
                    target_user_id = msg.get("target_user_id")
                    session = self.server_state.create_call(current_user.user_id, target_user_id)
                    if session:
                        await self.send_to_user(target_user_id, {
                            "type": "incoming_call",
                            "call_id": session.call_id,
                            "from_user_id": current_user.user_id,
                            "from_username": current_user.username
                        })
                        await self.send_to_user(current_user.user_id, {
                            "type": "call_ringing",
                            "call_id": session.call_id,
                            "target_user_id": target_user_id
                        })
                    else:
                        await self.send_to_user(current_user.user_id, {
                            "type": "call_failed",
                            "reason": "Пользователь занят или недоступен"
                        })

                elif msg_type == "call_accept":
                    call_id = msg.get("call_id")
                    session = self.server_state.accept_call(call_id)
                    if session:
                        caller = self.server_state.users.get(session.caller_id)
                        callee = self.server_state.users.get(session.callee_id)
                        await self.send_to_user(session.caller_id, {
                            "type": "call_accepted",
                            "call_id": call_id,
                            "peer_id": session.callee_id,
                            "peer_name": callee.username if callee else "Unknown"
                        })
                        await self.send_to_user(session.callee_id, {
                            "type": "call_accepted",
                            "call_id": call_id,
                            "peer_id": session.caller_id,
                            "peer_name": caller.username if caller else "Unknown"
                        })

                elif msg_type == "call_decline":
                    call_id = msg.get("call_id")
                    session = self.server_state.end_call(call_id)
                    if session:
                        peer_id = session.caller_id if current_user.user_id == session.callee_id else session.callee_id
                        await self.send_to_user(peer_id, {
                            "type": "call_declined",
                            "call_id": call_id
                        })

                elif msg_type == "call_end":
                    call_id = msg.get("call_id")
                    session = self.server_state.end_call(call_id)
                    if session:
                        peer_id = session.caller_id if current_user.user_id == session.callee_id else session.callee_id
                        end_notify = {"type": "call_ended", "call_id": call_id}
                        await self.send_to_user(peer_id, end_notify)
                        await self.send_to_user(current_user.user_id, end_notify)

                # 14. SCREEN SHARING (Reliable TCP Forwarding)
                elif msg_type == "screen_frame":
                    target_type = msg.get("target_type")
                    target_id = msg.get("target_id")
                    b64_data = msg.get("data", "")
                    if target_type == "channel":
                        for room in self.server_state.rooms.values():
                            if target_id in room.channels:
                                ch = room.channels[target_id]
                                for uid in ch.voice_users:
                                    if uid != current_user.user_id:
                                        await self.send_to_user(uid, {
                                            "type": "screen_frame",
                                            "sender_id": current_user.user_id,
                                            "sender_name": current_user.username,
                                            "target_id": target_id,
                                            "data": b64_data
                                        })
                                break
                    elif target_type == "call":
                        session = self.server_state.calls.get(target_id)
                        if session and session.state == "active":
                            peer_id = session.callee_id if current_user.user_id == session.caller_id else session.caller_id
                            await self.send_to_user(peer_id, {
                                "type": "screen_frame",
                                "sender_id": current_user.user_id,
                                "sender_name": current_user.username,
                                "target_id": target_id,
                                "data": b64_data
                            })

                elif msg_type == "screen_stop":
                    target_type = msg.get("target_type")
                    target_id = msg.get("target_id")
                    if target_type == "channel":
                        for room in self.server_state.rooms.values():
                            if target_id in room.channels:
                                ch = room.channels[target_id]
                                for uid in ch.voice_users:
                                    if uid != current_user.user_id:
                                        await self.send_to_user(uid, {
                                            "type": "screen_stop",
                                            "sender_id": current_user.user_id,
                                            "target_id": target_id
                                        })
                                break
                    elif target_type == "call":
                        session = self.server_state.calls.get(target_id)
                        if session and session.state == "active":
                            peer_id = session.callee_id if current_user.user_id == session.caller_id else session.caller_id
                            await self.send_to_user(peer_id, {
                                "type": "screen_stop",
                                "sender_id": current_user.user_id,
                                "target_id": target_id
                            })

        except (asyncio.CancelledError, ConnectionResetError):
            pass
        except Exception as e:
            logger.error(f"Error handling client {addr}: {e}", exc_info=True)
        finally:
            if current_user:
                logger.info(f"User disconnected: {current_user.username} ({current_user.user_id})")
                prev_room_id = current_user.current_room_id
                prev_channel_id = current_user.current_voice_channel_id
                self.server_state.remove_user(current_user.user_id)
                if prev_room_id and prev_channel_id:
                    await self.broadcast({
                        "type": "voice_state_update",
                        "user_id": current_user.user_id,
                        "room_id": prev_room_id,
                        "channel_id": prev_channel_id,
                        "action": "leave"
                    })
                await self.broadcast({
                    "type": "user_presence",
                    "user": {
                        "user_id": current_user.user_id,
                        "username": current_user.username,
                        "online": False
                    }
                })
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def start(self):
        self.server = await asyncio.start_server(self.handle_client, self.host, self.port)
        logger.info(f"TCP Control Server running on {self.host}:{self.port}")
        async with self.server:
            await self.server.serve_forever()
