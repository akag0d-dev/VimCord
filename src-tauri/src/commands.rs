use serde_json::Value;
use std::sync::Arc;
use tauri::{AppHandle, Manager, State};
use tokio::sync::Mutex;

use crate::audio::AudioManager;
use crate::config::{load_config, save_config, ClientConfig};
use crate::net_tcp::TcpClient;
use crate::net_udp::UdpVoiceClient;

pub struct AppState {
    pub tcp: Arc<Mutex<TcpClient>>,
    pub udp: Arc<Mutex<UdpVoiceClient>>,
    pub audio: Arc<AudioManager>,
    pub my_user_id: Arc<Mutex<String>>,
    pub my_username: Arc<Mutex<String>>,
}

impl AppState {
    pub fn new() -> Self {
        Self {
            tcp: Arc::new(Mutex::new(TcpClient::new())),
            udp: Arc::new(Mutex::new(UdpVoiceClient::new())),
            audio: Arc::new(AudioManager::new()),
            my_user_id: Arc::new(Mutex::new(String::new())),
            my_username: Arc::new(Mutex::new(String::new())),
        }
    }
}

#[tauri::command]
pub async fn get_initial_state(state: State<'_, AppState>) -> Result<Value, String> {
    let cfg = load_config();
    let devices = AudioManager::get_devices();

    Ok(serde_json::json!({
        "config": cfg,
        "language": cfg.language,
        "audio_devices": devices,
        "input_device": cfg.input_device,
        "output_device": cfg.output_device,
        "theme": cfg.theme,
        "ptt_mode": cfg.ptt_mode,
        "ptt_key": cfg.ptt_key,
        "mic_volume": cfg.mic_volume,
        "output_volume": cfg.output_volume,
        "vad_threshold": cfg.vad_threshold,
        "dnd_mode": cfg.dnd_mode,
        "stream_resolution": cfg.stream_resolution,
        "stream_fps": cfg.stream_fps,
        "stream_quality": cfg.stream_quality,
        "auto_login": cfg.auto_login,
        "saved_username": if !cfg.saved_username.is_empty() { cfg.saved_username } else { cfg.username },
        "saved_password": if cfg.auto_login { cfg.saved_password } else { String::new() }
    }))
}

#[tauri::command]
pub async fn minimize_window(app: AppHandle) -> Result<(), String> {
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.minimize();
    }
    Ok(())
}

#[tauri::command]
pub async fn toggle_maximize_window(app: AppHandle) -> Result<(), String> {
    if let Some(w) = app.get_webview_window("main") {
        if let Ok(maximized) = w.is_maximized() {
            if maximized {
                let _ = w.unmaximize();
            } else {
                let _ = w.maximize();
            }
        }
    }
    Ok(())
}

#[tauri::command]
pub async fn close_window(app: AppHandle) -> Result<(), String> {
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.hide();
    }
    Ok(())
}

#[tauri::command]
pub async fn set_window_size(app: AppHandle, width: f64, height: f64) -> Result<(), String> {
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.set_size(tauri::LogicalSize::new(width, height));
        let _ = w.center();
    }
    Ok(())
}

#[tauri::command]
pub async fn quit_app(app: AppHandle, state: State<'_, AppState>) -> Result<(), String> {
    state.tcp.lock().await.disconnect().await;
    state.udp.lock().await.stop().await;
    app.exit(0);
    Ok(())
}

#[tauri::command]
pub async fn login(
    app: AppHandle,
    state: State<'_, AppState>,
    username: String,
    password: Option<String>,
    host: Option<String>,
    tcp_port: Option<u16>,
    udp_port: Option<u16>,
    auto_login: Option<bool>,
) -> Result<Value, String> {
    let mut cfg = load_config();
    let pwd = password.unwrap_or_default();
    let auto = auto_login.unwrap_or(false);

    let h = match host {
        Some(h) if !h.trim().is_empty() => h.trim().to_string(),
        _ => cfg.host.clone(),
    };
    let tp = match tcp_port {
        Some(p) if p > 0 => p,
        _ => cfg.tcp_port,
    };
    let up = match udp_port {
        Some(p) if p > 0 => p,
        _ => cfg.udp_port,
    };

    cfg.host = h.clone();
    cfg.tcp_port = tp;
    cfg.udp_port = up;
    cfg.username = username.clone();
    cfg.saved_username = username.clone();
    cfg.auto_login = auto;
    if auto && !pwd.is_empty() {
        cfg.saved_password = pwd.clone();
    }
    save_config(&cfg);

    *state.my_username.lock().await = username.clone();

    let mut tcp = state.tcp.lock().await;
    if !tcp.is_connected().await {
        if let Err(e) = tcp.connect(&h, tp, app.clone()).await {
            return Ok(serde_json::json!({
                "success": false,
                "message": format!("Could not connect to server at {}:{}: {}", h, tp, e)
            }));
        }
    }

    tcp.send(serde_json::json!({
        "type": "login",
        "username": username,
        "password": pwd
    }));

    Ok(serde_json::json!({
        "success": true,
        "pending": true
    }))
}

