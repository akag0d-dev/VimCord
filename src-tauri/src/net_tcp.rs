use std::sync::Arc;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::net::TcpStream;
use tokio::sync::{mpsc, Mutex};
use serde_json::Value;
use tauri::{AppHandle, Manager};

pub struct TcpClient {
    write_tx: Option<mpsc::UnboundedSender<String>>,
    is_connected: Arc<Mutex<bool>>,
}

impl TcpClient {
    pub fn new() -> Self {
        Self {
            write_tx: None,
            is_connected: Arc::new(Mutex::new(false)),
        }
    }

    pub async fn is_connected(&self) -> bool {
        *self.is_connected.lock().await
    }

    pub async fn connect(
        &mut self,
        host: &str,
        port: u16,
        app: AppHandle,
    ) -> Result<(), String> {
        self.disconnect().await;

        let addr = format!("{}:{}", host, port);
        log::info!("Connecting to TCP server at {}", addr);

        let stream = TcpStream::connect(&addr)
            .await
            .map_err(|e| format!("Failed to connect to {}: {}", addr, e))?;

        let (read_half, mut write_half) = stream.into_split();
        let (tx, mut rx) = mpsc::unbounded_channel::<String>();
        self.write_tx = Some(tx);

        let is_connected_flag = self.is_connected.clone();
        *is_connected_flag.lock().await = true;

        // Background write loop
        let is_conn_writer = self.is_connected.clone();
        tokio::spawn(async move {
            while let Some(msg) = rx.recv().await {
                let mut data = msg.into_bytes();
                data.push(b'\n');
                if let Err(e) = write_half.write_all(&data).await {
                    log::error!("TCP write error: {}", e);
                    *is_conn_writer.lock().await = false;
                    break;
                }
            }
        });

        // Background read loop
        let is_conn_reader = self.is_connected.clone();
        let app_clone = app.clone();
        tokio::spawn(async move {
            let mut reader = BufReader::new(read_half);
            let mut line = String::new();

            dispatch_event(&app_clone, "connected", serde_json::json!({}));

            loop {
                line.clear();
                match reader.read_line(&mut line).await {
                    Ok(0) => {
                        log::info!("Server closed TCP connection");
                        break;
                    }
                    Ok(_) => {
                        let trimmed = line.trim();
                        if trimmed.is_empty() {
                            continue;
                        }
                        if let Ok(val) = serde_json::from_str::<Value>(trimmed) {
                            Self::dispatch_server_message(&app_clone, val);
                        }
                    }
                    Err(e) => {
                        log::error!("TCP read error: {}", e);
                        break;
                    }
                }
            }

            *is_conn_reader.lock().await = false;
            dispatch_event(&app_clone, "disconnected", serde_json::json!({}));
        });

        Ok(())
    }

    pub async fn disconnect(&mut self) {
        *self.is_connected.lock().await = false;
        self.write_tx = None;
    }

    pub fn send(&self, val: Value) {
        if let Some(tx) = &self.write_tx {
            if let Ok(s) = serde_json::to_string(&val) {
                let _ = tx.send(s);
            }
        }
    }

