use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use tokio::net::UdpSocket;
use tokio::sync::Mutex;
use tauri::{AppHandle, Emitter};

use crate::protocol::{
    pack_udp_audio, unpack_udp_audio, UnpackedUdp, UDP_TYPE_PING, UDP_TYPE_REGISTER,
    UDP_TYPE_SPEAKING,
};

pub struct UdpVoiceClient {
    socket: Arc<Mutex<Option<Arc<UdpSocket>>>>,
    is_running: Arc<AtomicBool>,
    server_addr: Arc<Mutex<String>>,
    user_id: Arc<Mutex<String>>,
}

impl UdpVoiceClient {
    pub fn new() -> Self {
        Self {
            socket: Arc::new(Mutex::new(None)),
            is_running: Arc::new(AtomicBool::new(false)),
            server_addr: Arc::new(Mutex::new(String::new())),
            user_id: Arc::new(Mutex::new(String::new())),
        }
    }

    pub async fn start(
        &self,
        uid: String,
        host: String,
        port: u16,
        app: AppHandle,
    ) -> Result<(), String> {
        self.stop().await;

        let sock = UdpSocket::bind("0.0.0.0:0")
            .await
            .map_err(|e| format!("UDP bind error: {}", e))?;

        let sock_arc = Arc::new(sock);
        *self.socket.lock().await = Some(sock_arc.clone());
        *self.user_id.lock().await = uid.clone();
        let target_addr = format!("{}:{}", host, port);
        *self.server_addr.lock().await = target_addr.clone();
        self.is_running.store(true, Ordering::SeqCst);

        // Send registration
        let reg_pkt = pack_udp_audio(UDP_TYPE_REGISTER, 0, &uid, "", b"");
        let _ = sock_arc.send_to(&reg_pkt, &target_addr).await;

        // Spawn UDP receive loop
        let is_running_rx = self.is_running.clone();
        let sock_rx = sock_arc.clone();
        let app_rx = app.clone();
        tokio::spawn(async move {
            let mut buf = [0u8; 65535];
            while is_running_rx.load(Ordering::Relaxed) {
                match sock_rx.recv_from(&mut buf).await {
                    Ok((n, _src)) => {
                        if let Some(pkt) = unpack_udp_audio(&buf[..n]) {
                            Self::handle_packet(&app_rx, pkt);
                        }
                    }
                    Err(e) => {
                        if is_running_rx.load(Ordering::Relaxed) {
                            log::error!("UDP recv error: {}", e);
                        }
                        break;
                    }
                }
            }
        });

        // Spawn ping loop (keepalive)
        let is_running_ping = self.is_running.clone();
        let sock_ping = sock_arc.clone();
        let uid_ping = uid.clone();
        let addr_ping = target_addr.clone();
        tokio::spawn(async move {
            let mut seq = 0u32;
            while is_running_ping.load(Ordering::Relaxed) {
                tokio::time::sleep(tokio::time::Duration::from_secs(5)).await;
                if !is_running_ping.load(Ordering::Relaxed) {
                    break;
                }
                seq = seq.wrapping_add(1);
                let ping = pack_udp_audio(UDP_TYPE_PING, seq, &uid_ping, "", b"");
                let _ = sock_ping.send_to(&ping, &addr_ping).await;
            }
        });

        Ok(())
    }

    pub async fn stop(&self) {
        self.is_running.store(false, Ordering::SeqCst);
        *self.socket.lock().await = None;
    }

    pub async fn send_packet(&self, pkt_type: u8, target_id: &str, payload: &[u8]) {
        if !self.is_running.load(Ordering::Relaxed) {
            return;
        }
        let sock = self.socket.lock().await;
        if let Some(s) = &*sock {
            let uid = self.user_id.lock().await;
            let addr = self.server_addr.lock().await;
            let pkt = pack_udp_audio(pkt_type, 0, &uid, target_id, payload);
            let _ = s.send_to(&pkt, &*addr).await;
        }
    }

    fn handle_packet(app: &AppHandle, pkt: UnpackedUdp) {
        match pkt.pkt_type {
            UDP_TYPE_SPEAKING => {
                let is_speaking = pkt.payload.first().copied().unwrap_or(0) != 0;
                let _ = app.emit("vimcord://event", serde_json::json!({
                    "event": "peer_speaking",
                    "payload": {
                        "user_id": pkt.sender_id,
                        "is_speaking": is_speaking
                    }
                }));
            }
            _ => {}
        }
    }
}