#[tauri::command]
pub async fn register(
    app: AppHandle,
    state: State<'_, AppState>,
    username: String,
    password: Option<String>,
    host: Option<String>,
    tcp_port: Option<u16>,
    udp_port: Option<u16>,
) -> Result<Value, String> {
    let cfg = load_config();
    let pwd = password.unwrap_or_default();
    let h = match host {
        Some(h) if !h.trim().is_empty() => h.trim().to_string(),
        _ => cfg.host.clone(),
    };
    let tp = match tcp_port {
        Some(p) if p > 0 => p,
        _ => cfg.tcp_port,
    };

    let mut tcp = state.tcp.lock().await;
    if !tcp.is_connected().await {
        if let Err(e) = tcp.connect(&h, tp, app.clone()).await {
            return Ok(serde_json::json!({
                "success": false,
                "message": format!("Could not connect to server at {}:{}: {}", h, tp, e)
            }));
        }
    }

    tcp.send(serde_json::json!({
        "type": "register",
        "username": username,
        "password": pwd
    }));

    Ok(serde_json::json!({
        "success": true,
        "pending": true
    }))
}

#[tauri::command]
pub async fn logout(app: AppHandle, state: State<'_, AppState>) -> Result<(), String> {
    let mut cfg = load_config();
    cfg.auto_login = false;
    cfg.saved_password = String::new();
    save_config(&cfg);

    state.tcp.lock().await.disconnect().await;
    state.udp.lock().await.stop().await;

    if let Some(w) = app.get_webview_window("main") {
        let _ = w.set_size(tauri::LogicalSize::new(460.0, 620.0));
        let _ = w.center();
    }

    Ok(())
}

#[tauri::command]
pub async fn send_chat_message(
    state: State<'_, AppState>,
    target_type: String,
    target_id: String,
    content: Option<String>,
    image_data: Option<String>,
    voice_data: Option<String>,
    voice_duration: Option<f64>,
    file_data: Option<String>,
    file_name: Option<String>,
    file_size: Option<u64>,
) -> Result<Value, String> {
    let msg_id = format!("m-{}", &uuid::Uuid::new_v4().to_string()[..8]);
    let uid = state.my_user_id.lock().await.clone();
    let uname = state.my_username.lock().await.clone();
    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs_f64();

    let local_msg = serde_json::json!({
        "msg_id": msg_id,
        "sender_id": uid,
        "sender_name": uname,
        "target_type": target_type,
        "target_id": target_id,
        "content": content.clone().unwrap_or_default(),
        "image_data": image_data.clone().unwrap_or_default(),
        "voice_data": voice_data.clone().unwrap_or_default(),
        "voice_duration": voice_duration.unwrap_or(0.0),
        "file_data": file_data.clone().unwrap_or_default(),
        "file_name": file_name.clone().unwrap_or_default(),
        "file_size": file_size.unwrap_or(0),
        "timestamp": now,
        "pending": false
    });

    state.tcp.lock().await.send(serde_json::json!({
        "type": "send_msg",
        "msg_id": msg_id,
        "target_type": target_type,
        "target_id": target_id,
        "content": content.unwrap_or_default(),
        "image_data": image_data.unwrap_or_default(),
        "voice_data": voice_data.unwrap_or_default(),
        "voice_duration": voice_duration.unwrap_or(0.0),
        "file_data": file_data.unwrap_or_default(),
        "file_name": file_name.unwrap_or_default(),
        "file_size": file_size.unwrap_or(0)
    }));

    Ok(local_msg)
}

#[tauri::command]
pub async fn delete_message(
    state: State<'_, AppState>,
    msg_id: String,
    target_type: String,
    target_id: String,
) -> Result<(), String> {
    state.tcp.lock().await.send(serde_json::json!({
        "type": "delete_msg",
        "msg_id": msg_id,
        "target_type": target_type,
        "target_id": target_id
    }));
    Ok(())
}

#[tauri::command]
pub async fn get_history(
    state: State<'_, AppState>,
    target_type: String,
    target_id: String,
) -> Result<(), String> {
    state.tcp.lock().await.send(serde_json::json!({
        "type": "get_history",
        "target_type": target_type,
        "target_id": target_id
    }));
    Ok(())
}

