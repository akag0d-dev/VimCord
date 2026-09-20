use std::sync::{Arc, Mutex};
use std::time::{SystemTime, UNIX_EPOCH};
use hmac::Hmac;
use rand::Rng;
use rusqlite::{params, Connection, OptionalExtension};
use serde::{Deserialize, Serialize};
use sha2::Sha256;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UserRow {
    pub user_id: String,
    pub username: String,
    pub display_name: String,
    pub status_text: String,
    pub avatar_color: String,
    pub avatar_image: String,
    pub bio: String,
    pub banner_color: String,
    pub banner_image: String,
    #[serde(default)]
    pub created_at: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChannelRow {
    pub channel_id: String,
    pub room_id: String,
    pub name: String,
    pub channel_type: String,
    pub created_at: f64,
    #[serde(default)]
    pub voice_users: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RoomRow {
    pub room_id: String,
    pub name: String,
    pub owner_id: String,
    pub created_at: f64,
    #[serde(default)]
    pub channels: Vec<ChannelRow>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MessageRow {
    pub msg_id: String,
    pub target_type: String,
    pub target_id: String,
    pub sender_id: String,
    pub sender_name: String,
    pub content: String,
    pub timestamp: f64,
    pub image_data: String,
    pub voice_data: String,
    pub voice_duration: f64,
    pub file_data: String,
    pub file_name: String,
    pub file_size: i64,
    pub avatar_color: String,
    pub avatar_image: String,
    pub display_name: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FriendRow {
    pub peer_id: String,
    pub username: String,
    pub display_name: String,
    pub status_text: String,
    pub avatar_color: String,
    pub avatar_image: String,
    pub banner_color: String,
    pub banner_image: String,
    pub friendship_status: String,
    pub is_incoming: bool,
    pub is_outgoing: bool,
}

pub struct Database {
    conn: Arc<Mutex<Connection>>,
}

impl Database {
    pub fn new(db_path: &str) -> Result<Self, rusqlite::Error> {
        let conn = Connection::open(db_path)?;
        conn.execute_batch(
            "PRAGMA journal_mode = WAL;
             PRAGMA synchronous = NORMAL;
             PRAGMA foreign_keys = ON;"
        )?;

        let db = Self {
            conn: Arc::new(Mutex::new(conn)),
        };
        db.init_schema()?;
        db.seed_default_room()?;
        Ok(db)
    }

    fn init_schema(&self) -> Result<(), rusqlite::Error> {
        let conn = self.conn.lock().unwrap();

        conn.execute_batch(
            "CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                status_text TEXT DEFAULT 'В сети',
                avatar_color TEXT DEFAULT '#5865F2',
                avatar_image TEXT DEFAULT '',
                bio TEXT DEFAULT '',
                created_at REAL NOT NULL,
                display_name TEXT DEFAULT '',
                banner_color TEXT DEFAULT '#5865F2',
                banner_image TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS rooms (
                room_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                owner_id TEXT NOT NULL,
                created_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS room_members (
                room_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                joined_at REAL NOT NULL,
                PRIMARY KEY (room_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS room_invites (
                code TEXT PRIMARY KEY,
                room_id TEXT NOT NULL,
                created_by TEXT NOT NULL,
                created_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS channels (
                channel_id TEXT PRIMARY KEY,
                room_id TEXT NOT NULL,
                name TEXT NOT NULL,
                channel_type TEXT NOT NULL,
                created_at REAL NOT NULL
            );

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
                voice_duration REAL DEFAULT 0.0,
                file_data TEXT DEFAULT '',
                file_name TEXT DEFAULT '',
                file_size INTEGER DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_msg_target ON messages(target_id, timestamp);

            CREATE TABLE IF NOT EXISTS friendships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                friend_id TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at REAL NOT NULL,
                UNIQUE(user_id, friend_id)
            );"
        )?;

        // Ensure columns exist on older databases
        let _ = conn.execute("ALTER TABLE users ADD COLUMN avatar_image TEXT DEFAULT ''", []);
        let _ = conn.execute("ALTER TABLE users ADD COLUMN bio TEXT DEFAULT ''", []);
        let _ = conn.execute("ALTER TABLE users ADD COLUMN display_name TEXT DEFAULT ''", []);
        let _ = conn.execute("ALTER TABLE users ADD COLUMN banner_color TEXT DEFAULT '#5865F2'", []);
        let _ = conn.execute("ALTER TABLE users ADD COLUMN banner_image TEXT DEFAULT ''", []);

        let _ = conn.execute("ALTER TABLE messages ADD COLUMN image_data TEXT DEFAULT ''", []);
        let _ = conn.execute("ALTER TABLE messages ADD COLUMN voice_data TEXT DEFAULT ''", []);
        let _ = conn.execute("ALTER TABLE messages ADD COLUMN voice_duration REAL DEFAULT 0.0", []);
        let _ = conn.execute("ALTER TABLE messages ADD COLUMN file_data TEXT DEFAULT ''", []);
        let _ = conn.execute("ALTER TABLE messages ADD COLUMN file_name TEXT DEFAULT ''", []);
        let _ = conn.execute("ALTER TABLE messages ADD COLUMN file_size INTEGER DEFAULT 0", []);

        Ok(())
    }

    fn seed_default_room(&self) -> Result<(), rusqlite::Error> {
        let conn = self.conn.lock().unwrap();
        let count: i64 = conn.query_row(
            "SELECT COUNT(*) FROM rooms WHERE room_id = 'room-default'",
            [],
            |r| r.get(0),
        )?;

        if count == 0 {
            let now = current_time_secs();
            conn.execute(
                "INSERT INTO rooms (room_id, name, owner_id, created_at) VALUES (?, ?, ?, ?)",
                params!["room-default", "Главный Сервер", "system", now],
            )?;

            let channels = [
                ("ch-general", "room-default", "общий-чат", "text"),
                ("ch-gaming", "room-default", "флудилка", "text"),
                ("vch-lobby", "room-default", "🔊 Голосовой 1", "voice"),
                ("vch-gaming", "room-default", "🔊 Игровая комната", "voice"),
            ];

            for (cid, rid, name, ctype) in channels {
                conn.execute(
                    "INSERT INTO channels (channel_id, room_id, name, channel_type, created_at) VALUES (?, ?, ?, ?, ?)",
                    params![cid, rid, name, ctype, now],
                )?;
            }
        }
        Ok(())
    }

    // ------------------ Authentication & Password Hashing ------------------

    pub fn hash_password(password: &str, salt: &str) -> String {
        let mut key = [0u8; 32];
        let _ = pbkdf2::pbkdf2::<Hmac<Sha256>>(password.as_bytes(), salt.as_bytes(), 100_000, &mut key);
        hex::encode(key)
    }

    pub fn register_user(
        &self,
        username: &str,
        password: &str,
        display_name: Option<&str>,
    ) -> Result<UserRow, String> {
        let uname = username.trim();
        if uname.len() < 2 || uname.len() > 32 {
            return Err("Username must be 2-32 characters".to_string());
        }
        if !uname.chars().all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-') {
            return Err("Username must contain only English letters, digits, '_' or '-'".to_string());
        }
        if password.len() < 4 {
            return Err("Password must be at least 4 characters".to_string());
        }

        let disp_name = match display_name {
            Some(d) if !d.trim().is_empty() => d.trim().to_string(),
            _ => uname.to_string(),
        };

        let colors = ["#5865F2", "#57F287", "#FEE75C", "#EB459E", "#ED4245", "#9B59B6", "#1ABC9C"];
        let mut rng = rand::thread_rng();
        let avatar_color = colors[rng.gen_range(0..colors.len())].to_string();

        let mut salt_bytes = [0u8; 16];
        rng.fill(&mut salt_bytes);
        let salt = hex::encode(salt_bytes);
        let pwd_hash = Self::hash_password(password, &salt);

        let mut uid_bytes = [0u8; 4];
        rng.fill(&mut uid_bytes);
        let user_id = format!("u-{}", hex::encode(uid_bytes));
        let now = current_time_secs();

        let conn = self.conn.lock().unwrap();
        let res = conn.execute(
            "INSERT INTO users (user_id, username, display_name, password_hash, salt, status_text, avatar_color, banner_color, banner_image, created_at)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            params![user_id, uname, disp_name, pwd_hash, salt, "Online", avatar_color, "#5865F2", "", now],
        );

        match res {
            Ok(_) => {
                let _ = conn.execute(
                    "INSERT OR IGNORE INTO room_members (room_id, user_id, joined_at) VALUES ('room-default', ?, ?)",
                    params![user_id, now],
                );

                Ok(UserRow {
                    user_id,
                    username: uname.to_string(),
                    display_name: disp_name,
                    status_text: "Online".to_string(),
                    avatar_color,
                    avatar_image: String::new(),
                    bio: String::new(),
                    banner_color: "#5865F2".to_string(),
                    banner_image: String::new(),
                    created_at: now,
                })
            }
            Err(rusqlite::Error::SqliteFailure(e, _)) if e.extended_code == 2067 || e.extended_code == 1555 => {
                Err("User with this username already exists".to_string())
            }
            Err(e) => Err(format!("Database error: {}", e)),
        }
    }

    pub fn authenticate_user(&self, username: &str, password: &str) -> Result<UserRow, String> {
        let uname = username.trim();
        let conn = self.conn.lock().unwrap();

        let row = conn.query_row(
            "SELECT user_id, username, COALESCE(NULLIF(display_name, ''), username) as display_name,
                    password_hash, salt, status_text, avatar_color, avatar_image, bio,
                    COALESCE(banner_color, '#5865F2') as banner_color, COALESCE(banner_image, '') as banner_image, created_at
             FROM users WHERE username = ?",
            params![uname],
            |r| {
                Ok((
                    r.get::<_, String>(0)?,
                    r.get::<_, String>(1)?,
                    r.get::<_, String>(2)?,
                    r.get::<_, String>(3)?,
                    r.get::<_, String>(4)?,
                    r.get::<_, String>(5)?,
                    r.get::<_, String>(6)?,
                    r.get::<_, String>(7)?,
                    r.get::<_, String>(8)?,
                    r.get::<_, String>(9)?,
                    r.get::<_, String>(10)?,
                    r.get::<_, f64>(11)?,
                ))
            },
        ).optional().map_err(|e| e.to_string())?;

        match row {
            Some((uid, un, dn, hash, salt, st, ac, ai, bio, bc, bi, cr)) => {
                let computed = Self::hash_password(password, &salt);
                if computed == hash {
                    Ok(UserRow {
                        user_id: uid,
                        username: un,
                        display_name: dn,
                        status_text: st,
                        avatar_color: ac,
                        avatar_image: ai,
                        bio,
                        banner_color: bc,
                        banner_image: bi,
                        created_at: cr,
                    })
                } else {
                    Err("Invalid password".to_string())
                }
            }
            None => Err("User not found".to_string()),
        }
    }

    pub fn update_profile(
        &self,
        user_id: &str,
        username: Option<&str>,
        display_name: Option<&str>,
        status_text: Option<&str>,
        avatar_color: Option<&str>,
        avatar_image: Option<&str>,
        bio: Option<&str>,
        banner_color: Option<&str>,
        banner_image: Option<&str>,
    ) -> Result<(), String> {
        let conn = self.conn.lock().unwrap();
        let mut updates = Vec::new();
        let mut params: Vec<Box<dyn rusqlite::ToSql>> = Vec::new();

        if let Some(u) = username {
            let u_clean = u.trim();
            if u_clean.len() < 2 || u_clean.len() > 32 {
                return Err("Username must be 2-32 characters".to_string());
            }
            updates.push("username = ?");
            params.push(Box::new(u_clean.to_string()));
        }
        if let Some(d) = display_name {
            updates.push("display_name = ?");
            params.push(Box::new(d.trim().to_string()));
        }
        if let Some(s) = status_text {
            updates.push("status_text = ?");
            params.push(Box::new(s.trim().to_string()));
        }
        if let Some(ac) = avatar_color {
            updates.push("avatar_color = ?");
            params.push(Box::new(ac.to_string()));
        }
        if let Some(ai) = avatar_image {
            updates.push("avatar_image = ?");
            params.push(Box::new(ai.to_string()));
        }
        if let Some(b) = bio {
            updates.push("bio = ?");
            params.push(Box::new(b.trim().to_string()));
        }
        if let Some(bc) = banner_color {
            updates.push("banner_color = ?");
            params.push(Box::new(bc.to_string()));
        }
        if let Some(bi) = banner_image {
            updates.push("banner_image = ?");
            params.push(Box::new(bi.to_string()));
        }

        if updates.is_empty() {
            return Ok(());
        }

        params.push(Box::new(user_id.to_string()));
        let sql = format!("UPDATE users SET {} WHERE user_id = ?", updates.join(", "));
        let param_refs: Vec<&dyn rusqlite::ToSql> = params.iter().map(|b| b.as_ref()).collect();

        conn.execute(&sql, rusqlite::params_from_iter(param_refs))
            .map_err(|e| {
                if let rusqlite::Error::SqliteFailure(err, _) = &e {
                    if err.extended_code == 2067 || err.extended_code == 1555 {
                        return "Username is already taken".to_string();
                    }
                }
                e.to_string()
            })?;
        Ok(())
    }

    pub fn change_password(&self, user_id: &str, old_pass: &str, new_pass: &str) -> Result<(), String> {
        if new_pass.len() < 4 {
            return Err("New password must be at least 4 characters".to_string());
        }
        let conn = self.conn.lock().unwrap();

        let row: Option<(String, String)> = conn
            .query_row(
                "SELECT password_hash, salt FROM users WHERE user_id = ?",
                params![user_id],
                |r| Ok((r.get(0)?, r.get(1)?)),
            )
            .optional()
            .map_err(|e| e.to_string())?;

        let (hash, salt) = row.ok_or_else(|| "User not found".to_string())?;
        if Self::hash_password(old_pass, &salt) != hash {
            return Err("Invalid current password".to_string());
        }

        let mut rng = rand::thread_rng();
        let mut salt_bytes = [0u8; 16];
        rng.fill(&mut salt_bytes);
        let new_salt = hex::encode(salt_bytes);
        let new_hash = Self::hash_password(new_pass, &new_salt);

        conn.execute(
            "UPDATE users SET password_hash = ?, salt = ? WHERE user_id = ?",
            params![new_hash, new_salt, user_id],
        ).map_err(|e| e.to_string())?;

        Ok(())
    }

    pub fn admin_set_password(&self, user_id: &str, new_pass: &str) -> Result<bool, String> {
        let conn = self.conn.lock().unwrap();
        let mut rng = rand::thread_rng();
        let mut salt_bytes = [0u8; 16];
        rng.fill(&mut salt_bytes);
        let salt = hex::encode(salt_bytes);
        let p_hash = Self::hash_password(new_pass, &salt);

        let rows = conn
            .execute(
                "UPDATE users SET password_hash = ?, salt = ? WHERE user_id = ?",
                params![p_hash, salt, user_id],
            )
            .map_err(|e| e.to_string())?;

        Ok(rows > 0)
    }

    pub fn get_user_by_id(&self, user_id: &str) -> Option<UserRow> {
        let conn = self.conn.lock().unwrap();
        conn.query_row(
            "SELECT user_id, username, COALESCE(NULLIF(display_name, ''), username) as display_name,
                    status_text, avatar_color, avatar_image, bio,
                    COALESCE(banner_color, '#5865F2') as banner_color, COALESCE(banner_image, '') as banner_image, created_at
             FROM users WHERE user_id = ?",
            params![user_id],
            |r| {
                Ok(UserRow {
                    user_id: r.get(0)?,
                    username: r.get(1)?,
                    display_name: r.get(2)?,
                    status_text: r.get(3)?,
                    avatar_color: r.get(4)?,
                    avatar_image: r.get(5)?,
                    bio: r.get(6)?,
                    banner_color: r.get(7)?,
                    banner_image: r.get(8)?,
                    created_at: r.get(9)?,
                })
            },
        ).optional().ok().flatten()
    }

    pub fn get_user_by_username(&self, username: &str) -> Option<UserRow> {
        let conn = self.conn.lock().unwrap();
        conn.query_row(
            "SELECT user_id, username, COALESCE(NULLIF(display_name, ''), username) as display_name,
                    status_text, avatar_color, avatar_image, bio,
                    COALESCE(banner_color, '#5865F2') as banner_color, COALESCE(banner_image, '') as banner_image, created_at
             FROM users WHERE username = ?",
            params![username.trim()],
            |r| {
                Ok(UserRow {
                    user_id: r.get(0)?,
                    username: r.get(1)?,
                    display_name: r.get(2)?,
                    status_text: r.get(3)?,
                    avatar_color: r.get(4)?,
                    avatar_image: r.get(5)?,
                    bio: r.get(6)?,
                    banner_color: r.get(7)?,
                    banner_image: r.get(8)?,
                    created_at: r.get(9)?,
                })
            },
        ).optional().ok().flatten()
    }

    pub fn get_all_users(&self) -> Vec<UserRow> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = match conn.prepare(
            "SELECT user_id, username, COALESCE(NULLIF(display_name, ''), username) as display_name,
                    status_text, avatar_color, avatar_image, bio,
                    COALESCE(banner_color, '#5865F2') as banner_color, COALESCE(banner_image, '') as banner_image, created_at
             FROM users ORDER BY username ASC"
        ) {
            Ok(s) => s,
            Err(_) => return Vec::new(),
        };

        let iter = stmt.query_map([], |r| {
            Ok(UserRow {
                user_id: r.get(0)?,
                username: r.get(1)?,
                display_name: r.get(2)?,
                status_text: r.get(3)?,
                avatar_color: r.get(4)?,
                avatar_image: r.get(5)?,
                bio: r.get(6)?,
                banner_color: r.get(7)?,
                banner_image: r.get(8)?,
                created_at: r.get(9)?,
            })
        });

        match iter {
            Ok(rows) => rows.filter_map(|r| r.ok()).collect(),
            Err(_) => Vec::new(),
        }
    }

    pub fn delete_user(&self, user_id: &str) -> bool {
        let conn = self.conn.lock().unwrap();
        let _ = conn.execute("DELETE FROM users WHERE user_id = ?", params![user_id]);
        let _ = conn.execute("DELETE FROM room_members WHERE user_id = ?", params![user_id]);
        let _ = conn.execute("DELETE FROM friendships WHERE user_id = ? OR friend_id = ?", params![user_id, user_id]);
        true
    }

    // ------------------ Messages ------------------

    pub fn get_canonical_dm_id(uid1: &str, uid2: &str) -> String {
        crate::protocol::get_dm_chat_key(uid1, uid2)
    }

    pub fn save_message(
        &self,
        msg_id: Option<String>,
        target_type: &str,
        target_id: &str,
        sender_id: &str,
        sender_name: &str,
        content: &str,
        timestamp: Option<f64>,
        image_data: &str,
        voice_data: &str,
        voice_duration: f64,
        file_data: &str,
        file_name: &str,
        file_size: i64,
    ) -> String {
        let mid = msg_id.unwrap_or_else(|| format!("msg-{}", uuid::Uuid::new_v4().simple()));
        let ts = timestamp.unwrap_or_else(current_time_secs);

        let final_target_id = if target_type == "dm" && !target_id.starts_with("dm:") {
            Self::get_canonical_dm_id(sender_id, target_id)
        } else {
            target_id.to_string()
        };

        let conn = self.conn.lock().unwrap();
        let _ = conn.execute(
            "INSERT OR REPLACE INTO messages (
                msg_id, target_type, target_id, sender_id, sender_name,
                content, timestamp, image_data, voice_data, voice_duration,
                file_data, file_name, file_size
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            params![
                mid, target_type, final_target_id, sender_id, sender_name,
                content, ts, image_data, voice_data, voice_duration,
                file_data, file_name, file_size
            ],
        );
        mid
    }

    pub fn delete_message(&self, msg_id: &str, user_id: &str) -> bool {
        let conn = self.conn.lock().unwrap();
        match conn.execute("DELETE FROM messages WHERE msg_id = ? AND sender_id = ?", params![msg_id, user_id]) {
            Ok(n) => n > 0,
            Err(_) => false,
        }
    }

    pub fn get_messages(&self, target_id: &str, limit: i64) -> Vec<MessageRow> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = match conn.prepare(
            "SELECT m.msg_id, m.target_type, m.target_id, m.sender_id, m.sender_name, m.content, m.timestamp,
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
             LIMIT ?"
        ) {
            Ok(s) => s,
            Err(_) => return Vec::new(),
        };

        let iter = stmt.query_map(params![target_id, limit], |r| {
            Ok(MessageRow {
                msg_id: r.get(0)?,
                target_type: r.get(1)?,
                target_id: r.get(2)?,
                sender_id: r.get(3)?,
                sender_name: r.get(4)?,
                content: r.get(5)?,
                timestamp: r.get(6)?,
                image_data: r.get(7)?,
                voice_data: r.get(8)?,
                voice_duration: r.get(9)?,
                file_data: r.get(10)?,
                file_name: r.get(11)?,
                file_size: r.get(12)?,
                avatar_color: r.get(13)?,
                avatar_image: r.get(14)?,
                display_name: r.get(15)?,
            })
        });

        match iter {
            Ok(rows) => rows.filter_map(|r| r.ok()).collect(),
            Err(_) => Vec::new(),
        }
    }

    // ------------------ Friendships ------------------

    pub fn send_friend_request(&self, from_user_id: &str, target_username: &str) -> (bool, String, Option<UserRow>) {
        let target = match self.get_user_by_username(target_username) {
            Some(u) => u,
            None => return (false, "Пользователь с таким никнеймом не найден".to_string(), None),
        };
        if target.user_id == from_user_id {
            return (false, "Нельзя отправить заявку самому себе".to_string(), None);
        }

        let to_user_id = &target.user_id;
        let conn = self.conn.lock().unwrap();

        let existing: Option<(i64, String, String)> = conn
            .query_row(
                "SELECT id, user_id, status FROM friendships WHERE (user_id = ? AND friend_id = ?) OR (user_id = ? AND friend_id = ?)",
                params![from_user_id, to_user_id, to_user_id, from_user_id],
                |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?)),
            )
            .optional()
            .unwrap_or(None);

        if let Some((fid, uid, status)) = existing {
            if status == "accepted" {
                return (false, "Этот пользователь уже у вас в друзьях".to_string(), None);
            } else if uid == from_user_id {
                return (false, "Заявка в друзья уже отправлена".to_string(), None);
            } else {
                // Auto accept mutual request
                let _ = conn.execute("UPDATE friendships SET status = 'accepted' WHERE id = ?", params![fid]);
                return (true, "Заявка принята (взаимная)".to_string(), Some(target));
            }
        }

        let now = current_time_secs();
        let _ = conn.execute(
            "INSERT INTO friendships (user_id, friend_id, status, created_at) VALUES (?, ?, 'pending', ?)",
            params![from_user_id, to_user_id, now],
        );
        (true, "Заявка в друзья успешно отправлена".to_string(), Some(target))
    }

    pub fn accept_friend_request(&self, user_id: &str, sender_user_id: &str) -> bool {
        let conn = self.conn.lock().unwrap();
        match conn.execute(
            "UPDATE friendships SET status = 'accepted' WHERE user_id = ? AND friend_id = ? AND status = 'pending'",
            params![sender_user_id, user_id],
        ) {
            Ok(n) => n > 0,
            Err(_) => false,
        }
    }

    pub fn decline_friend_request(&self, user_id: &str, peer_id: &str) -> bool {
        let conn = self.conn.lock().unwrap();
        match conn.execute(
            "DELETE FROM friendships WHERE ((user_id = ? AND friend_id = ?) OR (user_id = ? AND friend_id = ?))",
            params![user_id, peer_id, peer_id, user_id],
        ) {
            Ok(n) => n > 0,
            Err(_) => false,
        }
    }

    pub fn is_friend(&self, user_a: &str, user_b: &str) -> bool {
        if user_a.is_empty() || user_b.is_empty() || user_a == user_b {
            return false;
        }
        let conn = self.conn.lock().unwrap();
        let count: i64 = conn.query_row(
            "SELECT COUNT(*) FROM friendships
             WHERE ((user_id = ? AND friend_id = ?) OR (user_id = ? AND friend_id = ?))
               AND status = 'accepted'",
            params![user_a, user_b, user_b, user_a],
            |r| r.get(0),
        ).unwrap_or(0);
        count > 0
    }

    pub fn get_friends(&self, user_id: &str) -> Vec<FriendRow> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = match conn.prepare(
            "SELECT f.user_id, f.friend_id, f.status,
                    u.user_id as peer_id, u.username, COALESCE(NULLIF(u.display_name, ''), u.username) as display_name,
                    u.status_text, u.avatar_color, u.avatar_image,
                    COALESCE(u.banner_color, '#5865F2') as banner_color, COALESCE(u.banner_image, '') as banner_image
             FROM friendships f
             JOIN users u ON (u.user_id = CASE WHEN f.user_id = ? THEN f.friend_id ELSE f.user_id END)
             WHERE f.user_id = ? OR f.friend_id = ?"
        ) {
            Ok(s) => s,
            Err(_) => return Vec::new(),
        };

        let iter = stmt.query_map(params![user_id, user_id, user_id], |r| {
            let u_id: String = r.get(0)?;
            let f_id: String = r.get(1)?;
            let status: String = r.get(2)?;
            let peer_id: String = r.get(3)?;
            let username: String = r.get(4)?;
            let display_name: String = r.get(5)?;
            let status_text: String = r.get(6)?;
            let avatar_color: String = r.get(7)?;
            let avatar_image: String = r.get(8)?;
            let banner_color: String = r.get(9)?;
            let banner_image: String = r.get(10)?;

            let is_incoming = f_id == user_id && status == "pending";
            let is_outgoing = u_id == user_id && status == "pending";

            Ok(FriendRow {
                peer_id,
                username,
                display_name,
                status_text,
                avatar_color,
                avatar_image,
                banner_color,
                banner_image,
                friendship_status: status,
                is_incoming,
                is_outgoing,
            })
        });

        match iter {
            Ok(rows) => rows.filter_map(|r| r.ok()).collect(),
            Err(_) => Vec::new(),
        }
    }

    // ------------------ Rooms & Channels ------------------

    pub fn save_room(&self, room_id: &str, name: &str, owner_id: &str) {
        let conn = self.conn.lock().unwrap();
        let now = current_time_secs();
        let _ = conn.execute(
            "INSERT OR REPLACE INTO rooms (room_id, name, owner_id, created_at) VALUES (?, ?, ?, ?)",
            params![room_id, name, owner_id, now],
        );
        let _ = conn.execute(
            "INSERT OR IGNORE INTO room_members (room_id, user_id, joined_at) VALUES (?, ?, ?)",
            params![room_id, owner_id, now],
        );
    }

    pub fn delete_room(&self, room_id: &str) -> bool {
        if room_id == "room-default" {
            return false;
        }
        let conn = self.conn.lock().unwrap();
        let _ = conn.execute("DELETE FROM rooms WHERE room_id = ?", params![room_id]);
        let _ = conn.execute("DELETE FROM channels WHERE room_id = ?", params![room_id]);
        let _ = conn.execute("DELETE FROM room_members WHERE room_id = ?", params![room_id]);
        let _ = conn.execute("DELETE FROM room_invites WHERE room_id = ?", params![room_id]);
        true
    }

    pub fn save_channel(&self, channel_id: &str, room_id: &str, name: &str, channel_type: &str) {
        let conn = self.conn.lock().unwrap();
        let now = current_time_secs();
        let _ = conn.execute(
            "INSERT OR REPLACE INTO channels (channel_id, room_id, name, channel_type, created_at) VALUES (?, ?, ?, ?, ?)",
            params![channel_id, room_id, name, channel_type, now],
        );
    }

    pub fn rename_channel(&self, channel_id: &str, new_name: &str) -> bool {
        let conn = self.conn.lock().unwrap();
        match conn.execute("UPDATE channels SET name = ? WHERE channel_id = ?", params![new_name, channel_id]) {
            Ok(n) => n > 0,
            Err(_) => false,
        }
    }

    pub fn delete_channel(&self, channel_id: &str) {
        let conn = self.conn.lock().unwrap();
        let _ = conn.execute("DELETE FROM channels WHERE channel_id = ?", params![channel_id]);
        let _ = conn.execute("DELETE FROM messages WHERE target_id = ?", params![channel_id]);
    }

    pub fn create_invite(&self, room_id: &str, created_by: &str) -> String {
        let mut rng = rand::thread_rng();
        let mut code_bytes = [0u8; 2];
        rng.fill(&mut code_bytes);
        let code = format!("VC-{}", hex::encode(code_bytes).to_uppercase());

        let conn = self.conn.lock().unwrap();
        let now = current_time_secs();
        let _ = conn.execute(
            "INSERT OR REPLACE INTO room_invites (code, room_id, created_by, created_at) VALUES (?, ?, ?, ?)",
            params![code, room_id, created_by, now],
        );
        code
    }

    pub fn join_by_invite(&self, code: &str, user_id: &str) -> (bool, String, Option<String>) {
        let clean_code = code.trim().to_uppercase();
        let conn = self.conn.lock().unwrap();

        let room_id: Option<String> = conn
            .query_row("SELECT room_id FROM room_invites WHERE code = ?", params![clean_code], |r| r.get(0))
            .optional()
            .unwrap_or(None);

        match room_id {
            Some(rid) => {
                let now = current_time_secs();
                let _ = conn.execute(
                    "INSERT OR IGNORE INTO room_members (room_id, user_id, joined_at) VALUES (?, ?, ?)",
                    params![rid, user_id, now],
                );
                (true, "Успешное присоединение".to_string(), Some(rid))
            }
            None => (false, "Неверный или устаревший код приглашения".to_string(), None),
        }
    }

    pub fn load_all_rooms_and_channels(&self) -> Vec<RoomRow> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = match conn.prepare("SELECT room_id, name, owner_id, created_at FROM rooms ORDER BY created_at ASC") {
            Ok(s) => s,
            Err(_) => return Vec::new(),
        };

        let rooms_iter = stmt.query_map([], |r| {
            Ok((
                r.get::<_, String>(0)?,
                r.get::<_, String>(1)?,
                r.get::<_, String>(2)?,
                r.get::<_, f64>(3)?,
            ))
        });

        let mut rooms = Vec::new();
        if let Ok(r_iter) = rooms_iter {
            for item in r_iter.flatten() {
                let (rid, rname, owner, cr) = item;
                let mut ch_stmt = conn.prepare(
                    "SELECT channel_id, room_id, name, channel_type, created_at FROM channels WHERE room_id = ? ORDER BY created_at ASC"
                ).unwrap();
                let channels = ch_stmt.query_map(params![rid], |cr_row| {
                    Ok(ChannelRow {
                        channel_id: cr_row.get(0)?,
                        room_id: cr_row.get(1)?,
                        name: cr_row.get(2)?,
                        channel_type: cr_row.get(3)?,
                        created_at: cr_row.get(4)?,
                        voice_users: Vec::new(),
                    })
                }).unwrap().filter_map(|x| x.ok()).collect();

                rooms.push(RoomRow {
                    room_id: rid,
                    name: rname,
                    owner_id: owner,
                    created_at: cr,
                    channels,
                });
            }
        }
        rooms
    }

    pub fn get_user_rooms(&self, user_id: &str) -> Vec<RoomRow> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = match conn.prepare(
            "SELECT DISTINCT r.room_id, r.name, r.owner_id, r.created_at
             FROM rooms r
             LEFT JOIN room_members rm ON r.room_id = rm.room_id
             WHERE r.room_id = 'room-default' OR rm.user_id = ? OR r.owner_id = ?
             ORDER BY r.created_at ASC"
        ) {
            Ok(s) => s,
            Err(_) => return Vec::new(),
        };

        let rooms_iter = stmt.query_map(params![user_id, user_id], |r| {
            Ok((
                r.get::<_, String>(0)?,
                r.get::<_, String>(1)?,
                r.get::<_, String>(2)?,
                r.get::<_, f64>(3)?,
            ))
        });

        let mut rooms = Vec::new();
        if let Ok(r_iter) = rooms_iter {
            for item in r_iter.flatten() {
                let (rid, rname, owner, cr) = item;
                let mut ch_stmt = conn.prepare(
                    "SELECT channel_id, room_id, name, channel_type, created_at FROM channels WHERE room_id = ? ORDER BY created_at ASC"
                ).unwrap();
                let channels = ch_stmt.query_map(params![rid], |cr_row| {
                    Ok(ChannelRow {
                        channel_id: cr_row.get(0)?,
                        room_id: cr_row.get(1)?,
                        name: cr_row.get(2)?,
                        channel_type: cr_row.get(3)?,
                        created_at: cr_row.get(4)?,
                        voice_users: Vec::new(),
                    })
                }).unwrap().filter_map(|x| x.ok()).collect();

                rooms.push(RoomRow {
                    room_id: rid,
                    name: rname,
                    owner_id: owner,
                    created_at: cr,
                    channels,
                });
            }
        }
        rooms
    }

    pub fn leave_room(&self, room_id: &str, user_id: &str) -> (bool, String) {
        if room_id == "room-default" {
            return (false, "Нельзя покинуть главный сервер".to_string());
        }
        let conn = self.conn.lock().unwrap();
        let owner: Option<String> = conn
            .query_row("SELECT owner_id FROM rooms WHERE room_id = ?", params![room_id], |r| r.get(0))
            .optional()
            .unwrap_or(None);

        match owner {
            None => (false, "Сервер не найден".to_string()),
            Some(o) if o == user_id => {
                drop(conn);
                self.delete_room(room_id);
                (true, "Сервер удален создателем".to_string())
            }
            Some(_) => {
                let _ = conn.execute(
                    "DELETE FROM room_members WHERE room_id = ? AND user_id = ?",
                    params![room_id, user_id],
                );
                (true, "Вы покинули сервер".to_string())
            }
        }
    }

    pub fn get_room_members(&self, room_id: &str) -> Vec<UserRow> {
        let conn = self.conn.lock().unwrap();
        let (sql, p): (&str, Vec<Box<dyn rusqlite::ToSql>>) = if room_id == "room-default" {
            (
                "SELECT user_id, username, COALESCE(NULLIF(display_name, ''), username) as display_name,
                        status_text, avatar_color, avatar_image, bio,
                        COALESCE(banner_color, '#5865F2') as banner_color, COALESCE(banner_image, '') as banner_image, created_at
                 FROM users",
                Vec::new(),
            )
        } else {
            (
                "SELECT u.user_id, u.username, COALESCE(NULLIF(u.display_name, ''), u.username) as display_name,
                        u.status_text, u.avatar_color, u.avatar_image, u.bio,
                        COALESCE(u.banner_color, '#5865F2') as banner_color, COALESCE(u.banner_image, '') as banner_image, u.created_at
                 FROM room_members rm
                 JOIN users u ON rm.user_id = u.user_id
                 WHERE rm.room_id = ?",
                vec![Box::new(room_id.to_string())],
            )
        };

        let mut stmt = match conn.prepare(sql) {
            Ok(s) => s,
            Err(_) => return Vec::new(),
        };

        let refs: Vec<&dyn rusqlite::ToSql> = p.iter().map(|b| b.as_ref()).collect();
        let iter = stmt.query_map(rusqlite::params_from_iter(refs), |r| {
            Ok(UserRow {
                user_id: r.get(0)?,
                username: r.get(1)?,
                display_name: r.get(2)?,
                status_text: r.get(3)?,
                avatar_color: r.get(4)?,
                avatar_image: r.get(5)?,
                bio: r.get(6)?,
                banner_color: r.get(7)?,
                banner_image: r.get(8)?,
                created_at: r.get(9)?,
            })
        });

        match iter {
            Ok(rows) => rows.filter_map(|r| r.ok()).collect(),
            Err(_) => Vec::new(),
        }
    }

    pub fn get_stats(&self) -> (i64, i64, i64, i64) {
        let conn = self.conn.lock().unwrap();
        let u: i64 = conn.query_row("SELECT COUNT(*) FROM users", [], |r| r.get(0)).unwrap_or(0);
        let r: i64 = conn.query_row("SELECT COUNT(*) FROM rooms", [], |r| r.get(0)).unwrap_or(0);
        let c: i64 = conn.query_row("SELECT COUNT(*) FROM channels", [], |r| r.get(0)).unwrap_or(0);
        let m: i64 = conn.query_row("SELECT COUNT(*) FROM messages", [], |r| r.get(0)).unwrap_or(0);
        (u, r, c, m)
    }
}

