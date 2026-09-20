#![allow(dead_code)]

use std::collections::{HashMap, HashSet};
use std::net::SocketAddr;
use std::sync::Arc;
use serde::{Deserialize, Serialize};
use serde_json::json;
use tokio::sync::{mpsc, RwLock};

use crate::db::{current_time_secs, Database};

#[derive(Debug, Clone)]
pub struct UserSession {
    pub user_id: String,
    pub username: String,
    pub display_name: String,
    pub avatar_color: String,
    pub avatar_image: String,
    pub bio: String,
    pub banner_color: String,
    pub banner_image: String,
    pub status_text: String,
    pub current_room_id: Option<String>,
    pub current_voice_channel_id: Option<String>,
    pub active_call_id: Option<String>,
    pub is_muted: bool,
    pub is_deafened: bool,
    pub udp_addr: Option<SocketAddr>,
    pub tx: mpsc::UnboundedSender<String>,
}

impl UserSession {
    pub fn to_dict(&self) -> serde_json::Value {
        json!({
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
            "in_call": self.active_call_id.is_some(),
            "is_muted": self.is_muted,
            "is_deafened": self.is_deafened,
            "online": true
        })
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Channel {
    pub channel_id: String,
    pub name: String,
    pub channel_type: String,
    pub voice_users: HashSet<String>,
}

impl Channel {
    pub fn to_dict(&self) -> serde_json::Value {
        json!({
            "channel_id": self.channel_id,
            "name": self.name,
            "channel_type": self.channel_type,
            "voice_users": self.voice_users.iter().cloned().collect::<Vec<_>>()
        })
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Room {
    pub room_id: String,
    pub name: String,
    pub owner_id: String,
    pub channels: HashMap<String, Channel>,
}

impl Room {
    pub fn to_dict(&self) -> serde_json::Value {
        let channels_vec: Vec<serde_json::Value> = self.channels.values().map(|c| c.to_dict()).collect();
        json!({
            "room_id": self.room_id,
            "name": self.name,
            "owner_id": self.owner_id,
            "channels": channels_vec
        })
    }
}

#[derive(Debug, Clone)]
pub struct CallSession {
    pub call_id: String,
    pub caller_id: String,
    pub callee_id: String,
    pub state: String, // "ringing", "active", "ended"
    pub started_at: f64,
}

pub struct ServerState {
    pub db: Arc<Database>,
    pub users: HashMap<String, UserSession>,
    pub udp_addr_to_user_id: HashMap<SocketAddr, String>,
    pub rooms: HashMap<String, Room>,
    pub calls: HashMap<String, CallSession>,
}

pub type SharedState = Arc<RwLock<ServerState>>;

impl ServerState {
    pub fn new(db: Arc<Database>) -> Self {
        let mut state = Self {
            db: db.clone(),
            users: HashMap::new(),
            udp_addr_to_user_id: HashMap::new(),
            rooms: HashMap::new(),
            calls: HashMap::new(),
        };
        state.load_from_db();
        state
    }

    fn load_from_db(&mut self) {
        let loaded_rooms = self.db.load_all_rooms_and_channels();
        for r_row in loaded_rooms {
            let mut ch_map = HashMap::new();
            for c_row in r_row.channels {
                ch_map.insert(
                    c_row.channel_id.clone(),
                    Channel {
                        channel_id: c_row.channel_id,
                        name: c_row.name,
                        channel_type: c_row.channel_type,
                        voice_users: HashSet::new(),
                    },
                );
            }
            self.rooms.insert(
                r_row.room_id.clone(),
                Room {
                    room_id: r_row.room_id,
                    name: r_row.name,
                    owner_id: r_row.owner_id,
                    channels: ch_map,
                },
            );
        }
    }

    pub fn add_user(&mut self, session: UserSession) {
        let uid = session.user_id.clone();
        self.users.insert(uid, session);
    }

    pub fn remove_user(&mut self, user_id: &str) -> Option<UserSession> {
        let session = self.users.remove(user_id);
        if let Some(ref u) = session {
            if let Some(addr) = u.udp_addr {
                self.udp_addr_to_user_id.remove(&addr);
            }
        }
        self.leave_voice(user_id);
        if let Some(ref u) = session {
            if let Some(ref cid) = u.active_call_id {
                self.end_call(cid);
            }
        }
        session
    }

    pub fn register_udp(&mut self, user_id: &str, addr: SocketAddr) {
        if let Some(user) = self.users.get_mut(user_id) {
            if let Some(prev) = user.udp_addr {
                self.udp_addr_to_user_id.remove(&prev);
            }
            user.udp_addr = Some(addr);
            self.udp_addr_to_user_id.insert(addr, user_id.to_string());
        }
    }

    pub fn create_room(&mut self, name: &str, owner_id: &str) -> Room {
        let room_id = format!("room-{}", &uuid::Uuid::new_v4().simple().to_string()[..8]);
        let ch_text_id = format!("ch-{}", &uuid::Uuid::new_v4().simple().to_string()[..6]);
        let ch_voice_id = format!("vch-{}", &uuid::Uuid::new_v4().simple().to_string()[..6]);

        let mut channels = HashMap::new();
        channels.insert(
            ch_text_id.clone(),
            Channel {
                channel_id: ch_text_id.clone(),
                name: "основной".to_string(),
                channel_type: "text".to_string(),
                voice_users: HashSet::new(),
            },
        );
        channels.insert(
            ch_voice_id.clone(),
            Channel {
                channel_id: ch_voice_id.clone(),
                name: "🔊 Голосовой".to_string(),
                channel_type: "voice".to_string(),
                voice_users: HashSet::new(),
            },
        );

        let room = Room {
            room_id: room_id.clone(),
            name: name.to_string(),
            owner_id: owner_id.to_string(),
            channels,
        };

        self.rooms.insert(room_id.clone(), room.clone());

        // Persist to DB
        self.db.save_room(&room_id, name, owner_id);
        self.db.save_channel(&ch_text_id, &room_id, "основной", "text");
        self.db.save_channel(&ch_voice_id, &room_id, "🔊 Голосовой", "voice");

        room
    }

    pub fn delete_room(&mut self, room_id: &str) -> bool {
        if room_id == "room-default" {
            return false;
        }
        if let Some(room) = self.rooms.remove(room_id) {
            for ch in room.channels.values() {
                for uid in &ch.voice_users {
                    self.leave_voice(uid);
                }
            }
            self.db.delete_room(room_id);
            true
        } else {
            false
        }
    }

    pub fn create_channel(&mut self, room_id: &str, name: &str, channel_type: &str) -> Option<Channel> {
        let room = self.rooms.get_mut(room_id)?;
        let prefix = if channel_type == "voice" { "vch-" } else { "ch-" };
        let channel_id = format!("{}{}", prefix, &uuid::Uuid::new_v4().simple().to_string()[..6]);

        let channel = Channel {
            channel_id: channel_id.clone(),
            name: name.to_string(),
            channel_type: channel_type.to_string(),
            voice_users: HashSet::new(),
        };

        room.channels.insert(channel_id.clone(), channel.clone());
        self.db.save_channel(&channel_id, room_id, name, channel_type);
        Some(channel)
    }

    pub fn delete_channel(&mut self, room_id: &str, channel_id: &str) -> bool {
        let room = match self.rooms.get_mut(room_id) {
            Some(r) => r,
            None => return false,
        };
        if let Some(ch) = room.channels.remove(channel_id) {
            for uid in &ch.voice_users {
                self.leave_voice(uid);
            }
            self.db.delete_channel(channel_id);
            true
        } else {
            false
        }
    }

    pub fn rename_channel(&mut self, room_id: &str, channel_id: &str, new_name: &str) -> bool {
        let room = match self.rooms.get_mut(room_id) {
            Some(r) => r,
            None => return false,
        };
        if let Some(ch) = room.channels.get_mut(channel_id) {
            ch.name = new_name.to_string();
            self.db.rename_channel(channel_id, new_name);
            true
        } else {
            false
        }
    }

    pub fn join_voice(&mut self, user_id: &str, room_id: &str, channel_id: &str) -> (bool, Vec<(String, String)>) {
        if !self.users.contains_key(user_id) {
            return (false, Vec::new());
        }

        let is_voice_ch = self.rooms.get(room_id)
            .and_then(|r| r.channels.get(channel_id))
            .map(|c| c.channel_type == "voice")
            .unwrap_or(false);

        if !is_voice_ch {
            return (false, Vec::new());
        }

        let prev_left = self.leave_voice(user_id);

        if let Some(room) = self.rooms.get_mut(room_id) {
            if let Some(ch) = room.channels.get_mut(channel_id) {
                ch.voice_users.insert(user_id.to_string());
            }
        }

        if let Some(user) = self.users.get_mut(user_id) {
            user.current_room_id = Some(room_id.to_string());
            user.current_voice_channel_id = Some(channel_id.to_string());
        }

        (true, prev_left)
    }

    pub fn leave_voice(&mut self, user_id: &str) -> Vec<(String, String)> {
        let mut left = Vec::new();
        if let Some(user) = self.users.get_mut(user_id) {
            if let (Some(r_id), Some(c_id)) = (user.current_room_id.take(), user.current_voice_channel_id.take()) {
                left.push((r_id, c_id));
            }
        }

        for (r_id, room) in self.rooms.iter_mut() {
            for (c_id, channel) in room.channels.iter_mut() {
                if channel.channel_type == "voice" && channel.voice_users.remove(user_id) {
                    let item = (r_id.clone(), c_id.clone());
                    if !left.contains(&item) {
                        left.push(item);
                    }
                }
            }
        }

        left
    }

    pub fn get_channel_voice_recipients(&self, sender_id: &str, channel_id: &str) -> Vec<SocketAddr> {
        let mut recipients = Vec::new();
        for room in self.rooms.values() {
            if let Some(ch) = room.channels.get(channel_id) {
                for uid in &ch.voice_users {
                    if uid != sender_id {
                        if let Some(u) = self.users.get(uid) {
                            if let Some(addr) = u.udp_addr {
                                recipients.push(addr);
                            }
                        }
                    }
                }
                break;
            }
        }
        recipients
    }

    pub fn create_call(&mut self, caller_id: &str, callee_id: &str) -> Option<CallSession> {
        let caller_busy = self.users.get(caller_id).map(|u| u.active_call_id.is_some()).unwrap_or(true);
        let callee_busy = self.users.get(callee_id).map(|u| u.active_call_id.is_some()).unwrap_or(true);
        if caller_busy || callee_busy {
            return None;
        }

        let call_id = format!("call-{}", &uuid::Uuid::new_v4().simple().to_string()[..8]);
        let session = CallSession {
            call_id: call_id.clone(),
            caller_id: caller_id.to_string(),
            callee_id: callee_id.to_string(),
            state: "ringing".to_string(),
            started_at: current_time_secs(),
        };

        self.calls.insert(call_id.clone(), session.clone());

        if let Some(u) = self.users.get_mut(caller_id) {
            u.active_call_id = Some(call_id.clone());
        }
        if let Some(u) = self.users.get_mut(callee_id) {
            u.active_call_id = Some(call_id);
        }

        Some(session)
    }

    pub fn accept_call(&mut self, call_id: &str) -> Option<CallSession> {
        let session = self.calls.get_mut(call_id)?;
        if session.state != "ringing" {
            return None;
        }
        session.state = "active".to_string();
        Some(session.clone())
    }

    pub fn end_call(&mut self, call_id: &str) -> Option<CallSession> {
        let mut session = self.calls.remove(call_id)?;
        session.state = "ended".to_string();

        if let Some(u) = self.users.get_mut(&session.caller_id) {
            if u.active_call_id.as_deref() == Some(call_id) {
                u.active_call_id = None;
            }
        }
        if let Some(u) = self.users.get_mut(&session.callee_id) {
            if u.active_call_id.as_deref() == Some(call_id) {
                u.active_call_id = None;
            }
        }

        Some(session)
    }

    pub fn get_call_peer_udp(&self, sender_id: &str, call_id: &str) -> Option<SocketAddr> {
        let session = self.calls.get(call_id)?;
        if session.state != "active" {
            return None;
        }
        let peer_id = if sender_id == session.caller_id {
            &session.callee_id
        } else {
            &session.caller_id
        };
        self.users.get(peer_id).and_then(|u| u.udp_addr)
    }

    pub fn get_all_users_dict(&self) -> Vec<serde_json::Value> {
        let db_users = self.db.get_all_users();
        let mut map: HashMap<String, serde_json::Value> = HashMap::new();

        for du in db_users {
            let uid = du.user_id.clone();
            map.insert(
                uid.clone(),
                json!({
                    "user_id": uid,
                    "username": du.username,
                    "display_name": du.display_name,
                    "avatar_color": du.avatar_color,
                    "avatar_image": du.avatar_image,
                    "bio": du.bio,
                    "status_text": if du.status_text.is_empty() { "Не в сети" } else { &du.status_text },
                    "current_room_id": None::<String>,
                    "current_voice_channel_id": None::<String>,
                    "in_call": false,
                    "is_muted": false,
                    "is_deafened": false,
                    "online": false
                }),
            );
        }

        for (uid, user) in &self.users {
            map.insert(uid.clone(), user.to_dict());
        }

        map.into_values().collect()
    }
}
