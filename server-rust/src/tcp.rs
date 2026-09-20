use std::net::SocketAddr;
use futures_util::StreamExt;
use serde_json::{json, Value};
use tokio::io::AsyncWriteExt;
use tokio::net::{TcpListener, TcpStream};
use tokio::sync::mpsc;
use tokio_util::codec::{FramedRead, LinesCodec};
use tracing::{debug, error, info, warn};

use crate::db::current_time_secs;
use crate::protocol::get_dm_chat_key;
use crate::state::{SharedState, UserSession};

pub async fn broadcast(state: &SharedState, msg: &Value, exclude_user_id: Option<&str>) {
    let text = serde_json::to_string(msg).unwrap();
    let s = state.read().await;
    for (uid, user) in &s.users {
        if let Some(ex) = exclude_user_id {
            if uid == ex {
                continue;
            }
        }
        let _ = user.tx.send(text.clone());
    }
}

pub async fn send_to_user(state: &SharedState, user_id: &str, msg: &Value) {
    let text = serde_json::to_string(msg).unwrap();
    let s = state.read().await;
    if let Some(user) = s.users.get(user_id) {
        let _ = user.tx.send(text);
    }
}

pub async fn send_to_channel_room(state: &SharedState, channel_id: &str, msg: &Value) {
    let (room_id, is_default) = {
        let s = state.read().await;
        let mut r_id = None;
        for (rid, r) in &s.rooms {
            if r.channels.contains_key(channel_id) {
                r_id = Some(rid.clone());
                break;
            }
        }
        let is_def = r_id.as_deref() == Some("room-default") || r_id.is_none();
        (r_id, is_def)
    };

    if is_default {
        broadcast(state, msg, None).await;
        return;
    }

    let rid = room_id.unwrap();
    let members = {
        let s = state.read().await;
        s.db.get_room_members(&rid)
    };

    for m in members {
        send_to_user(state, &m.user_id, msg).await;
    }
}

pub async fn send_to_room_members(state: &SharedState, room_id: &str, msg: &Value) {
    if room_id.is_empty() || room_id == "room-default" {
        broadcast(state, msg, None).await;
        return;
    }

    let members = {
        let s = state.read().await;
        s.db.get_room_members(room_id)
    };

    for m in members {
        send_to_user(state, &m.user_id, msg).await;
    }
}

pub async fn run_tcp_server(state: SharedState, host: &str, port: u16) -> anyhow::Result<()> {
    let addr = format!("{}:{}", host, port);
    let listener = TcpListener::bind(&addr).await?;
    info!("TCP Control Server listening on {}", addr);

    loop {
        let (socket, peer) = match listener.accept().await {
            Ok(res) => res,
            Err(e) => {
                error!("TCP accept error: {}", e);
                continue;
            }
        };

        let state_clone = state.clone();
        tokio::spawn(async move {
            if let Err(e) = handle_connection(state_clone, socket, peer).await {
                debug!("Client {} error: {}", peer, e);
            }
        });
    }
}

