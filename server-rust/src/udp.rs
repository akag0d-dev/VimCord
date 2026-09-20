use std::sync::Arc;
use tokio::net::UdpSocket;
use tracing::{debug, error, info};

use crate::protocol::*;
use crate::state::SharedState;

pub async fn run_udp_server(state: SharedState, host: &str, port: u16) -> anyhow::Result<()> {
    let addr = format!("{}:{}", host, port);
    let socket = Arc::new(UdpSocket::bind(&addr).await?);
    info!("UDP Voice & Screen Router listening on {}", addr);

    let mut buf = vec![0u8; 65536];

    loop {
        let (len, peer) = match socket.recv_from(&mut buf).await {
            Ok(res) => res,
            Err(e) => {
                error!("UDP recv_from error: {}", e);
                continue;
            }
        };

        if len < UDP_HEADER_SIZE {
            continue;
        }

        let packet = match unpack_udp_audio(&buf[..len]) {
            Some(p) => p,
            None => continue,
        };

        let data = &buf[..len];

        match packet.pkt_type {
            UDP_TYPE_REGISTER | UDP_TYPE_PING => {
                {
                    let mut s = state.write().await;
                    s.register_udp(&packet.sender_id, peer);
                }
                // Send ping ACK back so client knows UDP socket is open and working
                let ack = pack_udp_audio(UDP_TYPE_PING, packet.seq, "server", &packet.sender_id, &[]);
                let _ = socket.send_to(&ack, peer).await;
            }
            UDP_TYPE_CHANNEL_AUDIO | UDP_TYPE_SPEAKING => {
                let recipients = {
                    let s = state.read().await;
                    s.get_channel_voice_recipients(&packet.sender_id, &packet.target_id)
                };
                for r_addr in recipients {
                    let _ = socket.send_to(data, r_addr).await;
                }
            }
            UDP_TYPE_DM_AUDIO => {
                let peer_addr = {
                    let s = state.read().await;
                    s.get_call_peer_udp(&packet.sender_id, &packet.target_id)
                };
                if let Some(r_addr) = peer_addr {
                    let _ = socket.send_to(data, r_addr).await;
                }
            }
            UDP_TYPE_SCREEN_FRAME | UDP_TYPE_SCREEN_CHUNK => {
                let recipients = {
                    let s = state.read().await;
                    s.get_channel_voice_recipients(&packet.sender_id, &packet.target_id)
                };
                if !recipients.is_empty() {
                    for r_addr in recipients {
                        let _ = socket.send_to(data, r_addr).await;
                    }
                } else {
                    let peer_addr = {
                        let s = state.read().await;
                        s.get_call_peer_udp(&packet.sender_id, &packet.target_id)
                    };
                    if let Some(r_addr) = peer_addr {
                        let _ = socket.send_to(data, r_addr).await;
                    }
                }
            }
            _ => {
                debug!("Unknown UDP packet type: {}", packet.pkt_type);
            }
        }
    }
}
