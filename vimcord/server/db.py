"""
SQLite database storage for VimCord.
Persists users, passwords, rooms, channels, messages, friendships, and invites.
Zero external dependencies (uses standard library sqlite3).
"""

import hashlib
import os
import secrets
import sqlite3
import time
from typing import Dict, Any, List, Optional, Tuple


from contextlib import contextmanager


class Database:
    def __init__(self, db_path: str = "vimcord_data.db"):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self):
        with self._get_conn() as conn:
            cur = conn.cursor()
            
            # 1. Users table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    status_text TEXT DEFAULT 'В сети',
                    avatar_color TEXT DEFAULT '#5865F2',
                    avatar_image TEXT DEFAULT '',
                    bio TEXT DEFAULT '',
                    created_at REAL NOT NULL
                )
            """)
            try:
                cur.execute("ALTER TABLE users ADD COLUMN avatar_image TEXT DEFAULT ''")
            except Exception:
                pass
            try:
                cur.execute("ALTER TABLE users ADD COLUMN bio TEXT DEFAULT ''")
            except Exception:
                pass
            try:
                cur.execute("ALTER TABLE users ADD COLUMN display_name TEXT DEFAULT ''")
            except Exception:
                pass
            try:
                cur.execute("ALTER TABLE users ADD COLUMN banner_color TEXT DEFAULT '#5865F2'")
            except Exception:
                pass
            try:
                cur.execute("ALTER TABLE users ADD COLUMN banner_image TEXT DEFAULT ''")
            except Exception:
                pass

            # 2. Rooms (Servers) table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS rooms (
                    room_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
            """)

            # 3. Room Members table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS room_members (
                    room_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    joined_at REAL NOT NULL,
                    PRIMARY KEY (room_id, user_id)
                )
            """)

            # 4. Room Invites table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS room_invites (
                    code TEXT PRIMARY KEY,
                    room_id TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
            """)

            # 5. Channels table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS channels (
                    channel_id TEXT PRIMARY KEY,
                    room_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    channel_type TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
            """)

            # 6. Messages table (channels and DMs)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    msg_id TEXT PRIMARY KEY,
                    target_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    sender_id TEXT NOT NULL,
                    sender_name TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    image_data TEXT DEFAULT '',
                    voice_data TEXT DEFAULT '',
                    voice_duration REAL DEFAULT 0.0
                )
            """)
            try:
                cur.execute("ALTER TABLE messages ADD COLUMN image_data TEXT DEFAULT ''")
            except Exception:
                pass
            try:
                cur.execute("ALTER TABLE messages ADD COLUMN voice_data TEXT DEFAULT ''")
            except Exception:
                pass
            try:
                cur.execute("ALTER TABLE messages ADD COLUMN voice_duration REAL DEFAULT 0.0")
            except Exception:
                pass
            try:
                cur.execute("ALTER TABLE messages ADD COLUMN file_data TEXT DEFAULT ''")
            except Exception:
                pass
            try:
                cur.execute("ALTER TABLE messages ADD COLUMN file_name TEXT DEFAULT ''")
            except Exception:
                pass
            try:
                cur.execute("ALTER TABLE messages ADD COLUMN file_size INTEGER DEFAULT 0")
            except Exception:
                pass
            cur.execute("CREATE INDEX IF NOT EXISTS idx_msg_target ON messages(target_id, timestamp)")

            # 7. Friendships table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS friendships (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    friend_id TEXT NOT NULL,
                    status TEXT NOT NULL, -- 'pending' or 'accepted'
                    created_at REAL NOT NULL,
                    UNIQUE(user_id, friend_id)
                )
            """)
            
            conn.commit()

        # Seed default public room if empty
        self._seed_default_room()

    def _seed_default_room(self):
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM rooms WHERE room_id = 'room-default'")
            if cur.fetchone()[0] == 0:
                now = time.time()
                cur.execute(
                    "INSERT INTO rooms (room_id, name, owner_id, created_at) VALUES (?, ?, ?, ?)",
                    ("room-default", "Главный Сервер", "system", now)
                )
                channels = [
                    ("ch-general", "room-default", "общий-чат", "text", now),
                    ("ch-gaming", "room-default", "флудилка", "text", now),
                    ("vch-lobby", "room-default", "🔊 Голосовой 1", "voice", now),
                    ("vch-gaming", "room-default", "🔊 Игровая комната", "voice", now)
                ]
                cur.executemany(
                    "INSERT INTO channels (channel_id, room_id, name, channel_type, created_at) VALUES (?, ?, ?, ?, ?)",
                    channels
                )
                conn.commit()

    # ------------------ Authentication & User Management ------------------

    @staticmethod
    def _hash_password(password: str, salt: str) -> str:
        return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000).hex()

    def register_user(self, username: str, password: str, display_name: Optional[str] = None) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """Registers a new user. Returns (success, message, user_dict)."""
        import re
        username = username.strip()
        if not username or not re.match(r"^[a-zA-Z0-9_-]{2,32}$", username):
            return False, "Username must be 2-32 characters (English letters, digits, '_' or '-' only)", None
        if not password or len(password) < 4:
            return False, "Password must be at least 4 characters", None

        disp_name = (display_name or "").strip() or username

        # Choose a random aesthetic Discord color
        colors = ["#5865F2", "#57F287", "#FEE75C", "#EB459E", "#ED4245", "#9B59B6", "#1ABC9C"]
        avatar_color = secrets.choice(colors)
        salt = secrets.token_hex(16)
        pwd_hash = self._hash_password(password, salt)
        user_id = "u-" + secrets.token_hex(4)
        now = time.time()

        with self._get_conn() as conn:
            cur = conn.cursor()
            try:
                cur.execute(
                    """
                    INSERT INTO users (user_id, username, display_name, password_hash, salt, status_text, avatar_color, banner_color, banner_image, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (user_id, username, disp_name, pwd_hash, salt, "Online", avatar_color, "#5865F2", "", now)
                )
                # Auto add to default room
                cur.execute(
                    "INSERT OR IGNORE INTO room_members (room_id, user_id, joined_at) VALUES ('room-default', ?, ?)",
                    (user_id, now)
                )
                conn.commit()
            except sqlite3.IntegrityError:
                return False, "User with this username already exists", None

        return True, "Registration successful", {
            "user_id": user_id,
            "username": username,
            "display_name": disp_name,
            "status_text": "Online",
            "avatar_color": avatar_color,
            "avatar_image": "",
            "bio": "",
            "banner_color": "#5865F2",
            "banner_image": ""
        }

    def authenticate_user(self, username: str, password: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """Authenticates an existing user."""
        username = username.strip()
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM users WHERE username = ?", (username,))
            row = cur.fetchone()
            if not row:
                return False, "User not found", None

            user_dict = dict(row)
            expected_hash = self._hash_password(password, user_dict["salt"])
            if secrets.compare_digest(expected_hash, user_dict["password_hash"]):
                disp_name = user_dict.get("display_name") or user_dict["username"]
                return True, "Login successful", {
                    "user_id": user_dict["user_id"],
                    "username": user_dict["username"],
                    "display_name": disp_name,
                    "status_text": user_dict.get("status_text", "Online"),
                    "avatar_color": user_dict.get("avatar_color", "#5865F2"),
                    "avatar_image": user_dict.get("avatar_image", ""),
                    "bio": user_dict.get("bio", ""),
                    "banner_color": user_dict.get("banner_color", "#5865F2"),
                    "banner_image": user_dict.get("banner_image", "")
                }
            return False, "Invalid password", None

    def update_profile(self, user_id: str, username: Optional[str] = None, display_name: Optional[str] = None,
                       status_text: Optional[str] = None, avatar_color: Optional[str] = None,
                       avatar_image: Optional[str] = None, bio: Optional[str] = None,
                       banner_color: Optional[str] = None, banner_image: Optional[str] = None) -> Tuple[bool, str]:
        with self._get_conn() as conn:
            cur = conn.cursor()
            updates = []
            params = []
            if username:
                import re
                if not re.match(r"^[a-zA-Z0-9_-]{2,32}$", username.strip()):
                    return False, "Username must be 2-32 characters, English letters, digits, '_' or '-' only."
                updates.append("username = ?")
                params.append(username.strip())
            if display_name is not None:
                updates.append("display_name = ?")
                params.append(display_name.strip())
            if status_text is not None:
                updates.append("status_text = ?")
                params.append(status_text.strip())
            if avatar_color:
                updates.append("avatar_color = ?")
                params.append(avatar_color)
            if avatar_image is not None:
                updates.append("avatar_image = ?")
                params.append(avatar_image)
            if bio is not None:
                updates.append("bio = ?")
                params.append(bio.strip())
            if banner_color:
                updates.append("banner_color = ?")
                params.append(banner_color)
            if banner_image is not None:
                updates.append("banner_image = ?")
                params.append(banner_image)

            if not updates:
                return True, "No changes"

            params.append(user_id)
            try:
                cur.execute(f"UPDATE users SET {', '.join(updates)} WHERE user_id = ?", params)
                conn.commit()
                return True, "Profile updated successfully"
            except sqlite3.IntegrityError:
                return False, "Username is already taken"

    def change_password(self, user_id: str, old_pass: str, new_pass: str) -> Tuple[bool, str]:
        if len(new_pass) < 4:
            return False, "New password must be at least 4 characters"
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT password_hash, salt FROM users WHERE user_id = ?", (user_id,))
            row = cur.fetchone()
            if not row:
                return False, "User not found"

            if not secrets.compare_digest(self._hash_password(old_pass, row["salt"]), row["password_hash"]):
                return False, "Invalid current password"

            new_salt = secrets.token_hex(16)
            new_hash = self._hash_password(new_pass, new_salt)
            cur.execute("UPDATE users SET password_hash = ?, salt = ? WHERE user_id = ?", (new_hash, new_salt, user_id))
            conn.commit()
            return True, "Password changed successfully"

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT user_id, username, COALESCE(NULLIF(display_name, ''), username) as display_name, status_text, avatar_color, avatar_image, bio, COALESCE(banner_color, '#5865F2') as banner_color, COALESCE(banner_image, '') as banner_image FROM users WHERE user_id = ?", (user_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT user_id, username, COALESCE(NULLIF(display_name, ''), username) as display_name, status_text, avatar_color, avatar_image, bio, COALESCE(banner_color, '#5865F2') as banner_color, COALESCE(banner_image, '') as banner_image FROM users WHERE username = ?", (username,))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_all_users(self) -> List[Dict[str, Any]]:
        """Returns all registered users from the database."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT user_id, username, COALESCE(NULLIF(display_name, ''), username) as display_name, status_text, avatar_color, avatar_image, bio, COALESCE(banner_color, '#5865F2') as banner_color, COALESCE(banner_image, '') as banner_image, created_at FROM users ORDER BY username ASC")
            rows = cur.fetchall()
            return [dict(r) for r in rows]

    def delete_user(self, user_id: str) -> bool:
        """Deletes a user and related memberships/friendships from the database."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
            cur.execute("DELETE FROM room_members WHERE user_id = ?", (user_id,))
            cur.execute("DELETE FROM friendships WHERE user_id = ? OR friend_id = ?", (user_id, user_id))
            conn.commit()
            return True

    def admin_set_password(self, user_id: str, new_pass: str) -> bool:
        """Sets a new password for a user without requiring old password (admin tool)."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            salt = secrets.token_hex(16)
            p_hash = self._hash_password(new_pass, salt)
            cur.execute("UPDATE users SET password_hash = ?, salt = ? WHERE user_id = ?", (p_hash, salt, user_id))
            conn.commit()
            return cur.rowcount > 0

    # ------------------ Persistent Messages ------------------

    @staticmethod
    def get_canonical_dm_id(uid1: str, uid2: str) -> str:
        """Computes a canonical target_id for 1-on-1 private messaging."""
        return f"dm:{min(uid1, uid2)}:{max(uid1, uid2)}"

    def save_message(self, msg_id: Optional[str] = None, target_type: str = "channel", target_id: str = "", sender_id: str = "", sender_name: str = "", content: str = "", timestamp: Optional[float] = None, image_data: str = "", voice_data: str = "", voice_duration: float = 0.0, file_data: str = "", file_name: str = "", file_size: int = 0) -> str:
        import uuid
        import time
        if not msg_id:
            msg_id = str(uuid.uuid4())
        if timestamp is None:
            timestamp = time.time()
        if not sender_name and sender_id:
            u = self.get_user_by_id(sender_id)
            if u:
                sender_name = u.get("display_name") or u.get("username", "")
        if target_type == "dm" and sender_id and target_id and not target_id.startswith("dm:"):
            target_id = self.get_canonical_dm_id(sender_id, target_id)

        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT OR REPLACE INTO messages (msg_id, target_type, target_id, sender_id, sender_name, content, timestamp, image_data, voice_data, voice_duration, file_data, file_name, file_size)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (msg_id, target_type, target_id, sender_id, sender_name, content, timestamp, image_data, voice_data, voice_duration, file_data, file_name, file_size)
            )
            conn.commit()
        return msg_id

    def delete_message(self, msg_id: str, user_id: str) -> bool:
        """Deletes a message if sent by user_id."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM messages WHERE msg_id = ? AND sender_id = ?", (msg_id, user_id))
            conn.commit()
            return cur.rowcount > 0

    def get_messages(self, target_id: str, limit: Any = 100, *args, peer_id: Optional[str] = None, **kwargs) -> List[Dict[str, Any]]:
        actual_target = target_id
        actual_limit = 100
        if target_id == "dm":
            user_a = limit if isinstance(limit, str) else (args[0] if args else "")
            if peer_id:
                actual_target = self.get_canonical_dm_id(user_a, peer_id)
            else:
                actual_target = user_a
            actual_limit = args[1] if len(args) > 1 else 100
        else:
            if isinstance(limit, int):
                actual_limit = limit
            if peer_id:
                actual_target = self.get_canonical_dm_id(target_id, peer_id)

        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT m.msg_id, m.target_type, m.target_id, m.sender_id, m.sender_name, m.content, m.timestamp,
                       COALESCE(m.image_data, '') as image_data,
                       COALESCE(m.voice_data, '') as voice_data,
                       COALESCE(m.voice_duration, 0.0) as voice_duration,
                       COALESCE(m.file_data, '') as file_data,
                       COALESCE(m.file_name, '') as file_name,
                       COALESCE(m.file_size, 0) as file_size,
                       COALESCE(u.avatar_color, '#5865F2') as avatar_color,
                       COALESCE(u.avatar_image, '') as avatar_image,
                       COALESCE(NULLIF(u.display_name, ''), m.sender_name) as display_name
                FROM messages m
                LEFT JOIN users u ON m.sender_id = u.user_id
                WHERE m.target_id = ?
                ORDER BY m.timestamp ASC
                LIMIT ?
                """,
                (actual_target, actual_limit)
            )
            return [dict(row) for row in cur.fetchall()]

    # ------------------ Friendships & Requests ------------------

    def send_friend_request(self, from_user_id: str, target_username: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        target = self.get_user_by_username(target_username)
        if not target:
            return False, "Пользователь с таким никнеймом не найден", None
        if target["user_id"] == from_user_id:
            return False, "Нельзя отправить заявку самому себе", None

        to_user_id = target["user_id"]
        with self._get_conn() as conn:
            cur = conn.cursor()
            # Check if friendship or request already exists
            cur.execute(
                "SELECT * FROM friendships WHERE (user_id = ? AND friend_id = ?) OR (user_id = ? AND friend_id = ?)",
                (from_user_id, to_user_id, to_user_id, from_user_id)
            )
            existing = cur.fetchone()
            if existing:
                if existing["status"] == "accepted":
                    return False, "Этот пользователь уже у вас в друзьях", None
                elif existing["user_id"] == from_user_id:
                    return False, "Заявка в друзья уже отправлена", None
                else:
                    # Target had sent a request to us: auto-accept!
                    cur.execute(
                        "UPDATE friendships SET status = 'accepted' WHERE id = ?",
                        (existing["id"],)
                    )
                    conn.commit()
                    return True, "Заявка принята (взаимная)", target

            now = time.time()
            cur.execute(
                "INSERT INTO friendships (user_id, friend_id, status, created_at) VALUES (?, ?, 'pending', ?)",
                (from_user_id, to_user_id, now)
            )
            conn.commit()
            return True, "Заявка в друзья успешно отправлена", target

    def accept_friend_request(self, user_id: str, sender_user_id: str) -> bool:
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE friendships SET status = 'accepted' WHERE user_id = ? AND friend_id = ? AND status = 'pending'",
                (sender_user_id, user_id)
            )
            conn.commit()
            return cur.rowcount > 0

    def decline_friend_request(self, user_id: str, peer_id: str) -> bool:
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM friendships WHERE ((user_id = ? AND friend_id = ?) OR (user_id = ? AND friend_id = ?))",
                (user_id, peer_id, peer_id, user_id)
            )
            conn.commit()
            return cur.rowcount > 0

    def get_friends(self, user_id: str) -> List[Dict[str, Any]]:
        """Returns list of accepted friends and incoming/outgoing pending requests."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT f.user_id, f.friend_id, f.status,
                       u.user_id as peer_id, u.username, COALESCE(NULLIF(u.display_name, ''), u.username) as display_name, u.status_text, u.avatar_color, u.avatar_image, COALESCE(u.banner_color, '#5865F2') as banner_color, COALESCE(u.banner_image, '') as banner_image
                FROM friendships f
                JOIN users u ON (u.user_id = CASE WHEN f.user_id = ? THEN f.friend_id ELSE f.user_id END)
                WHERE f.user_id = ? OR f.friend_id = ?
                """,
                (user_id, user_id, user_id)
            )
            results = []
            for row in cur.fetchall():
                is_incoming = (row["friend_id"] == user_id and row["status"] == "pending")
                is_outgoing = (row["user_id"] == user_id and row["status"] == "pending")
                results.append({
                    "peer_id": row["peer_id"],
                    "username": row["username"],
                    "display_name": row["display_name"],
                    "status_text": row["status_text"],
                    "avatar_color": row["avatar_color"],
                    "avatar_image": row["avatar_image"] or "",
                    "banner_color": row["banner_color"],
                    "banner_image": row["banner_image"] or "",
                    "friendship_status": row["status"],
                    "is_incoming": is_incoming,
                    "is_outgoing": is_outgoing
                })
            return results

    # ------------------ Rooms & Invites ------------------

    def save_room(self, room_id: str, name: str, owner_id: str):
        with self._get_conn() as conn:
            cur = conn.cursor()
            now = time.time()
            cur.execute(
                "INSERT OR REPLACE INTO rooms (room_id, name, owner_id, created_at) VALUES (?, ?, ?, ?)",
                (room_id, name, owner_id, now)
            )
            cur.execute(
                "INSERT OR IGNORE INTO room_members (room_id, user_id, joined_at) VALUES (?, ?, ?)",
                (room_id, owner_id, now)
            )
            conn.commit()

    def delete_room(self, room_id: str) -> bool:
        if room_id == "room-default":
            return False
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM rooms WHERE room_id = ?", (room_id,))
            cur.execute("DELETE FROM channels WHERE room_id = ?", (room_id,))
            cur.execute("DELETE FROM room_members WHERE room_id = ?", (room_id,))
            cur.execute("DELETE FROM room_invites WHERE room_id = ?", (room_id,))
            conn.commit()
            return True

    def save_channel(self, channel_id: str, room_id: str, name: str, channel_type: str):
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT OR REPLACE INTO channels (channel_id, room_id, name, channel_type, created_at) VALUES (?, ?, ?, ?, ?)",
                (channel_id, room_id, name, channel_type, time.time())
            )
            conn.commit()

    def rename_channel(self, channel_id: str, new_name: str) -> bool:
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE channels SET name = ? WHERE channel_id = ?", (new_name, channel_id))
            conn.commit()
            return cur.rowcount > 0

    def delete_channel(self, channel_id: str):
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM channels WHERE channel_id = ?", (channel_id,))
            cur.execute("DELETE FROM messages WHERE target_id = ?", (channel_id,))
            conn.commit()

    def create_invite(self, room_id: str, created_by: str) -> str:
        # Generates short invite code like VC-4A8F
        code = "VC-" + secrets.token_hex(2).upper()
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT OR REPLACE INTO room_invites (code, room_id, created_by, created_at) VALUES (?, ?, ?, ?)",
                (code, room_id, created_by, time.time())
            )
            conn.commit()
        return code

    def join_by_invite(self, code: str, user_id: str) -> Tuple[bool, str, Optional[str]]:
        code = code.strip().upper()
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT room_id FROM room_invites WHERE code = ?", (code,))
            row = cur.fetchone()
            if not row:
                return False, "Неверный или устаревший код приглашения", None
            room_id = row["room_id"]
            cur.execute(
                "INSERT OR IGNORE INTO room_members (room_id, user_id, joined_at) VALUES (?, ?, ?)",
                (room_id, user_id, time.time())
            )
            conn.commit()
            return True, "Успешное присоединение", room_id

    def load_all_rooms_and_channels(self) -> List[Dict[str, Any]]:
        """Loads all rooms and their channels from DB."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM rooms ORDER BY created_at ASC")
            rooms = []
            for r in cur.fetchall():
                r_dict = dict(r)
                cur.execute("SELECT * FROM channels WHERE room_id = ? ORDER BY created_at ASC", (r["room_id"],))
                r_dict["channels"] = [dict(c) for c in cur.fetchall()]
                rooms.append(r_dict)
            return rooms

    def get_user_rooms(self, user_id: str) -> List[Dict[str, Any]]:
        """Loads only rooms where user is a member/owner, or the default public room."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT DISTINCT r.* FROM rooms r
                LEFT JOIN room_members rm ON r.room_id = rm.room_id
                WHERE r.room_id = 'room-default' OR rm.user_id = ? OR r.owner_id = ?
                ORDER BY r.created_at ASC
                """,
                (user_id, user_id)
            )
            rooms = []
            for r in cur.fetchall():
                r_dict = dict(r)
                cur.execute("SELECT * FROM channels WHERE room_id = ? ORDER BY created_at ASC", (r["room_id"],))
                r_dict["channels"] = [dict(c) for c in cur.fetchall()]
                rooms.append(r_dict)
            return rooms

    def leave_room(self, room_id: str, user_id: str) -> Tuple[bool, str]:
        """User leaves a room. If user is owner, the room is deleted."""
        if room_id == "room-default":
            return False, "Нельзя покинуть главный сервер"
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT owner_id FROM rooms WHERE room_id = ?", (room_id,))
            row = cur.fetchone()
            if not row:
                return False, "Сервер не найден"
            if row["owner_id"] == user_id:
                self.delete_room(room_id)
                return True, "Сервер удален создателем"
            else:
                cur.execute("DELETE FROM room_members WHERE room_id = ? AND user_id = ?", (room_id, user_id))
                conn.commit()
                return True, "Вы покинули сервер"

    def get_room_members(self, room_id: str) -> List[Dict[str, Any]]:
        """Returns list of members belonging to room_id."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            if room_id == "room-default":
                cur.execute("SELECT user_id, username, COALESCE(NULLIF(display_name, ''), username) as display_name, status_text, avatar_color, avatar_image, bio, COALESCE(banner_color, '#5865F2') as banner_color, COALESCE(banner_image, '') as banner_image FROM users")
                return [dict(row) for row in cur.fetchall()]
            cur.execute(
                """
                SELECT u.user_id, u.username, COALESCE(NULLIF(u.display_name, ''), u.username) as display_name, u.status_text, u.avatar_color, u.avatar_image, u.bio, COALESCE(u.banner_color, '#5865F2') as banner_color, COALESCE(u.banner_image, '') as banner_image
                FROM room_members rm
                JOIN users u ON rm.user_id = u.user_id
                WHERE rm.room_id = ?
                """,
                (room_id,)
            )
            return [dict(row) for row in cur.fetchall()]

