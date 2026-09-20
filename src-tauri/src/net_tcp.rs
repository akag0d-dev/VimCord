use std::sync::Arc;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::net::TcpStream;
use tokio::sync::{mpsc, Mutex};
use serde_json::Value;
use tauri::{AppHandle, Emitter};

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

            let _ = app_clone.emit("vimcord://event", serde_json::json!({
                "event": "connected",
                "payload": {}
            }));

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
            let _ = app_clone.emit("vimcord://event", serde_json::json!({
                "event": "disconnected",
                "payload": {}
            }));
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
            "login_response" => {
                let ok = val.get("success").and_then(|v| v.as_bool()).unwrap_or(false);
                let _ = app.emit("vimcord://event", serde_json::json!({
                    "event": "login_response",
                    "payload": {
                        "success": ok,
                        "data": val
                    }
                }));
            }
            "register_response" => {
                let ok = val.get("success").and_then(|v| v.as_bool()).unwrap_or(false);
                let msg = val.get("message").and_then(|v| v.as_str()).unwrap_or("");
                let _ = app.emit("vimcord://event", serde_json::json!({
                    "event": "register_response",
                    "payload": {
                        "success": ok,
                        "message": msg
                    }
                }));
            }
            "chat_message" => {
                let _ = app.emit("vimcord://event", serde_json::json!({
                    "event": "chat_message",
                    "payload": val
                }));
            }
            "history_response" => {
                let _ = app.emit("vimcord://event", serde_json::json!({
                    "event": "history_response",
                    "payload": val
                }));
            }
            "message_deleted" => {
                let _ = app.emit("vimcord://event", serde_json::json!({
                    "event": "message_deleted",
                    "payload": val
                }));
            }
            "user_presence" => {
                let _ = app.emit("vimcord://event", serde_json::json!({
                    "event": "user_presence",
                    "payload": val
                }));
            }
            "room_created" => {
                let _ = app.emit("vimcord://event", serde_json::json!({
                    "event": "room_created",
                    "payload": val
                }));
            }
            "room_deleted" => {
                let rid = val.get("room_id").and_then(|v| v.as_str()).unwrap_or("");
                let _ = app.emit("vimcord://event", serde_json::json!({
                    "event": "room_deleted",
                    "payload": rid
                }));
            }
            "channel_created" => {
                let rid = val.get("room_id").and_then(|v| v.as_str()).unwrap_or("");
                let ch = val.get("channel").cloned().unwrap_or(Value::Null);
                let _ = app.emit("vimcord://event", serde_json::json!({
                    "event": "channel_created",
                    "payload": { "room_id": rid, "channel": ch }
                }));
            }
            "channel_deleted" => {
                let rid = val.get("room_id").and_then(|v| v.as_str()).unwrap_or("");
                let cid = val.get("channel_id").and_then(|v| v.as_str()).unwrap_or("");
                let _ = app.emit("vimcord://event", serde_json::json!({
                    "event": "channel_deleted",
                    "payload": { "room_id": rid, "channel_id": cid }
                }));
            }
            "channel_renamed" => {
                let rid = val.get("room_id").and_then(|v| v.as_str()).unwrap_or("");
                let cid = val.get("channel_id").and_then(|v| v.as_str()).unwrap_or("");
                let name = val.get("name").and_then(|v| v.as_str()).unwrap_or("");
                let _ = app.emit("vimcord://event", serde_json::json!({
                    "event": "channel_renamed",
                    "payload": { "room_id": rid, "channel_id": cid, "name": name }
                }));
            }
            "voice_state_update" => {
                let _ = app.emit("vimcord://event", serde_json::json!({
                    "event": "voice_state_update",
                    "payload": val
                }));
            }
            "voice_channel_sync" => {
                let _ = app.emit("vimcord://event", serde_json::json!({
                    "event": "voice_channel_sync",
                    "payload": val
                }));
            }
            "friends_update" => {
                let fl = val.get("friends").cloned().unwrap_or(Value::Array(vec![]));
                let _ = app.emit("vimcord://event", serde_json::json!({
                    "event": "friends_update",
                    "payload": fl
                }));
            }
            "friend_request_resp" => {
                let ok = val.get("success").and_then(|v| v.as_bool()).unwrap_or(false);
                let msg = val.get("message").and_then(|v| v.as_str()).unwrap_or("");
                let _ = app.emit("vimcord://event", serde_json::json!({
                    "event": "friend_request_resp",
                    "payload": { "success": ok, "message": msg }
                }));
            }
            "incoming_call" => {
                let cid = val.get("call_id").and_then(|v| v.as_str()).unwrap_or("");
                let uid = val.get("from_user_id").and_then(|v| v.as_str()).unwrap_or("");
                let uname = val.get("from_username").and_then(|v| v.as_str()).unwrap_or("");
                let _ = app.emit("vimcord://event", serde_json::json!({
                    "event": "incoming_call",
                    "payload": {
                        "call_id": cid,
                        "from_user_id": uid,
                        "from_username": uname
                    }
                }));
            }
            "call_ringing" => {
                let cid = val.get("call_id").and_then(|v| v.as_str()).unwrap_or("");
                let tid = val.get("target_id").and_then(|v| v.as_str()).unwrap_or("");
                let _ = app.emit("vimcord://event", serde_json::json!({
                    "event": "call_ringing",
                    "payload": { "call_id": cid, "target_id": tid }
                }));
            }
            "call_accepted" => {
                let cid = val.get("call_id").and_then(|v| v.as_str()).unwrap_or("");
                let pid = val.get("peer_id").and_then(|v| v.as_str()).unwrap_or("");
                let pname = val.get("peer_name").and_then(|v| v.as_str()).unwrap_or("");
                let _ = app.emit("vimcord://event", serde_json::json!({
                    "event": "call_accepted",
                    "payload": { "call_id": cid, "peer_id": pid, "peer_name": pname }
                }));
            }
            "call_declined" => {
                let cid = val.get("call_id").and_then(|v| v.as_str()).unwrap_or("");
                let _ = app.emit("vimcord://event", serde_json::json!({
                    "event": "call_declined",
                    "payload": { "call_id": cid }
                }));
            }
            "call_ended" => {
                let cid = val.get("call_id").and_then(|v| v.as_str()).unwrap_or("");
                let _ = app.emit("vimcord://event", serde_json::json!({
                    "event": "call_ended",
                    "payload": { "call_id": cid }
                }));
            }
            "call_failed" => {
                let r = val.get("reason").and_then(|v| v.as_str()).unwrap_or("");
                let _ = app.emit("vimcord://event", serde_json::json!({
                    "event": "call_failed",
                    "payload": { "reason": r }
                }));
            }
            "pong" => {
                let ts = val.get("timestamp").and_then(|v| v.as_f64()).unwrap_or(0.0);
                let now = std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap_or_default()
                    .as_secs_f64();
                let rtt_ms = ((now - ts).max(0.0) * 1000.0) as u32;
                let _ = app.emit("vimcord://event", serde_json::json!({
                    "event": "pong",
                    "payload": { "ping_ms": rtt_ms }
                }));
            }
            "profile_update_resp" => {
                let _ = app.emit("vimcord://event", serde_json::json!({
                    "event": "profile_update_resp",
                    "payload": val
                }));
            }
            "user_media_state" => {
                let _ = app.emit("vimcord://event", serde_json::json!({
                    "event": "user_media_state",
                    "payload": val
                }));
            }
            "change_password_resp" => {
                let _ = app.emit("vimcord://event", serde_json::json!({
                    "event": "change_password_resp",
                    "payload": val
                }));
            }
            "room_invite_created" => {
                let rid = val.get("room_id").and_then(|v| v.as_str()).unwrap_or("");
                let code = val.get("code").and_then(|v| v.as_str()).unwrap_or("");
                let _ = app.emit("vimcord://event", serde_json::json!({
                    "event": "room_invite_created",
                    "payload": { "room_id": rid, "code": code }
                }));
            }
            "room_invite_joined" => {
                let ok = val.get("success").and_then(|v| v.as_bool()).unwrap_or(false);
                let data = val.get("data").cloned().unwrap_or(Value::Null);
                let _ = app.emit("vimcord://event", serde_json::json!({
                    "event": "room_invite_joined",
                    "payload": { "success": ok, "data": data }
                }));
            }
            "leave_room_resp" => {
                let ok = val.get("success").and_then(|v| v.as_bool()).unwrap_or(false);
                let msg = val.get("message").and_then(|v| v.as_str()).unwrap_or("");
                let rid = val.get("room_id").and_then(|v| v.as_str()).unwrap_or("");
                let _ = app.emit("vimcord://event", serde_json::json!({
                    "event": "leave_room_resp",
                    "payload": { "success": ok, "message": msg, "room_id": rid }
                }));
            }
            "room_members_resp" => {
                let rid = val.get("room_id").and_then(|v| v.as_str()).unwrap_or("");
                let members = val.get("members").cloned().unwrap_or(Value::Array(vec![]));
                let _ = app.emit("vimcord://event", serde_json::json!({
                    "event": "room_members_resp",
                    "payload": { "room_id": rid, "members": members }
                }));
            }
            "screen_frame" => {
                let sid = val.get("sender_id").and_then(|v| v.as_str()).unwrap_or("");
                let frame = val.get("data").and_then(|v| v.as_str()).unwrap_or("");
                let _ = app.emit("vimcord://event", serde_json::json!({
                    "event": "screen_frame",
                    "payload": { "sender_id": sid, "frame": frame }
                }));
            }
            "screen_stop" => {
                let sid = val.get("sender_id").and_then(|v| v.as_str()).unwrap_or("");
                let _ = app.emit("vimcord://event", serde_json::json!({
                    "event": "screen_stop",
                    "payload": { "sender_id": sid }
                }));
            }
            _ => {
                log::debug!("Unhandled server message: {:?}", val);
            }
        }
    }
}