    fn dispatch_server_message(app: &AppHandle, val: Value) {
        let msg_type = val.get("type").and_then(|v| v.as_str()).unwrap_or("");
        match msg_type {
            "login_resp" | "login_response" => {
                let ok = val.get("success").and_then(|v| v.as_bool()).unwrap_or(false);
                if ok {
                    if let Some(uid) = val.get("user_id").and_then(|v| v.as_str()) {
                        if let Some(st) = app.try_state::<crate::commands::AppState>() {
                            if let Ok(mut lock) = st.my_user_id.try_lock() {
                                *lock = uid.to_string();
                            }
                            let udp_arc = st.udp.clone();
                            let audio_arc = st.audio.clone();
                            let app_cl = app.clone();
                            let uid_cl = uid.to_string();
                            tokio::spawn(async move {
                                let cfg = crate::config::load_config();
                                let host = if !cfg.host.trim().is_empty() { cfg.host } else { crate::protocol::DEFAULT_HOST.to_string() };
                                let udp_port = if cfg.udp_port > 0 { cfg.udp_port } else { crate::protocol::DEFAULT_UDP_PORT };

                                let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel::<(u8, String, Vec<u8>)>();
                                audio_arc.set_udp_sender(Some(tx));

                                let udp_for_rx = udp_arc.clone();
                                tokio::spawn(async move {
                                    while let Some((pkt_type, target_id, payload)) = rx.recv().await {
                                        udp_for_rx.lock().await.send_packet(pkt_type, &target_id, &payload).await;
                                    }
                                });

                                if let Err(e) = udp_arc.lock().await.start(uid_cl, host, udp_port, app_cl).await {
                                    log::error!("Failed to start UDP voice client on login: {}", e);
                                }
                            });
                        }
                    }
                    if let Some(w) = app.get_webview_window("main") {
                        let _ = w.set_size(tauri::LogicalSize::new(1280.0, 800.0));
                        let _ = w.center();
                    }
                }
                dispatch_event(app, "login_response", serde_json::json!({
                    "success": ok,
                    "data": val
                }));
            }
            "register_resp" | "register_response" => {
                let ok = val.get("success").and_then(|v| v.as_bool()).unwrap_or(false);
                let msg = val.get("message").and_then(|v| v.as_str()).unwrap_or("");
                dispatch_event(app, "register_response", serde_json::json!({
                    "success": ok,
                    "message": msg
                }));
            }
            "new_msg" | "chat_message" => {
                dispatch_event(app, "chat_message", val);
            }
            "history_resp" | "history_response" => {
                dispatch_event(app, "history_response", val);
            }
            "msg_deleted" | "message_deleted" => {
                dispatch_event(app, "message_deleted", val);
            }
            "user_presence" => {
                dispatch_event(app, "user_presence", val);
            }
            "room_created" => {
                let room_obj = val.get("room").cloned().unwrap_or_else(|| val.clone());
                dispatch_event(app, "room_created", room_obj);
            }
            "room_deleted" => {
                let rid = val.get("room_id").and_then(|v| v.as_str()).unwrap_or("");
                dispatch_event(app, "room_deleted", serde_json::json!(rid));
            }
            "channel_created" => {
                let rid = val.get("room_id").and_then(|v| v.as_str()).unwrap_or("");
                let ch = val.get("channel").cloned().unwrap_or(Value::Null);
                dispatch_event(app, "channel_created", serde_json::json!({
                    "room_id": rid,
                    "channel": ch
                }));
            }
            "channel_deleted" => {
                let rid = val.get("room_id").and_then(|v| v.as_str()).unwrap_or("");
                let cid = val.get("channel_id").and_then(|v| v.as_str()).unwrap_or("");
                dispatch_event(app, "channel_deleted", serde_json::json!({
                    "room_id": rid,
                    "channel_id": cid
                }));
            }
            "channel_renamed" => {
                let rid = val.get("room_id").and_then(|v| v.as_str()).unwrap_or("");
                let cid = val.get("channel_id").and_then(|v| v.as_str()).unwrap_or("");
                let name = val.get("name").and_then(|v| v.as_str()).unwrap_or("");
                dispatch_event(app, "channel_renamed", serde_json::json!({
                    "room_id": rid,
                    "channel_id": cid,
                    "name": name
                }));
            }
            "voice_state_update" => {
                dispatch_event(app, "voice_state_update", val);
            }
            "voice_channel_sync" => {
                dispatch_event(app, "voice_channel_sync", val);
            }
            "friends_update" => {
                let fl = val.get("friends").cloned().unwrap_or(Value::Array(vec![]));
                dispatch_event(app, "friends_update", fl);
            }
            "friend_request_resp" => {
                let ok = val.get("success").and_then(|v| v.as_bool()).unwrap_or(false);
                let msg = val.get("message").and_then(|v| v.as_str()).unwrap_or("");
                dispatch_event(app, "friend_request_resp", serde_json::json!({
                    "success": ok,
                    "message": msg
                }));
            }
            "incoming_call" => {
                let cid = val.get("call_id").and_then(|v| v.as_str()).unwrap_or("");
                let uid = val.get("from_user_id").and_then(|v| v.as_str()).unwrap_or("");
                let uname = val.get("from_username").and_then(|v| v.as_str()).unwrap_or("");
                dispatch_event(app, "incoming_call", serde_json::json!({
                    "call_id": cid,
                    "from_user_id": uid,
                    "from_username": uname
                }));
            }
            "call_ringing" => {
                let cid = val.get("call_id").and_then(|v| v.as_str()).unwrap_or("");
                let tid = val.get("target_id").and_then(|v| v.as_str()).unwrap_or("");
                dispatch_event(app, "call_ringing", serde_json::json!({
                    "call_id": cid,
                    "target_id": tid
                }));
            }
            "call_accepted" => {
                let cid = val.get("call_id").and_then(|v| v.as_str()).unwrap_or("");
                let pid = val.get("peer_id").and_then(|v| v.as_str()).unwrap_or("");
                let pname = val.get("peer_name").and_then(|v| v.as_str()).unwrap_or("");
                if let Some(st) = app.try_state::<crate::commands::AppState>() {
                    st.audio.set_voice_target(Some((crate::protocol::UDP_TYPE_DM_AUDIO, cid.to_string())));
                    st.audio.ensure_capture_and_playback(app);
                }
                dispatch_event(app, "call_accepted", serde_json::json!({
                    "call_id": cid,
                    "peer_id": pid,
                    "peer_name": pname
                }));
            }
            "call_declined" => {
                let cid = val.get("call_id").and_then(|v| v.as_str()).unwrap_or("");
                if let Some(st) = app.try_state::<crate::commands::AppState>() {
                    st.audio.set_voice_target(None);
                }
                dispatch_event(app, "call_declined", serde_json::json!({
                    "call_id": cid
                }));
            }
            "call_ended" => {
                let cid = val.get("call_id").and_then(|v| v.as_str()).unwrap_or("");
                if let Some(st) = app.try_state::<crate::commands::AppState>() {
                    st.audio.set_voice_target(None);
                }
                dispatch_event(app, "call_ended", serde_json::json!({
                    "call_id": cid
                }));
            }
            "call_failed" => {
                let r = val.get("reason").and_then(|v| v.as_str()).unwrap_or("");
                if let Some(st) = app.try_state::<crate::commands::AppState>() {
                    st.audio.set_voice_target(None);
                }
                dispatch_event(app, "call_failed", serde_json::json!({
                    "reason": r
                }));
            }
            "pong" => {
                let ts = val.get("timestamp").and_then(|v| v.as_f64()).unwrap_or(0.0);
                let now = std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap_or_default()
                    .as_secs_f64();
                let rtt_ms = ((now - ts).max(0.0) * 1000.0) as u32;
                dispatch_event(app, "pong", serde_json::json!({
                    "ping_ms": rtt_ms
                }));
            }
            "profile_update_resp" => {
                dispatch_event(app, "profile_update_resp", val);
            }
            "user_media_state" => {
                dispatch_event(app, "user_media_state", val);
            }
            "change_password_resp" => {
                dispatch_event(app, "change_password_resp", val);
            }
            "room_invite_created" => {
                let rid = val.get("room_id").and_then(|v| v.as_str()).unwrap_or("");
                let code = val.get("code").and_then(|v| v.as_str()).unwrap_or("");
                dispatch_event(app, "room_invite_created", serde_json::json!({
                    "room_id": rid,
                    "code": code
                }));
            }
            "room_invite_joined" => {
                let ok = val.get("success").and_then(|v| v.as_bool()).unwrap_or(false);
                let data = val.get("data").cloned().unwrap_or(Value::Null);
                dispatch_event(app, "room_invite_joined", serde_json::json!({
                    "success": ok,
                    "data": data
                }));
            }
            "leave_room_resp" => {
                let ok = val.get("success").and_then(|v| v.as_bool()).unwrap_or(false);
                let msg = val.get("message").and_then(|v| v.as_str()).unwrap_or("");
                let rid = val.get("room_id").and_then(|v| v.as_str()).unwrap_or("");
                dispatch_event(app, "leave_room_resp", serde_json::json!({
                    "success": ok,
                    "message": msg,
                    "room_id": rid
                }));
            }
            "room_members_resp" => {
                let rid = val.get("room_id").and_then(|v| v.as_str()).unwrap_or("");
                let members = val.get("members").cloned().unwrap_or(Value::Array(vec![]));
                dispatch_event(app, "room_members_resp", serde_json::json!({
                    "room_id": rid,
                    "members": members
                }));
            }
            "screen_frame" => {
                let sid = val.get("sender_id").and_then(|v| v.as_str()).unwrap_or("");
                let frame = val.get("data").and_then(|v| v.as_str()).unwrap_or("");
                dispatch_event(app, "screen_frame", serde_json::json!({
                    "sender_id": sid,
                    "frame": frame
                }));
            }
            "screen_stop" => {
                let sid = val.get("sender_id").and_then(|v| v.as_str()).unwrap_or("");
                dispatch_event(app, "screen_stop", serde_json::json!({
                    "sender_id": sid
                }));
            }
            _ => {
                log::debug!("Unhandled server message: {:?}", val);
            }
        }
    }
}

pub fn dispatch_event(app: &AppHandle, event_name: &str, payload: Value) {
    if let Some(w) = app.get_webview_window("main") {
        if let (Ok(evt_json), Ok(payload_json)) = (serde_json::to_string(event_name), serde_json::to_string(&payload)) {
            let js = format!(
                "if (typeof window.dispatchVimCordEvent === 'function') {{ window.dispatchVimCordEvent({}, {}); }} else if (typeof window.onVimCordEvent === 'function') {{ window.onVimCordEvent({}, {}); }}",
                evt_json, payload_json, evt_json, payload_json
            );
            let _ = w.eval(&js);
        }
    }
}