pub fn current_time_secs() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_pbkdf2_python_compatibility() {
        let expected = "4508eedce8952f9d49fe93521ccaa747a7423d29a8ff8f6e24bc71ffbbb59316";
        let actual = Database::hash_password("testpass", "salttest");
        assert_eq!(actual, expected, "Password hash must match Python hashlib.pbkdf2_hmac exactly!");
    }

    #[test]
    fn test_db_crud_flow() {
        let db = Database::new(":memory:").expect("Failed to create in-memory database");

        // 1. Register user
        let user = db.register_user("Alice", "mypassword", Some("Alice Walker")).expect("Registration failed");
        assert_eq!(user.username, "Alice");
        assert_eq!(user.display_name, "Alice Walker");

        // 2. Authenticate user
        let auth = db.authenticate_user("Alice", "mypassword").expect("Auth failed");
        assert_eq!(auth.user_id, user.user_id);

        // 3. Wrong password
        assert!(db.authenticate_user("Alice", "wrongpass").is_err());

        // 4. Default room seeded
        let rooms = db.load_all_rooms_and_channels();
        assert!(!rooms.is_empty(), "Default room must be seeded");
        assert_eq!(rooms[0].room_id, "room-default");

        // 5. Send message
        let msg_id = db.save_message(
            None,
            "channel",
            "ch-general",
            &user.user_id,
            &user.username,
            "Hello World!",
            None,
            "",
            "",
            0.0,
            "",
            "",
            0,
        );
        assert!(!msg_id.is_empty());

        let msgs = db.get_messages("ch-general", 100);
        assert_eq!(msgs.len(), 1);
        assert_eq!(msgs[0].content, "Hello World!");
    }
}
