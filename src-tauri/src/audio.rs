use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use tokio::sync::Mutex;
use tauri::{AppHandle, Emitter};

pub struct AudioManager {
    is_muted: Arc<AtomicBool>,
    is_deafened: Arc<AtomicBool>,
    mic_volume: Arc<Mutex<f32>>,
    output_volume: Arc<Mutex<f32>>,
    vad_threshold: Arc<Mutex<f32>>,
    ptt_mode: Arc<AtomicBool>,
    ptt_active: Arc<AtomicBool>,
}

// Safety wrapper or channel-based stream holder so AudioManager is Send + Sync
unsafe impl Send for AudioManager {}
unsafe impl Sync for AudioManager {}

impl AudioManager {
    pub fn new() -> Self {
        Self {
            is_muted: Arc::new(AtomicBool::new(false)),
            is_deafened: Arc::new(AtomicBool::new(false)),
            mic_volume: Arc::new(Mutex::new(1.0)),
            output_volume: Arc::new(Mutex::new(1.0)),
            vad_threshold: Arc::new(Mutex::new(0.005)),
            ptt_mode: Arc::new(AtomicBool::new(false)),
            ptt_active: Arc::new(AtomicBool::new(false)),
        }
    }

    pub fn set_muted(&self, val: bool) {
        self.is_muted.store(val, Ordering::SeqCst);
    }

    pub fn set_deafened(&self, val: bool) {
        self.is_deafened.store(val, Ordering::SeqCst);
    }

    pub async fn set_mic_volume(&self, vol: f32) {
        *self.mic_volume.lock().await = vol.clamp(0.0, 2.0);
    }

    pub async fn set_output_volume(&self, vol: f32) {
        *self.output_volume.lock().await = vol.clamp(0.0, 2.0);
    }

    pub async fn set_vad_threshold(&self, thresh: f32) {
        *self.vad_threshold.lock().await = thresh.clamp(0.001, 0.2);
    }

    pub fn set_ptt_mode(&self, enabled: bool) {
        self.ptt_mode.store(enabled, Ordering::SeqCst);
    }

    pub fn set_ptt_active(&self, active: bool) {
        self.ptt_active.store(active, Ordering::SeqCst);
    }

    pub fn get_devices() -> serde_json::Value {
        let host = cpal::default_host();
        let mut input_names = Vec::new();
        let mut output_names = Vec::new();

        if let Ok(devices) = host.input_devices() {
            for dev in devices {
                if let Ok(name) = dev.name() {
                    input_names.push(name);
                }
            }
        }

        if let Ok(devices) = host.output_devices() {
            for dev in devices {
                if let Ok(name) = dev.name() {
                    output_names.push(name);
                }
            }
        }

        serde_json::json!({
            "input": input_names,
            "output": output_names
        })
    }

    pub fn start_capture(&self, app: AppHandle) -> Result<(), String> {
        let host = cpal::default_host();
        let device = match host.default_input_device() {
            Some(d) => d,
            None => return Ok(()),
        };

        let config: cpal::StreamConfig = match device.default_input_config() {
            Ok(c) => c.into(),
            Err(_) => return Ok(()),
        };

        let is_muted = self.is_muted.clone();
        let ptt_mode = self.ptt_mode.clone();
        let ptt_active = self.ptt_active.clone();
        let app_clone = app.clone();

        std::thread::spawn(move || {
            let stream = device.build_input_stream(
                &config,
                move |data: &[f32], _: &cpal::InputCallbackInfo| {
                    if is_muted.load(Ordering::Relaxed) {
                        return;
                    }

                    let mut sum = 0.0;
                    for &s in data {
                        sum += s * s;
                    }
                    let rms = (sum / (data.len() as f32).max(1.0)).sqrt();

                    let is_ptt = ptt_mode.load(Ordering::Relaxed);
                    let speaking = if is_ptt {
                        ptt_active.load(Ordering::Relaxed)
                    } else {
                        rms > 0.005
                    };

                    let _ = app_clone.emit("vimcord://event", serde_json::json!({
                        "event": "local_speaking",
                        "payload": {
                            "is_speaking": speaking
                        }
                    }));
                },
                |err| log::error!("Audio capture error: {}", err),
                None,
            );

            if let Ok(s) = stream {
                let _ = s.play();
                loop {
                    std::thread::sleep(std::time::Duration::from_secs(10));
                }
            }
        });

        Ok(())
    }
}