#[tauri::command]
pub async fn open_file_dialog() -> Result<Option<Value>, String> {
    let file = rfd::AsyncFileDialog::new().pick_file().await;
    if let Some(f) = file {
        let path = f.path();
        if let Ok(bytes) = tokio::fs::read(path).await {
            let size = bytes.len();
            if size > 25 * 1024 * 1024 {
                return Ok(Some(serde_json::json!({ "error": "File exceeds 25 MB limit" })));
            }
            let name = path
                .file_name()
                .map(|n| n.to_string_lossy().to_string())
                .unwrap_or_else(|| "file".to_string());
            let ext = path
                .extension()
                .map(|e| e.to_string_lossy().to_lowercase())
                .unwrap_or_default();
            let is_image = matches!(ext.as_str(), "png" | "jpg" | "jpeg" | "webp" | "gif" | "bmp");
            use base64::Engine;
            let b64 = base64::engine::general_purpose::STANDARD.encode(&bytes);

            return Ok(Some(serde_json::json!({
                "name": name,
                "size": size,
                "is_image": is_image,
                "data": b64
            })));
        }
    }
    Ok(None)
}

#[tauri::command]
pub async fn save_file_to_disk(filename: String, b64_data: String) -> Result<Value, String> {
    use base64::Engine;
    if let Ok(bytes) = base64::engine::general_purpose::STANDARD.decode(&b64_data) {
        if let Some(mut dl) = dirs::download_dir() {
            dl.push(&filename);
            let _ = tokio::fs::write(&dl, bytes).await;
            return Ok(serde_json::json!({
                "success": true,
                "path": dl.to_string_lossy().to_string()
            }));
        }
    }
    Ok(serde_json::json!({
        "success": false,
        "error": "Failed to save file"
    }))
}

#[tauri::command]
pub async fn join_voice(
    state: State<'_, AppState>,
    room_id: String,
    channel_id: String,
) -> Result<(), String> {
    state.tcp.lock().await.send(serde_json::json!({
        "type": "join_voice",
        "room_id": room_id,
        "channel_id": channel_id
    }));
    Ok(())
}

#[tauri::command]
pub async fn leave_voice(state: State<'_, AppState>) -> Result<(), String> {
    state.tcp.lock().await.send(serde_json::json!({
        "type": "leave_voice"
    }));
    Ok(())
}

#[tauri::command]
pub async fn start_call(state: State<'_, AppState>, target_user_id: String) -> Result<(), String> {
    state.tcp.lock().await.send(serde_json::json!({
        "type": "call_start",
        "target_user_id": target_user_id
    }));
    Ok(())
}

#[tauri::command]
pub async fn accept_call(state: State<'_, AppState>, call_id: String) -> Result<(), String> {
    state.tcp.lock().await.send(serde_json::json!({
        "type": "call_accept",
        "call_id": call_id
    }));
    Ok(())
}

#[tauri::command]
pub async fn decline_call(state: State<'_, AppState>, call_id: String) -> Result<(), String> {
    state.tcp.lock().await.send(serde_json::json!({
        "type": "call_decline",
        "call_id": call_id
    }));
    Ok(())
}

#[tauri::command]
pub async fn end_call(state: State<'_, AppState>, call_id: Option<String>) -> Result<(), String> {
    if let Some(cid) = call_id {
        state.tcp.lock().await.send(serde_json::json!({
            "type": "call_end",
            "call_id": cid
        }));
    }
    Ok(())
}

#[tauri::command]
pub async fn set_mic_muted(state: State<'_, AppState>, muted: bool) -> Result<(), String> {
    state.audio.set_muted(muted);
    state.tcp.lock().await.send(serde_json::json!({
        "type": "user_media_state",
        "is_muted": muted,
        "is_deafened": false
    }));
    Ok(())
}

#[tauri::command]
pub async fn set_deafened(state: State<'_, AppState>, deafened: bool) -> Result<(), String> {
    state.audio.set_deafened(deafened);
    state.tcp.lock().await.send(serde_json::json!({
        "type": "user_media_state",
        "is_muted": deafened,
        "is_deafened": deafened
    }));
    Ok(())
}

#[tauri::command]
pub async fn set_mic_volume(state: State<'_, AppState>, volume: f32) -> Result<(), String> {
    state.audio.set_mic_volume(volume).await;
    let mut cfg = load_config();
    cfg.mic_volume = (volume * 100.0) as u32;
    save_config(&cfg);
    Ok(())
}

#[tauri::command]
pub async fn set_output_volume(state: State<'_, AppState>, volume: f32) -> Result<(), String> {
    state.audio.set_output_volume(volume).await;
    let mut cfg = load_config();
    cfg.output_volume = (volume * 100.0) as u32;
    save_config(&cfg);
    Ok(())
}

#[tauri::command]
pub async fn set_vad_threshold(state: State<'_, AppState>, threshold: f32) -> Result<(), String> {
    state.audio.set_vad_threshold(threshold).await;
    let mut cfg = load_config();
    cfg.vad_threshold = threshold;
    save_config(&cfg);
    Ok(())
}

