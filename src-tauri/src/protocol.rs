//! Protocol definitions and packet serialization matching Python server

pub const DEFAULT_HOST: &str = "194.226.123.199";
pub const DEFAULT_TCP_PORT: u16 = 9988;
pub const DEFAULT_UDP_PORT: u16 = 9989;

pub const SAMPLE_RATE: u32 = 24000;
pub const CHANNELS: u16 = 1;
pub const FRAME_DURATION_MS: u32 = 20;
pub const SAMPLES_PER_FRAME: usize = (SAMPLE_RATE * FRAME_DURATION_MS / 1000) as usize; // 480
pub const BYTES_PER_SAMPLE: usize = 2;
pub const BYTES_PER_FRAME: usize = SAMPLES_PER_FRAME * BYTES_PER_SAMPLE * (CHANNELS as usize); // 960

pub const UDP_MAGIC: &[u8; 2] = b"VC";
pub const UDP_TYPE_REGISTER: u8 = 1;
pub const UDP_TYPE_CHANNEL_AUDIO: u8 = 2;
pub const UDP_TYPE_DM_AUDIO: u8 = 3;
pub const UDP_TYPE_PING: u8 = 4;
pub const UDP_TYPE_SPEAKING: u8 = 5;
pub const UDP_TYPE_SCREEN_FRAME: u8 = 6;
pub const UDP_TYPE_SCREEN_CHUNK: u8 = 7;

pub const UDP_HEADER_SIZE: usize = 9;

/// Packs an audio/signaling packet:
/// Magic: 2 bytes (VC)
/// Type: 1 byte (B)
/// Seq: 4 bytes big-endian (I)
/// Sender ID len: 1 byte (B)
/// Target ID len: 1 byte (B)
/// sender_id_bytes + target_id_bytes + payload
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
