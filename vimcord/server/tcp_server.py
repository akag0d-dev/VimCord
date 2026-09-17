"""
TCP Control Server for VimCord.
Handles authentication, room/channel CRUD, text messaging, and call signaling.
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
        """Sends a JSON message to a specific user."""
        user = self.server_state.users.get(user_id)
        if user and user.tcp_writer and not user.tcp_writer.is_closing():
            try:
                user.tcp_writer.write(encode_json_message(message))
                await user.tcp_writer.drain()
            except Exception as e:
                logger.debug(f"Failed to send to {user_id}: {e}")

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

                # 1. LOGIN
                if msg_type == "login":
                    username = msg.get("username", "Anonymous").strip() or "Anonymous"
                    current_user = self.server_state.add_user(username=username, tcp_writer=writer)
                    
                    # Respond with login success
                    resp = {
                        "type": "login_resp",
                        "success": True,
                        "user_id": current_user.user_id,
                        "username": current_user.username,
                        "rooms": self.server_state.get_all_rooms_dict(),
                        "users": self.server_state.get_all_users_dict()
                    }
                    writer.write(encode_json_message(resp))
                    await writer.drain()

                    # Notify all other clients of new user
                    await self.broadcast({
                        "type": "user_presence",
                        "user": current_user.to_dict()
                    }, exclude_user_id=current_user.user_id)
                    logger.info(f"User logged in: {current_user.username} ({current_user.user_id})")

                # Require login for subsequent actions
                if not current_user:
                    continue

                # 2. CREATE ROOM
                if msg_type == "create_room":
                    name = msg.get("name", "Новая комната").strip() or "Новая комната"
                    room = self.server_state.create_room(name=name, owner_id=current_user.user_id)
                    await self.broadcast({
                        "type": "room_created",
                        "room": room.to_dict()
                    })

                # 3. DELETE ROOM
                elif msg_type == "delete_room":
                    room_id = msg.get("room_id")
                    if room_id and self.server_state.delete_room(room_id):
                        await self.broadcast({
                            "type": "room_deleted",
                            "room_id": room_id
                        })

                # 4. CREATE CHANNEL
                elif msg_type == "create_channel":
                    room_id = msg.get("room_id")
                    name = msg.get("name", "канал").strip()
                    ch_type = msg.get("channel_type", "text")
                    channel = self.server_state.create_channel(room_id, name, ch_type)
                    if channel:
                        await self.broadcast({
                            "type": "channel_created",
                            "room_id": room_id,
                            "channel": channel.to_dict()
                        })

                # 5. DELETE CHANNEL
                elif msg_type == "delete_channel":
                    room_id = msg.get("room_id")
                    channel_id = msg.get("channel_id")
                    if self.server_state.delete_channel(room_id, channel_id):
                        await self.broadcast({
                            "type": "channel_deleted",
                            "room_id": room_id,
                            "channel_id": channel_id
                        })

                # 6. JOIN VOICE CHANNEL
                elif msg_type == "join_voice":
                    room_id = msg.get("room_id")
                    channel_id = msg.get("channel_id")
                    if self.server_state.join_voice(current_user.user_id, room_id, channel_id):
                        await self.broadcast({
                            "type": "voice_state_update",
                            "user_id": current_user.user_id,
                            "room_id": room_id,
                            "channel_id": channel_id,
                            "action": "join"
                        })

                # 7. LEAVE VOICE CHANNEL
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

                # 8. TEXT CHAT MESSAGE
                elif msg_type == "send_msg":
                    target_type = msg.get("target_type")  # "channel" or "dm"
                    target_id = msg.get("target_id")
                    content = msg.get("content", "").strip()
                    if content:
                        chat_msg = {
                            "type": "new_msg",
                            "msg_id": "msg-" + uuid.uuid4().hex[:8],
                            "target_type": target_type,
                            "target_id": target_id,
                            "sender_id": current_user.user_id,
                            "sender_name": current_user.username,
                            "content": content,
                            "timestamp": time.time()
                        }
                        if target_type == "channel":
                            await self.broadcast(chat_msg)
                        elif target_type == "dm":
                            # Send to callee and echo back to sender
                            await self.send_to_user(target_id, chat_msg)
                            await self.send_to_user(current_user.user_id, chat_msg)

                # 9. DIRECT CALL: START
                elif msg_type == "call_start":
                    target_user_id = msg.get("target_user_id")
                    session = self.server_state.create_call(current_user.user_id, target_user_id)
                    if session:
                        # Send incoming call prompt to target
                        await self.send_to_user(target_user_id, {
                            "type": "incoming_call",
                            "call_id": session.call_id,
                            "from_user_id": current_user.user_id,
                            "from_username": current_user.username
                        })
                        # Send ringing feedback to caller
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

                # 10. DIRECT CALL: ACCEPT
                elif msg_type == "call_accept":
                    call_id = msg.get("call_id")
                    session = self.server_state.accept_call(call_id)
                    if session:
                        caller = self.server_state.users.get(session.caller_id)
                        callee = self.server_state.users.get(session.callee_id)
                        # Notify caller
                        await self.send_to_user(session.caller_id, {
                            "type": "call_accepted",
                            "call_id": call_id,
                            "peer_id": session.callee_id,
                            "peer_name": callee.username if callee else "Unknown"
                        })
                        # Notify callee
                        await self.send_to_user(session.callee_id, {
                            "type": "call_accepted",
                            "call_id": call_id,
                            "peer_id": session.caller_id,
                            "peer_name": caller.username if caller else "Unknown"
                        })

                # 11. DIRECT CALL: DECLINE
                elif msg_type == "call_decline":
                    call_id = msg.get("call_id")
                    session = self.server_state.end_call(call_id)
                    if session:
                        peer_id = session.caller_id if current_user.user_id == session.callee_id else session.callee_id
                        await self.send_to_user(peer_id, {
                            "type": "call_declined",
                            "call_id": call_id
                        })

                # 12. DIRECT CALL: END
                elif msg_type == "call_end":
                    call_id = msg.get("call_id")
                    session = self.server_state.end_call(call_id)
                    if session:
                        peer_id = session.caller_id if current_user.user_id == session.callee_id else session.callee_id
                        end_notify = {"type": "call_ended", "call_id": call_id}
                        await self.send_to_user(peer_id, end_notify)
                        await self.send_to_user(current_user.user_id, end_notify)

        except (asyncio.CancelledError, ConnectionResetError):
            pass
        except Exception as e:
            logger.error(f"Error handling client {addr}: {e}", exc_info=True)
        finally:
            if current_user:
                logger.info(f"User disconnected: {current_user.username} ({current_user.user_id})")
                self.server_state.remove_user(current_user.user_id)
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
