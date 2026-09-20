use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;

use crate::protocol::{DEFAULT_HOST, DEFAULT_TCP_PORT, DEFAULT_UDP_PORT};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ClientConfig {
    #[serde(default = "default_host")]
    pub host: String,
    #[serde(default = "default_tcp_port")]
    pub tcp_port: u16,
    #[serde(default = "default_udp_port")]
    pub udp_port: u16,
    #[serde(default)]
    pub username: String,
    #[serde(default)]
    pub saved_username: String,
    #[serde(default)]
    pub saved_password: String,
    #[serde(default)]
    pub auto_login: bool,
    #[serde(default = "default_lang")]
    pub language: String,
    #[serde(default = "default_theme")]
    pub theme: String,
    #[serde(default)]
    pub dnd_mode: bool,
    #[serde(default)]
    pub ptt_mode: bool,
    #[serde(default = "default_ptt_key")]
    pub ptt_key: String,
    #[serde(default = "default_vad_threshold")]
    pub vad_threshold: f32,
    #[serde(default)]
    pub input_device: Option<u32>,
    #[serde(default)]
    pub output_device: Option<u32>,
    #[serde(default = "default_mic_volume")]
    pub mic_volume: u32,
    #[serde(default = "default_output_volume")]
    pub output_volume: u32,
    #[serde(default = "default_stream_volume")]
    pub stream_volume: u32,
    #[serde(default = "default_call_volume")]
    pub call_volume: u32,
    #[serde(default = "default_stream_res")]
    pub stream_resolution: String,
    #[serde(default = "default_stream_fps")]
    pub stream_fps: u32,
    #[serde(default = "default_stream_quality")]
    pub stream_quality: u32,
}

fn default_host() -> String { DEFAULT_HOST.to_string() }
fn default_tcp_port() -> u16 { DEFAULT_TCP_PORT }
fn default_udp_port() -> u16 { DEFAULT_UDP_PORT }
fn default_lang() -> String { "en".to_string() }
fn default_theme() -> String { "dark".to_string() }
fn default_ptt_key() -> String { "Space".to_string() }
fn default_vad_threshold() -> f32 { 0.005 }
fn default_mic_volume() -> u32 { 100 }
fn default_output_volume() -> u32 { 100 }
fn default_stream_volume() -> u32 { 100 }
fn default_call_volume() -> u32 { 100 }
fn default_stream_res() -> String { "720p".to_string() }
fn default_stream_fps() -> u32 { 15 }
fn default_stream_quality() -> u32 { 45 }

impl Default for ClientConfig {
    fn default() -> Self {
        Self {
            host: default_host(),
            tcp_port: default_tcp_port(),
            udp_port: default_udp_port(),
            username: String::new(),
            saved_username: String::new(),
            saved_password: String::new(),
            auto_login: false,
            language: default_lang(),
            theme: default_theme(),
            dnd_mode: false,
            ptt_mode: false,
            ptt_key: default_ptt_key(),
            vad_threshold: default_vad_threshold(),
            input_device: None,
            output_device: None,
            mic_volume: default_mic_volume(),
            output_volume: default_output_volume(),
            stream_volume: default_stream_volume(),
            call_volume: default_call_volume(),
            stream_resolution: default_stream_res(),
            stream_fps: default_stream_fps(),
            stream_quality: default_stream_quality(),
        }
    }
}

pub fn get_appdata_dir() -> PathBuf {
    if let Some(mut base) = dirs::data_dir() {
        base.push("VimCord");
        let _ = fs::create_dir_all(&base);
        base
    } else {
        PathBuf::from(".")
    }
}

pub fn get_config_file() -> PathBuf {
    get_appdata_dir().join("config.json")
}

pub fn load_config() -> ClientConfig {
    let path = get_config_file();
    if path.exists() {
        if let Ok(content) = fs::read_to_string(&path) {
            if let Ok(mut cfg) = serde_json::from_str::<ClientConfig>(&content) {
                if cfg.host.is_empty() || cfg.host == "127.0.0.1" || cfg.host == "localhost" {
                    cfg.host = DEFAULT_HOST.to_string();
                }
                if cfg.tcp_port == 0 {
                    cfg.tcp_port = DEFAULT_TCP_PORT;
                }
                if cfg.udp_port == 0 {
                    cfg.udp_port = DEFAULT_UDP_PORT;
                }
                return cfg;
            }
        }
    }
    ClientConfig::default()
}

pub fn save_config(cfg: &ClientConfig) {
    let path = get_config_file();
    if let Ok(json_str) = serde_json::to_string_pretty(cfg) {
        let _ = fs::write(path, json_str);
    }
}