async fn handle_connection(state: SharedState, socket: TcpStream, peer: SocketAddr) -> anyhow::Result<()> {
    debug!("New TCP connection from {}", peer);
    let (reader, mut writer) = socket.into_split();

    // Limit line length to 64MB to support large file attachments and high-res screen frames
    let codec = LinesCodec::new_with_max_length(64 * 1024 * 1024);
    let mut framed_reader = FramedRead::new(reader, codec);

    let (tx, mut rx) = mpsc::unbounded_channel::<String>();

    // Spawn dedicated writer task
    let writer_task = tokio::spawn(async move {
        while let Some(msg) = rx.recv().await {
            if writer.write_all(msg.as_bytes()).await.is_err() {
                break;
            }
            if writer.write_all(b"\n").await.is_err() {
                break;
            }
            if writer.flush().await.is_err() {
                break;
            }
        }
    });

    let mut current_user_id: Option<String> = None;

    while let Some(line_res) = framed_reader.next().await {
        let line = match line_res {
            Ok(l) => l,
            Err(e) => {
                warn!("TCP framed read error from {}: {}", peer, e);
                break;
            }
        };

        if line.trim().is_empty() {
            continue;
        }

        let msg: Value = match serde_json::from_str(&line) {
            Ok(v) => v,
            Err(_) => continue,
        };

        let msg_type = msg.get("type").and_then(|t| t.as_str()).unwrap_or("");

        // 1. REGISTER
        if msg_type == "register" {
            let uname = msg.get("username").and_then(|v| v.as_str()).unwrap_or("").trim();
            let pwd = msg.get("password").and_then(|v| v.as_str()).unwrap_or("").trim();
            let disp = msg.get("display_name").and_then(|v| v.as_str());

            let res = {
                let s = state.read().await;
                s.db.register_user(uname, pwd, disp)
            };

            let resp = match res {
                Ok(_) => json!({ "type": "register_resp", "success": true, "message": "Registration successful" }),
                Err(err) => json!({ "type": "register_resp", "success": false, "message": err }),
            };
            let _ = tx.send(serde_json::to_string(&resp).unwrap());
            continue;
        }

        // 2. LOGIN
        if msg_type == "login" {
            let uname = msg.get("username").and_then(|v| v.as_str()).unwrap_or("Anonymous").trim();
            let pwd = msg.get("password").and_then(|v| v.as_str()).unwrap_or("").trim();

            let u_data_res = {
                let s = state.read().await;
                if !pwd.is_empty() {
                    s.db.authenticate_user(uname, pwd)
                } else {
                    // Fallback for tests/unauthenticated login
                    match s.db.get_user_by_username(uname) {
                        Some(u) => Ok(u),
                        None => s.db.register_user(uname, "testpass123", None),
                    }
                }
            };

            let u_data = match u_data_res {
                Ok(u) => u,
                Err(err) => {
                    let resp = json!({ "type": "login_resp", "success": false, "message": err });
                    let _ = tx.send(serde_json::to_string(&resp).unwrap());
                    continue;
                }
            };

            // Clear any old voice session and session record
            let prev_left = {
                let mut s = state.write().await;
                let left = s.leave_voice(&u_data.user_id);
                s.remove_user(&u_data.user_id);
                left
            };

            for (pr_id, pc_id) in prev_left {
                broadcast(
                    &state,
                    &json!({
                        "type": "voice_state_update",
                        "user_id": u_data.user_id,
                        "room_id": pr_id,
                        "channel_id": pc_id,
                        "action": "leave"
                    }),
                    None,
                ).await;
            }

            let session = UserSession {
                user_id: u_data.user_id.clone(),
                username: u_data.username.clone(),
                display_name: u_data.display_name.clone(),
                avatar_color: u_data.avatar_color.clone(),
                avatar_image: u_data.avatar_image.clone(),
                bio: u_data.bio.clone(),
                banner_color: u_data.banner_color.clone(),
                banner_image: u_data.banner_image.clone(),
                status_text: u_data.status_text.clone(),
                current_room_id: None,
                current_voice_channel_id: None,
                active_call_id: None,
                is_muted: false,
                is_deafened: false,
                udp_addr: None,
                tx: tx.clone(),
            };

            let user_dict = session.to_dict();

            {
                let mut s = state.write().await;
                s.add_user(session);
            }
            current_user_id = Some(u_data.user_id.clone());

            let (friends, mut user_rooms, all_users) = {
                let s = state.read().await;
                let fr = s.db.get_friends(&u_data.user_id);
                let rooms = s.db.get_user_rooms(&u_data.user_id);
                let users = s.get_all_users_dict();
                (fr, rooms, users)
            };

            // Synchronize in-memory live voice_users into room channels data
            {
                let s = state.read().await;
                for r in &mut user_rooms {
                    if let Some(live_r) = s.rooms.get(&r.room_id) {
                        for c in &mut r.channels {
                            if let Some(live_c) = live_r.channels.get(&c.channel_id) {
                                c.voice_users = live_c.voice_users.iter().cloned().collect();
                            }
                        }
                    }
                }
            }

            let resp = json!({
                "type": "login_resp",
                "success": true,
                "user_id": u_data.user_id,
                "username": u_data.username,
                "display_name": u_data.display_name,
                "avatar_color": u_data.avatar_color,
                "avatar_image": u_data.avatar_image,
                "banner_color": u_data.banner_color,
                "banner_image": u_data.banner_image,
                "bio": u_data.bio,
                "status_text": u_data.status_text,
                "rooms": user_rooms,
                "users": all_users,
                "friends": friends
            });
            let _ = tx.send(serde_json::to_string(&resp).unwrap());

            // Broadcast user presence to others
            broadcast(
                &state,
                &json!({
                    "type": "user_presence",
                    "user": user_dict
                }),
                Some(&u_data.user_id),
            ).await;

            info!("User logged in: {} ({})", u_data.username, u_data.user_id);
            continue;
        }

        // Require authentication for all subsequent actions
        let uid = match current_user_id {
            Some(ref id) => id.clone(),
            None => continue,
        };

        match msg_type {
            // 3. GET CHAT HISTORY
            "get_history" => {
                let t_type = msg.get("target_type").and_then(|v| v.as_str()).unwrap_or("channel");
                let t_id = msg.get("target_id").and_then(|v| v.as_str()).unwrap_or("");
                let db_key = if t_type == "channel" {
                    t_id.to_string()
                } else {
                    get_dm_chat_key(&uid, t_id)
                };

                let history = {
                    let s = state.read().await;
                    s.db.get_messages(&db_key, 100)
                };

                let resp = json!({
                    "type": "history_resp",
                    "target_type": t_type,
                    "target_id": t_id,
                    "messages": history
                });
                let _ = tx.send(serde_json::to_string(&resp).unwrap());
            }

            // 4. SEND MESSAGE
            "send_msg" => {
                let t_type = msg.get("target_type").and_then(|v| v.as_str()).unwrap_or("channel");
                let t_id = msg.get("target_id").and_then(|v| v.as_str()).unwrap_or("");
                let content = msg.get("content").and_then(|v| v.as_str()).unwrap_or("").trim();
                let image_data = msg.get("image_data").and_then(|v| v.as_str()).unwrap_or("");
                let voice_data = msg.get("voice_data").and_then(|v| v.as_str()).unwrap_or("");
                let voice_duration = msg.get("voice_duration").and_then(|v| v.as_f64()).unwrap_or(0.0);
                let file_data = msg.get("file_data").and_then(|v| v.as_str()).unwrap_or("");
                let file_name = msg.get("file_name").and_then(|v| v.as_str()).unwrap_or("");
                let file_size = msg.get("file_size").and_then(|v| v.as_i64()).unwrap_or(0);
                let client_msg_id = msg.get("msg_id").and_then(|v| v.as_str()).map(|s| s.to_string());

                if !content.is_empty() || !image_data.is_empty() || !voice_data.is_empty() || !file_data.is_empty() {
                    let now = current_time_secs();
                    let msg_id = client_msg_id.unwrap_or_else(|| format!("msg-{}", &uuid::Uuid::new_v4().simple().to_string()[..8]));

                    let (sender_name, display_name, avatar_color, avatar_image) = {
                        let s = state.read().await;
                        s.users.get(&uid).map(|u| (u.username.clone(), u.display_name.clone(), u.avatar_color.clone(), u.avatar_image.clone()))
                            .unwrap_or_else(|| ("Unknown".into(), "Unknown".into(), "#5865F2".into(), "".into()))
                    };

                    let db_key = if t_type == "channel" {
                        t_id.to_string()
                    } else {
                        get_dm_chat_key(&uid, t_id)
                    };

                    {
                        let s = state.read().await;
                        s.db.save_message(
                            Some(msg_id.clone()),
                            t_type,
                            &db_key,
                            &uid,
                            &sender_name,
                            content,
                            Some(now),
                            image_data,
                            voice_data,
                            voice_duration,
                            file_data,
                            file_name,
                            file_size,
                        );
                    }

                    let chat_msg = json!({
                        "type": "new_msg",
                        "msg_id": msg_id,
                        "target_type": t_type,
                        "target_id": t_id,
                        "sender_id": uid,
                        "sender_name": sender_name,
                        "display_name": display_name,
                        "avatar_color": avatar_color,
                        "avatar_image": avatar_image,
                        "content": content,
                        "image_data": image_data,
                        "voice_data": voice_data,
                        "voice_duration": voice_duration,
                        "file_data": file_data,
                        "file_name": file_name,
                        "file_size": file_size,
                        "timestamp": now
                    });

                    if t_type == "channel" {
                        send_to_channel_room(&state, t_id, &chat_msg).await;
                    } else if t_type == "dm" {
                        send_to_user(&state, t_id, &chat_msg).await;
                        send_to_user(&state, &uid, &chat_msg).await;
                    }
                }
            }

            // 4.1 DELETE MESSAGE
            "delete_msg" => {
                let mid = msg.get("msg_id").and_then(|v| v.as_str()).unwrap_or("");
                let t_type = msg.get("target_type").and_then(|v| v.as_str()).unwrap_or("");
                let t_id = msg.get("target_id").and_then(|v| v.as_str()).unwrap_or("");

                let deleted = {
                    let s = state.read().await;
                    s.db.delete_message(mid, &uid)
                };

                if deleted {
                    let del_event = json!({
                        "type": "msg_deleted",
                        "msg_id": mid,
                        "target_type": t_type,
                        "target_id": t_id
                    });

                    if t_type == "channel" {
                        send_to_channel_room(&state, t_id, &del_event).await;
                    } else if t_type == "dm" {
                        send_to_user(&state, t_id, &del_event).await;
                        send_to_user(&state, &uid, &del_event).await;
                    }
                }
            }

            // 5. CREATE ROOM
            "create_room" => {
                let name = msg.get("name").and_then(|v| v.as_str()).unwrap_or("Новая комната").trim();
                let room = {
                    let mut s = state.write().await;
                    s.create_room(if name.is_empty() { "Новая комната" } else { name }, &uid)
                };

                let resp = json!({ "type": "room_created", "room": room.to_dict() });
                send_to_user(&state, &uid, &resp).await;
            }

            // 5.1 LEAVE ROOM
            "leave_room" => {
                let room_id = msg.get("room_id").and_then(|v| v.as_str()).unwrap_or("");
                let (ok, res_msg) = {
                    let s = state.read().await;
                    s.db.leave_room(room_id, &uid)
                };

                let resp = json!({
                    "type": "leave_room_resp",
                    "success": ok,
                    "message": res_msg,
                    "room_id": room_id
                });
                let _ = tx.send(serde_json::to_string(&resp).unwrap());

                if ok {
                    let prev_voice = {
                        let mut s = state.write().await;
                        let user_in_room = s.users.get(&uid).and_then(|u| u.current_room_id.as_deref()) == Some(room_id);
                        if user_in_room {
                            s.leave_voice(&uid)
                        } else {
                            Vec::new()
                        }
                    };

                    for (r, c) in prev_voice {
                        broadcast(
                            &state,
                            &json!({
                                "type": "voice_state_update",
                                "user_id": uid,
                                "room_id": r,
                                "channel_id": c,
                                "action": "leave"
                            }),
                            None,
                        ).await;
                    }

                    if res_msg == "Сервер удален создателем" {
                        {
                            let mut s = state.write().await;
                            s.rooms.remove(room_id);
                        }
                        broadcast(&state, &json!({ "type": "room_deleted", "room_id": room_id }), None).await;
                    }
                }
            }

            // 5.2 GET ROOM MEMBERS
            "get_room_members" => {
                let room_id = msg.get("room_id").and_then(|v| v.as_str()).unwrap_or("");
                let (members, voice_map) = {
                    let s = state.read().await;
                    let m_list = s.db.get_room_members(room_id);
                    let mut vm: serde_json::Map<String, Value> = serde_json::Map::new();

                    if let Some(live_room) = s.rooms.get(room_id) {
                        for (cid, ch) in &live_room.channels {
                            if ch.channel_type == "voice" {
                                let mut user_list = Vec::new();
                                for u_id in &ch.voice_users {
                                    if let Some(u_obj) = s.users.get(u_id) {
                                        user_list.push(json!({
                                            "user_id": u_obj.user_id,
                                            "username": u_obj.username,
                                            "display_name": u_obj.display_name,
                                            "avatar_color": u_obj.avatar_color,
                                            "avatar_image": u_obj.avatar_image,
                                            "is_muted": u_obj.is_muted,
                                            "is_deafened": u_obj.is_deafened
                                        }));
                                    }
                                }
                                vm.insert(cid.clone(), Value::Array(user_list));
                            }
                        }
                    }
                    (m_list, vm)
                };

                let online_set = {
                    let s = state.read().await;
                    s.users.keys().cloned().collect::<std::collections::HashSet<_>>()
                };

                let members_json: Vec<Value> = members.iter().map(|m| {
                    let is_online = online_set.contains(&m.user_id);
                    json!({
                        "user_id": m.user_id,
                        "username": m.username,
                        "display_name": m.display_name,
                        "status_text": m.status_text,
                        "avatar_color": m.avatar_color,
                        "avatar_image": m.avatar_image,
                        "bio": m.bio,
                        "banner_color": m.banner_color,
                        "banner_image": m.banner_image,
                        "online": is_online
                    })
                }).collect();

                let resp = json!({
                    "type": "room_members_resp",
                    "room_id": room_id,
                    "members": members_json,
                    "voice_channels": voice_map
                });
                let _ = tx.send(serde_json::to_string(&resp).unwrap());
            }

            // 5.3 PING
            "ping" => {
                let ts = msg.get("timestamp").and_then(|v| v.as_f64()).unwrap_or_else(current_time_secs);
                let resp = json!({ "type": "pong", "timestamp": ts });
                let _ = tx.send(serde_json::to_string(&resp).unwrap());
            }

            // 6. DELETE ROOM
            "delete_room" => {
                let room_id = msg.get("room_id").and_then(|v| v.as_str()).unwrap_or("");
                let members: Vec<String> = {
                    let s = state.read().await;
                    s.db.get_room_members(room_id).into_iter().map(|m| m.user_id).collect()
                };
                let ok = {
                    let mut s = state.write().await;
                    s.delete_room(room_id)
                };
                if ok {
                    let notif = json!({ "type": "room_deleted", "room_id": room_id });
                    for member_id in &members {
                        send_to_user(&state, member_id, &notif).await;
                    }
                    send_to_user(&state, &uid, &notif).await;
                }
            }

            // 7. CREATE CHANNEL
            "create_channel" => {
                let room_id = msg.get("room_id").and_then(|v| v.as_str()).unwrap_or("");
                let name = msg.get("name").and_then(|v| v.as_str()).unwrap_or("канал").trim();
                let ch_type = msg.get("channel_type").and_then(|v| v.as_str()).unwrap_or("text");

                let channel_opt = {
                    let mut s = state.write().await;
                    s.create_channel(room_id, if name.is_empty() { "канал" } else { name }, ch_type)
                };

                if let Some(ch) = channel_opt {
                    send_to_room_members(
                        &state,
                        room_id,
                        &json!({
                            "type": "channel_created",
                            "room_id": room_id,
                            "channel": ch.to_dict()
                        }),
                    ).await;
                }
            }

            // 8. DELETE CHANNEL
            "delete_channel" => {
                let room_id = msg.get("room_id").and_then(|v| v.as_str()).unwrap_or("");
                let channel_id = msg.get("channel_id").and_then(|v| v.as_str()).unwrap_or("");

                let ok = {
                    let mut s = state.write().await;
                    s.delete_channel(room_id, channel_id)
                };

                if ok {
                    send_to_room_members(
                        &state,
                        room_id,
                        &json!({
                            "type": "channel_deleted",
                            "room_id": room_id,
                            "channel_id": channel_id
                        }),
                    ).await;
                }
            }

            // 8b. RENAME CHANNEL
            "rename_channel" => {
                let room_id = msg.get("room_id").and_then(|v| v.as_str()).unwrap_or("");
                let channel_id = msg.get("channel_id").and_then(|v| v.as_str()).unwrap_or("");
                let new_name = msg.get("name").and_then(|v| v.as_str()).unwrap_or("").trim();

                if !new_name.is_empty() {
                    let ok = {
                        let mut s = state.write().await;
                        s.rename_channel(room_id, channel_id, new_name)
                    };

                    if ok {
                        send_to_room_members(
                            &state,
                            room_id,
                            &json!({
                                "type": "channel_renamed",
                                "room_id": room_id,
                                "channel_id": channel_id,
                                "name": new_name
                            }),
                        ).await;
                    }
                }
            }

            // 9. SERVER INVITES
            "create_room_invite" => {
                let room_id = msg.get("room_id").and_then(|v| v.as_str()).unwrap_or("");
                let code = {
                    let s = state.read().await;
                    s.db.create_invite(room_id, &uid)
                };

                let resp = json!({
                    "type": "room_invite_created",
                    "room_id": room_id,
                    "code": code
                });
                let _ = tx.send(serde_json::to_string(&resp).unwrap());
            }

            "join_room_by_invite" => {
                let code = msg.get("code").and_then(|v| v.as_str()).unwrap_or("").trim();
                let (ok, res_msg, room_id_opt) = {
                    let s = state.read().await;
                    s.db.join_by_invite(code, &uid)
                };

                if ok {
                    if let Some(rid) = room_id_opt {
                        let room_dict = {
                            let s = state.read().await;
                            s.rooms.get(&rid).map(|r| r.to_dict())
                        };

                        if let Some(rd) = room_dict {
                            let resp = json!({
                                "type": "room_invite_joined",
                                "success": true,
                                "room": rd
                            });
                            let _ = tx.send(serde_json::to_string(&resp).unwrap());
                            continue;
                        }
                    }
                }

                let resp = json!({
                    "type": "room_invite_joined",
                    "success": false,
                    "message": res_msg
                });
                let _ = tx.send(serde_json::to_string(&resp).unwrap());
            }

            // 10. FRIEND REQUESTS & FRIENDS LIST
            "send_friend_request" => {
                let target_uname = msg.get("username").and_then(|v| v.as_str()).unwrap_or("").trim();
                let (ok, res_msg, target_info) = {
                    let s = state.read().await;
                    s.db.send_friend_request(&uid, target_uname)
                };

                let resp = json!({
                    "type": "friend_request_resp",
                    "success": ok,
                    "message": res_msg
                });
                let _ = tx.send(serde_json::to_string(&resp).unwrap());

                if ok {
                    if let Some(tgt) = target_info {
                        let (sender_friends, receiver_friends) = {
                            let s = state.read().await;
                            (s.db.get_friends(&uid), s.db.get_friends(&tgt.user_id))
                        };
                        send_to_user(&state, &uid, &json!({ "type": "friends_update", "friends": sender_friends })).await;
                        send_to_user(&state, &tgt.user_id, &json!({ "type": "friends_update", "friends": receiver_friends })).await;
                    }
                }
            }

            "accept_friend_request" => {
                let sender_uid = msg.get("sender_user_id").and_then(|v| v.as_str()).unwrap_or("");
                let ok = {
                    let s = state.read().await;
                    s.db.accept_friend_request(&uid, sender_uid)
                };

                if ok {
                    let (f1, f2) = {
                        let s = state.read().await;
                        (s.db.get_friends(&uid), s.db.get_friends(sender_uid))
                    };
                    send_to_user(&state, &uid, &json!({ "type": "friends_update", "friends": f1 })).await;
                    send_to_user(&state, sender_uid, &json!({ "type": "friends_update", "friends": f2 })).await;
                }
            }

            "decline_friend_request" => {
                let peer_id = msg.get("peer_id").and_then(|v| v.as_str()).unwrap_or("");
                let ok = {
                    let s = state.read().await;
                    s.db.decline_friend_request(&uid, peer_id)
                };

                if ok {
                    let (f1, f2) = {
                        let s = state.read().await;
                        (s.db.get_friends(&uid), s.db.get_friends(peer_id))
                    };
                    send_to_user(&state, &uid, &json!({ "type": "friends_update", "friends": f1 })).await;
                    send_to_user(&state, peer_id, &json!({ "type": "friends_update", "friends": f2 })).await;
                }
            }

            // 11. PROFILE UPDATE & MEDIA STATE
            "update_profile" => {
                let new_uname = msg.get("username").and_then(|v| v.as_str());
                let new_dname = msg.get("display_name").and_then(|v| v.as_str());
                let new_status = msg.get("status_text").and_then(|v| v.as_str());
                let new_color = msg.get("avatar_color").and_then(|v| v.as_str());
                let new_avatar = msg.get("avatar_image").and_then(|v| v.as_str());
                let new_bcolor = msg.get("banner_color").and_then(|v| v.as_str());
                let new_bimage = msg.get("banner_image").and_then(|v| v.as_str());
                let new_bio = msg.get("bio").and_then(|v| v.as_str());

                let res = {
                    let s = state.read().await;
                    s.db.update_profile(
                        &uid,
                        new_uname,
                        new_dname,
                        new_status,
                        new_color,
                        new_avatar,
                        new_bio,
                        new_bcolor,
                        new_bimage,
                    )
                };

                match res {
                    Ok(_) => {
                        let user_dict = {
                            let mut s = state.write().await;
                            if let Some(u) = s.users.get_mut(&uid) {
                                if let Some(un) = new_uname { u.username = un.to_string(); }
                                if let Some(dn) = new_dname { u.display_name = if dn.trim().is_empty() { u.username.clone() } else { dn.trim().to_string() }; }
                                if let Some(st) = new_status { u.status_text = st.to_string(); }
                                if let Some(ac) = new_color { u.avatar_color = ac.to_string(); }
                                if let Some(ai) = new_avatar { u.avatar_image = ai.to_string(); }
                                if let Some(bc) = new_bcolor { u.banner_color = bc.to_string(); }
                                if let Some(bi) = new_bimage { u.banner_image = bi.to_string(); }
                                if let Some(b) = new_bio { u.bio = b.to_string(); }
                                u.to_dict()
                            } else {
                                json!({})
                            }
                        };

                        broadcast(&state, &json!({ "type": "user_presence", "user": user_dict }), None).await;

                        let resp = json!({
                            "type": "profile_update_resp",
                            "success": true,
                            "message": "Profile updated successfully",
                            "user": user_dict
                        });
                        let _ = tx.send(serde_json::to_string(&resp).unwrap());
                    }
                    Err(err) => {
                        let resp = json!({
                            "type": "profile_update_resp",
                            "success": false,
                            "message": err
                        });
                        let _ = tx.send(serde_json::to_string(&resp).unwrap());
                    }
                }
            }

            "get_profile" => {
                let target_uid = msg.get("user_id").and_then(|v| v.as_str()).unwrap_or("");
                let info_opt = {
                    let s = state.read().await;
                    s.db.get_user_by_id(target_uid)
                };

                if let Some(info) = info_opt {
                    let is_online = {
                        let s = state.read().await;
                        s.users.contains_key(target_uid)
                    };
                    let resp = json!({
                        "type": "profile_resp",
                        "success": true,
                        "profile": {
                            "user_id": info.user_id,
                            "username": info.username,
                            "display_name": info.display_name,
                            "status_text": info.status_text,
                            "avatar_color": info.avatar_color,
                            "avatar_image": info.avatar_image,
                            "bio": info.bio,
                            "banner_color": info.banner_color,
                            "banner_image": info.banner_image,
                            "online": is_online
                        }
                    });
                    let _ = tx.send(serde_json::to_string(&resp).unwrap());
                } else {
                    let resp = json!({
                        "type": "profile_resp",
                        "success": false,
                        "error": "Пользователь не найден"
                    });
                    let _ = tx.send(serde_json::to_string(&resp).unwrap());
                }
            }

            "user_media_state" => {
                let is_muted = msg.get("is_muted").and_then(|v| v.as_bool()).unwrap_or(false);
                let is_deafened = msg.get("is_deafened").and_then(|v| v.as_bool()).unwrap_or(false);

                {
                    let mut s = state.write().await;
                    if let Some(u) = s.users.get_mut(&uid) {
                        u.is_muted = is_muted;
                        u.is_deafened = is_deafened;
                    }
                }

                broadcast(
                    &state,
                    &json!({
                        "type": "user_media_state",
                        "user_id": uid,
                        "is_muted": is_muted,
                        "is_deafened": is_deafened
                    }),
                    None,
                ).await;
            }

            "change_password" => {
                let old_p = msg.get("old_password").and_then(|v| v.as_str()).unwrap_or("");
                let new_p = msg.get("new_password").and_then(|v| v.as_str()).unwrap_or("");

                let res = {
                    let s = state.read().await;
                    s.db.change_password(&uid, old_p, new_p)
                };

                let resp = match res {
                    Ok(_) => json!({ "type": "change_password_resp", "success": true, "message": "Password changed successfully" }),
                    Err(err) => json!({ "type": "change_password_resp", "success": false, "message": err }),
                };
                let _ = tx.send(serde_json::to_string(&resp).unwrap());
            }

            // 12. VOICE CHANNELS
            "join_voice" => {
                let room_id = msg.get("room_id").and_then(|v| v.as_str()).unwrap_or("");
                let channel_id = msg.get("channel_id").and_then(|v| v.as_str()).unwrap_or("");

                let (ok, prev_list, is_muted, is_deafened) = {
                    let mut s = state.write().await;
                    let (succ, left) = s.join_voice(&uid, room_id, channel_id);
                    let (m, d) = s.users.get(&uid).map(|u| (u.is_muted, u.is_deafened)).unwrap_or((false, false));
                    (succ, left, m, d)
                };

                if ok {
                    for (pr_id, pc_id) in prev_list {
                        broadcast(
                            &state,
                            &json!({
                                "type": "voice_state_update",
                                "user_id": uid,
                                "room_id": pr_id,
                                "channel_id": pc_id,
                                "action": "leave"
                            }),
                            None,
                        ).await;
                    }

                    broadcast(
                        &state,
                        &json!({
                            "type": "voice_state_update",
                            "user_id": uid,
                            "room_id": room_id,
                            "channel_id": channel_id,
                            "action": "join",
                            "is_muted": is_muted,
                            "is_deafened": is_deafened
                        }),
                        None,
                    ).await;

                    // Send snapshot of current participants to the joining user
                    let participants: Vec<Value> = {
                        let s = state.read().await;
                        let mut list = Vec::new();
                        if let Some(ch) = s.rooms.get(room_id).and_then(|r| r.channels.get(channel_id)) {
                            for member_id in &ch.voice_users {
                                if let Some(u_obj) = s.users.get(member_id) {
                                    list.push(json!({
                                        "user_id": u_obj.user_id,
                                        "username": u_obj.username,
                                        "display_name": u_obj.display_name,
                                        "avatar_color": u_obj.avatar_color,
                                        "avatar_image": u_obj.avatar_image,
                                        "is_muted": u_obj.is_muted,
                                        "is_deafened": u_obj.is_deafened,
                                        "is_speaking": false
                                    }));
                                } else if let Some(db_u) = s.db.get_user_by_id(member_id) {
                                    list.push(json!({
                                        "user_id": db_u.user_id,
                                        "username": db_u.username,
                                        "display_name": db_u.display_name,
                                        "avatar_color": db_u.avatar_color,
                                        "avatar_image": db_u.avatar_image,
                                        "is_muted": false,
                                        "is_deafened": false,
                                        "is_speaking": false
                                    }));
                                }
                            }
                        }
                        list
                    };

                    let sync_msg = json!({
                        "type": "voice_channel_sync",
                        "room_id": room_id,
                        "channel_id": channel_id,
                        "users": participants
                    });
                    let _ = tx.send(serde_json::to_string(&sync_msg).unwrap());
                }
            }

            "leave_voice" => {
                let prev_list = {
                    let mut s = state.write().await;
                    s.leave_voice(&uid)
                };

                for (r, c) in prev_list {
                    broadcast(
                        &state,
                        &json!({
                            "type": "voice_state_update",
                            "user_id": uid,
                            "room_id": r,
                            "channel_id": c,
                            "action": "leave"
                        }),
                        None,
                    ).await;
                }
            }

            // 13. DIRECT CALLS
            "call_start" => {
                let target_user_id = msg.get("target_user_id").and_then(|v| v.as_str()).unwrap_or("");
                let is_friend = {
                    let s = state.read().await;
                    s.db.is_friend(&uid, target_user_id)
                };

                if !is_friend {
                    let resp = json!({
                        "type": "call_failed",
                        "target_user_id": target_user_id,
                        "reason": "Звонки доступны только друзьям"
                    });
                    let _ = tx.send(serde_json::to_string(&resp).unwrap());
                    continue;
                }

                let session_opt = {
                    let mut s = state.write().await;
                    s.create_call(&uid, target_user_id)
                };

                match session_opt {
                    Some(session) => {
                        let caller_name = {
                            let s = state.read().await;
                            s.users.get(&uid).map(|u| u.username.clone()).unwrap_or_else(|| "Unknown".into())
                        };

                        send_to_user(
                            &state,
                            target_user_id,
                            &json!({
                                "type": "incoming_call",
                                "call_id": session.call_id,
                                "from_user_id": uid,
                                "from_username": caller_name
                            }),
                        ).await;

                        let ring_resp = json!({
                            "type": "call_ringing",
                            "call_id": session.call_id,
                            "target_user_id": target_user_id
                        });
                        let _ = tx.send(serde_json::to_string(&ring_resp).unwrap());
                    }
                    None => {
                        let fail_resp = json!({ "type": "call_failed", "reason": "User is busy or unavailable" });
                        let _ = tx.send(serde_json::to_string(&fail_resp).unwrap());
                    }
                }
            }

            "call_accept" => {
                let call_id = msg.get("call_id").and_then(|v| v.as_str()).unwrap_or("");
                let session_opt = {
                    let mut s = state.write().await;
                    s.accept_call(call_id)
                };

                if let Some(session) = session_opt {
                    let (caller_name, callee_name) = {
                        let s = state.read().await;
                        (
                            s.users.get(&session.caller_id).map(|u| u.username.clone()).unwrap_or_else(|| "Unknown".into()),
                            s.users.get(&session.callee_id).map(|u| u.username.clone()).unwrap_or_else(|| "Unknown".into()),
                        )
                    };

                    send_to_user(
                        &state,
                        &session.caller_id,
                        &json!({
                            "type": "call_accepted",
                            "call_id": call_id,
                            "peer_id": session.callee_id,
                            "peer_name": callee_name
                        }),
                    ).await;

                    send_to_user(
                        &state,
                        &session.callee_id,
                        &json!({
                            "type": "call_accepted",
                            "call_id": call_id,
                            "peer_id": session.caller_id,
                            "peer_name": caller_name
                        }),
                    ).await;
                }
            }

            "call_decline" => {
                let call_id = msg.get("call_id").and_then(|v| v.as_str()).unwrap_or("");
                let session_opt = {
                    let mut s = state.write().await;
                    s.end_call(call_id)
                };

                if let Some(session) = session_opt {
                    let peer_id = if uid == session.callee_id { session.caller_id } else { session.callee_id };
                    send_to_user(&state, &peer_id, &json!({ "type": "call_declined", "call_id": call_id })).await;
                }
            }

            "call_end" => {
                let call_id = msg.get("call_id").and_then(|v| v.as_str()).unwrap_or("");
                let session_opt = {
                    let mut s = state.write().await;
                    let target_cid = if !call_id.is_empty() {
                        call_id.to_string()
                    } else {
                        s.users.get(&uid).and_then(|u| u.active_call_id.clone()).unwrap_or_default()
                    };
                    s.end_call(&target_cid)
                };

                if let Some(session) = session_opt {
                    let end_event = json!({ "type": "call_ended", "call_id": session.call_id });
                    send_to_user(&state, &session.caller_id, &end_event).await;
                    send_to_user(&state, &session.callee_id, &end_event).await;
                }
            }

            // 14. SCREEN SHARING (TCP Reliable Forwarding)
            "screen_frame" => {
                let t_type = msg.get("target_type").and_then(|v| v.as_str()).unwrap_or("");
                let t_id = msg.get("target_id").and_then(|v| v.as_str()).unwrap_or("");
                let b64_data = msg.get("data").and_then(|v| v.as_str()).unwrap_or("");

                let sender_name = {
                    let s = state.read().await;
                    s.users.get(&uid).map(|u| u.username.clone()).unwrap_or_else(|| "Unknown".into())
                };

                let frame_event = json!({
                    "type": "screen_frame",
                    "sender_id": uid,
                    "sender_name": sender_name,
                    "target_id": t_id,
                    "data": b64_data
                });

                if t_type == "channel" {
                    let recipients = {
                        let s = state.read().await;
                        let mut list = Vec::new();
                        for r in s.rooms.values() {
                            if let Some(ch) = r.channels.get(t_id) {
                                for member_id in &ch.voice_users {
                                    if member_id != &uid {
                                        list.push(member_id.clone());
                                    }
                                }
                                break;
                            }
                        }
                        list
                    };
                    for r_uid in recipients {
                        send_to_user(&state, &r_uid, &frame_event).await;
                    }
                } else if t_type == "call" {
                    let peer_opt = {
                        let s = state.read().await;
                        s.calls.get(t_id).and_then(|sess| {
                            if sess.state == "active" {
                                Some(if uid == sess.caller_id { sess.callee_id.clone() } else { sess.caller_id.clone() })
                            } else {
                                None
                            }
                        })
                    };
                    if let Some(peer_id) = peer_opt {
                        send_to_user(&state, &peer_id, &frame_event).await;
                    }
                } else if t_type == "dm" || t_type == "user" {
                    send_to_user(&state, t_id, &frame_event).await;
                }
            }

            "screen_stop" => {
                let t_type = msg.get("target_type").and_then(|v| v.as_str()).unwrap_or("");
                let t_id = msg.get("target_id").and_then(|v| v.as_str()).unwrap_or("");

                let stop_event = json!({
                    "type": "screen_stop",
                    "sender_id": uid,
                    "target_id": t_id
                });

                if t_type == "channel" {
                    let recipients = {
                        let s = state.read().await;
                        let mut list = Vec::new();
                        for r in s.rooms.values() {
                            if let Some(ch) = r.channels.get(t_id) {
                                for member_id in &ch.voice_users {
                                    if member_id != &uid {
                                        list.push(member_id.clone());
                                    }
                                }
                                break;
                            }
                        }
                        list
                    };
                    for r_uid in recipients {
                        send_to_user(&state, &r_uid, &stop_event).await;
                    }
                } else if t_type == "call" {
                    let peer_opt = {
                        let s = state.read().await;
                        s.calls.get(t_id).and_then(|sess| {
                            if sess.state == "active" {
                                Some(if uid == sess.caller_id { sess.callee_id.clone() } else { sess.caller_id.clone() })
                            } else {
                                None
                            }
                        })
                    };
                    if let Some(peer_id) = peer_opt {
                        send_to_user(&state, &peer_id, &stop_event).await;
                    }
                } else if t_type == "dm" || t_type == "user" {
                    send_to_user(&state, t_id, &stop_event).await;
                }
            }

            _ => {
                debug!("Unhandled TCP message type: {}", msg_type);
            }
        }
    }

    // Client disconnected
    if let Some(uid) = current_user_id {
        let (removed_user, prev_left) = {
            let mut s = state.write().await;
            let left = s.leave_voice(&uid);
            let u = s.remove_user(&uid);
            (u, left)
        };

        if let Some(u) = removed_user {
            info!("User disconnected: {} ({})", u.username, u.user_id);
            for (pr_id, pc_id) in prev_left {
                broadcast(
                    &state,
                    &json!({
                        "type": "voice_state_update",
                        "user_id": uid,
                        "room_id": pr_id,
                        "channel_id": pc_id,
                        "action": "leave"
                    }),
                    None,
                ).await;
            }

            broadcast(
                &state,
                &json!({
                    "type": "user_presence",
                    "user": {
                        "user_id": u.user_id,
                        "username": u.username,
                        "status_text": "Не в сети",
                        "avatar_color": u.avatar_color,
                        "avatar_image": u.avatar_image,
                        "bio": u.bio,
                        "online": false
                    }
                }),
                None,
            ).await;
        }
    }

    writer_task.abort();
    Ok(())
}
