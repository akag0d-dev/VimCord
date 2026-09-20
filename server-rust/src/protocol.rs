#![allow(dead_code)]

pub const DEFAULT_HOST: &str = "0.0.0.0";
pub const DEFAULT_TCP_PORT: u16 = 9988;
pub const DEFAULT_UDP_PORT: u16 = 9989;

pub const UDP_MAGIC: &[u8; 2] = b"VC";
pub const UDP_TYPE_REGISTER: u8 = 1;
pub const UDP_TYPE_CHANNEL_AUDIO: u8 = 2;
pub const UDP_TYPE_DM_AUDIO: u8 = 3;
pub const UDP_TYPE_PING: u8 = 4;
pub const UDP_TYPE_SPEAKING: u8 = 5;
pub const UDP_TYPE_SCREEN_FRAME: u8 = 6;
pub const UDP_TYPE_SCREEN_CHUNK: u8 = 7;

pub const UDP_HEADER_SIZE: usize = 9;

pub fn get_dm_chat_key(user_a: &str, user_b: &str) -> String {
    if user_a <= user_b {
        format!("dm:{}:{}", user_a, user_b)
    } else {
        format!("dm:{}:{}", user_b, user_a)
    }
}

pub fn pack_udp_audio(pkt_type: u8, seq: u32, sender_id: &str, target_id: &str, payload: &[u8]) -> Vec<u8> {
    let s_bytes = sender_id.as_bytes();
    let s_len = s_bytes.len().min(255) as u8;
    let t_bytes = target_id.as_bytes();
    let t_len = t_bytes.len().min(255) as u8;

    let mut buf = Vec::with_capacity(UDP_HEADER_SIZE + s_len as usize + t_len as usize + payload.len());
    buf.extend_from_slice(UDP_MAGIC);
    buf.push(pkt_type);
    buf.extend_from_slice(&seq.to_be_bytes());
    buf.push(s_len);
    buf.push(t_len);
    buf.extend_from_slice(&s_bytes[..s_len as usize]);
    buf.extend_from_slice(&t_bytes[..t_len as usize]);
    buf.extend_from_slice(payload);
    buf
}

#[derive(Debug, Clone)]
pub struct UnpackedUdp {
    pub pkt_type: u8,
    pub seq: u32,
    pub sender_id: String,
    pub target_id: String,
    pub payload: Vec<u8>,
}

pub fn unpack_udp_audio(data: &[u8]) -> Option<UnpackedUdp> {
    if data.len() < UDP_HEADER_SIZE {
        return None;
    }
    if &data[0..2] != UDP_MAGIC {
        return None;
    }
    let pkt_type = data[2];
    let seq = u32::from_be_bytes([data[3], data[4], data[5], data[6]]);
    let s_len = data[7] as usize;
    let t_len = data[8] as usize;

    let offset = UDP_HEADER_SIZE;
    if data.len() < offset + s_len + t_len {
        return None;
    }

    let sender_id = String::from_utf8_lossy(&data[offset..offset + s_len]).to_string();
    let offset = offset + s_len;
    let target_id = String::from_utf8_lossy(&data[offset..offset + t_len]).to_string();
    let offset = offset + t_len;
    let payload = data[offset..].to_vec();

    Some(UnpackedUdp {
        pkt_type,
        seq,
        sender_id,
        target_id,
        payload,
    })
}