#[tauri::command]
pub async fn set_theme(theme_name: String) -> Result<(), String> {
    let mut cfg = load_config();
    cfg.theme = theme_name;
    save_config(&cfg);
    Ok(())
}

#[tauri::command]
pub async fn set_language(lang: String) -> Result<(), String> {
    let mut cfg = load_config();
    cfg.language = lang;
    save_config(&cfg);
    Ok(())
}

#[tauri::command]
pub async fn set_dnd_mode(enabled: bool) -> Result<(), String> {
    let mut cfg = load_config();
    cfg.dnd_mode = enabled;
    save_config(&cfg);
    Ok(())
}

#[tauri::command]
pub async fn create_room(state: State<'_, AppState>, name: String) -> Result<(), String> {
    state.tcp.lock().await.send(serde_json::json!({
        "type": "create_room",
        "name": name
    }));
    Ok(())
}

#[tauri::command]
pub async fn delete_room(state: State<'_, AppState>, room_id: String) -> Result<(), String> {
    state.tcp.lock().await.send(serde_json::json!({
        "type": "delete_room",
        "room_id": room_id
    }));
    Ok(())
}

#[tauri::command]
pub async fn leave_room(state: State<'_, AppState>, room_id: String) -> Result<(), String> {
    state.tcp.lock().await.send(serde_json::json!({
        "type": "leave_room",
        "room_id": room_id
    }));
    Ok(())
}

#[tauri::command]
pub async fn create_channel(
    state: State<'_, AppState>,
    room_id: String,
    name: String,
    channel_type: Option<String>,
) -> Result<(), String> {
    state.tcp.lock().await.send(serde_json::json!({
        "type": "create_channel",
        "room_id": room_id,
        "name": name,
        "channel_type": channel_type.unwrap_or_else(|| "text".to_string())
    }));
    Ok(())
}

#[tauri::command]
pub async fn delete_channel(
    state: State<'_, AppState>,
    room_id: String,
    channel_id: String,
) -> Result<(), String> {
    state.tcp.lock().await.send(serde_json::json!({
        "type": "delete_channel",
        "room_id": room_id,
        "channel_id": channel_id
    }));
    Ok(())
}

#[tauri::command]
pub async fn rename_channel(
    state: State<'_, AppState>,
    room_id: String,
    channel_id: String,
    name: String,
) -> Result<(), String> {
    state.tcp.lock().await.send(serde_json::json!({
        "type": "rename_channel",
        "room_id": room_id,
        "channel_id": channel_id,
        "name": name
    }));
    Ok(())
}

#[tauri::command]
pub async fn send_friend_request(
    state: State<'_, AppState>,
    username: String,
) -> Result<(), String> {
    state.tcp.lock().await.send(serde_json::json!({
        "type": "send_friend_request",
        "username": username
    }));
    Ok(())
}

#[tauri::command]
pub async fn accept_friend_request(
    state: State<'_, AppState>,
    sender_id: String,
) -> Result<(), String> {
    state.tcp.lock().await.send(serde_json::json!({
        "type": "accept_friend_request",
        "sender_user_id": sender_id
    }));
    Ok(())
}

#[tauri::command]
pub async fn decline_friend_request(
    state: State<'_, AppState>,
    peer_id: String,
) -> Result<(), String> {
    state.tcp.lock().await.send(serde_json::json!({
        "type": "decline_friend_request",
        "peer_id": peer_id
    }));
    Ok(())
}

#[tauri::command]
pub async fn update_profile(
    state: State<'_, AppState>,
    display_name: Option<String>,
    status_text: Option<String>,
    avatar_color: Option<String>,
    banner_color: Option<String>,
    avatar_image: Option<String>,
    banner_image: Option<String>,
    bio: Option<String>,
) -> Result<(), String> {
    let mut msg = serde_json::json!({ "type": "update_profile" });
    if let Some(d) = display_name { msg["display_name"] = serde_json::Value::String(d); }
    if let Some(s) = status_text { msg["status_text"] = serde_json::Value::String(s); }
    if let Some(a) = avatar_color { msg["avatar_color"] = serde_json::Value::String(a); }
    if let Some(b) = banner_color { msg["banner_color"] = serde_json::Value::String(b); }
    if let Some(ai) = avatar_image { msg["avatar_image"] = serde_json::Value::String(ai); }
    if let Some(bi) = banner_image { msg["banner_image"] = serde_json::Value::String(bi); }
    if let Some(bio) = bio { msg["bio"] = serde_json::Value::String(bio); }

    state.tcp.lock().await.send(msg);
    Ok(())
}

#[tauri::command]
pub async fn change_password(
    state: State<'_, AppState>,
    old_pass: String,
    new_pass: String,
) -> Result<(), String> {
    state.tcp.lock().await.send(serde_json::json!({
        "type": "change_password",
        "old_password": old_pass,
        "new_password": new_pass
    }));
    Ok(())
}
