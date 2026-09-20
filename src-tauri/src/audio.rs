use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use std::collections::VecDeque;
use std::sync::atomic::{AtomicBool, AtomicU32, Ordering};
use std::sync::Arc;
use std::sync::Mutex as StdMutex;
use tauri::AppHandle;

pub struct AtomicF32(AtomicU32);

impl AtomicF32 {
    pub fn new(val: f32) -> Self {
        Self(AtomicU32::new(val.to_bits()))
    }
    pub fn get(&self) -> f32 {
        f32::from_bits(self.0.load(Ordering::Relaxed))
    }
    pub fn set(&self, val: f32) {
        self.0.store(val.to_bits(), Ordering::Relaxed);
    }
}

pub struct AudioManager {
    is_muted: Arc<AtomicBool>,
    is_deafened: Arc<AtomicBool>,
    mic_volume: Arc<AtomicF32>,
    output_volume: Arc<AtomicF32>,
    vad_threshold: Arc<AtomicF32>,
    ptt_mode: Arc<AtomicBool>,
    ptt_active: Arc<AtomicBool>,
    noise_suppression: Arc<AtomicBool>,
    pub is_testing_mic: Arc<AtomicBool>,
    selected_input_device: Arc<StdMutex<Option<u32>>>,
    selected_output_device: Arc<StdMutex<Option<u32>>>,
    voice_target: Arc<StdMutex<Option<(u8, String)>>>,
    udp_sender: Arc<StdMutex<Option<tokio::sync::mpsc::UnboundedSender<(u8, String, Vec<u8>)>>>>,
    incoming_playback_queue: Arc<StdMutex<VecDeque<f32>>>,
    mic_test_queue: Arc<StdMutex<VecDeque<f32>>>,

    capture_stream: Arc<StdMutex<Option<cpal::Stream>>>,
    playback_stream: Arc<StdMutex<Option<cpal::Stream>>>,
    mic_test_input_stream: Arc<StdMutex<Option<cpal::Stream>>>,
    mic_test_output_stream: Arc<StdMutex<Option<cpal::Stream>>>,
}

unsafe impl Send for AudioManager {}
unsafe impl Sync for AudioManager {}

impl AudioManager {
    pub fn new() -> Self {
        Self {
            is_muted: Arc::new(AtomicBool::new(false)),
            is_deafened: Arc::new(AtomicBool::new(false)),
            mic_volume: Arc::new(AtomicF32::new(1.0)),
            output_volume: Arc::new(AtomicF32::new(1.0)),
            vad_threshold: Arc::new(AtomicF32::new(0.005)),
            ptt_mode: Arc::new(AtomicBool::new(false)),
            ptt_active: Arc::new(AtomicBool::new(false)),
            noise_suppression: Arc::new(AtomicBool::new(false)),
            is_testing_mic: Arc::new(AtomicBool::new(false)),
            selected_input_device: Arc::new(StdMutex::new(None)),
            selected_output_device: Arc::new(StdMutex::new(None)),

            voice_target: Arc::new(StdMutex::new(None)),
            udp_sender: Arc::new(StdMutex::new(None)),
            incoming_playback_queue: Arc::new(StdMutex::new(VecDeque::with_capacity(48000))),
            mic_test_queue: Arc::new(StdMutex::new(VecDeque::with_capacity(48000))),

            capture_stream: Arc::new(StdMutex::new(None)),
            playback_stream: Arc::new(StdMutex::new(None)),
            mic_test_input_stream: Arc::new(StdMutex::new(None)),
            mic_test_output_stream: Arc::new(StdMutex::new(None)),
        }
    }

    pub fn set_selected_input(&self, id: Option<u32>) {
        if let Ok(mut lock) = self.selected_input_device.lock() {
            *lock = id;
        }
    }

    pub fn set_selected_output(&self, id: Option<u32>) {
        if let Ok(mut lock) = self.selected_output_device.lock() {
            *lock = id;
        }
    }

    pub fn set_voice_target(&self, target: Option<(u8, String)>) {
        if let Ok(mut lock) = self.voice_target.lock() {
            *lock = target;
        }
        if self.voice_target.lock().map(|g| g.is_none()).unwrap_or(true) {
            self.stop_capture_and_playback();
        }
    }

    pub fn set_udp_sender(&self, tx: Option<tokio::sync::mpsc::UnboundedSender<(u8, String, Vec<u8>)>>) {
        if let Ok(mut lock) = self.udp_sender.lock() {
            *lock = tx;
        }
    }

    pub fn get_input_device(host: &cpal::Host, id: Option<u32>) -> Option<cpal::Device> {
        if let Some(target_id) = id {
            if let Ok(mut devices) = host.input_devices() {
                if let Some(dev) = devices.nth(target_id as usize) {
                    return Some(dev);
                }
            }
        }
        host.default_input_device()
    }

    pub fn get_output_device(host: &cpal::Host, id: Option<u32>) -> Option<cpal::Device> {
        if let Some(target_id) = id {
            if let Ok(mut devices) = host.output_devices() {
                if let Some(dev) = devices.nth(target_id as usize) {
                    return Some(dev);
                }
            }
        }
        host.default_output_device()
    }

    pub fn set_muted(&self, val: bool) {
        self.is_muted.store(val, Ordering::SeqCst);
    }

    pub fn set_deafened(&self, val: bool) {
        self.is_deafened.store(val, Ordering::SeqCst);
    }

    pub fn set_mic_volume(&self, vol: f32) {
        self.mic_volume.set(vol.clamp(0.0, 2.0));
    }

    pub fn set_output_volume(&self, vol: f32) {
        self.output_volume.set(vol.clamp(0.0, 2.0));
    }

    pub fn set_vad_threshold(&self, thresh: f32) {
        self.vad_threshold.set(thresh.clamp(0.001, 0.2));
    }

    pub fn set_ptt_mode(&self, enabled: bool) {
        self.ptt_mode.store(enabled, Ordering::SeqCst);
    }

    pub fn set_ptt_active(&self, active: bool) {
        self.ptt_active.store(active, Ordering::SeqCst);
    }

    pub fn set_noise_suppression(&self, enabled: bool) {
        self.noise_suppression.store(enabled, Ordering::SeqCst);
    }

    pub fn get_devices() -> serde_json::Value {
        let host = cpal::default_host();
        let mut inputs = Vec::new();
        let mut outputs = Vec::new();

        if let Ok(devices) = host.input_devices() {
            for (idx, dev) in devices.enumerate() {
                if let Ok(name) = dev.name() {
                    inputs.push(serde_json::json!({
                        "id": idx as u32,
                        "name": name
                    }));
                }
            }
        }

        if let Ok(devices) = host.output_devices() {
            for (idx, dev) in devices.enumerate() {
                if let Ok(name) = dev.name() {
                    outputs.push(serde_json::json!({
                        "id": idx as u32,
                        "name": name
                    }));
                }
            }
        }

        let input_names: Vec<String> = inputs.iter().filter_map(|d| d.get("name").and_then(|v| v.as_str()).map(|s| s.to_string())).collect();
        let output_names: Vec<String> = outputs.iter().filter_map(|d| d.get("name").and_then(|v| v.as_str()).map(|s| s.to_string())).collect();

        serde_json::json!({
            "inputs": inputs,
            "outputs": outputs,
            "input": input_names,
            "output": output_names
        })
    }

    pub fn push_incoming_pcm(&self, pcm_bytes: &[u8]) {
        if pcm_bytes.is_empty() {
            return;
        }
        if let Ok(mut q) = self.incoming_playback_queue.lock() {
            for chunk in pcm_bytes.chunks_exact(2) {
                let sample_i16 = i16::from_le_bytes([chunk[0], chunk[1]]);
                let sample_f32 = sample_i16 as f32 / 32768.0;
                q.push_back(sample_f32);
            }
            // If latency exceeds 500ms (12000 samples @ 24kHz), trim older samples
            if q.len() > 12000 {
                let excess = q.len() - 4800;
                q.drain(0..excess);
            }
        }
    }

    pub fn ensure_playback_stream(&self, _app: &AppHandle) {
        if let Ok(lock) = self.playback_stream.lock() {
            if lock.is_some() {
                return;
            }
        }

        let host = cpal::default_host();
        let out_id = self.selected_output_device.lock().ok().and_then(|g| *g);
        let device = match Self::get_output_device(&host, out_id) {
            Some(d) => d,
            None => {
                log::warn!("No output audio device found");
                return;
            }
        };

        let config = match device.default_output_config() {
            Ok(c) => c,
            Err(e) => {
                log::error!("Failed to get output config: {}", e);
                return;
            }
        };

        let sample_rate = config.sample_rate().0 as f64;
        let channels = config.channels() as usize;
        let stream_config: cpal::StreamConfig = config.into();

        let queue = self.incoming_playback_queue.clone();
        let is_deafened = self.is_deafened.clone();
        let output_volume = self.output_volume.clone();

        let ratio = 24000.0 / sample_rate.max(1.0);
        let mut accum = 0.0f64;
        let mut current_sample = 0.0f32;

        let stream = device.build_output_stream(
            &stream_config,
            move |data: &mut [f32], _: &cpal::OutputCallbackInfo| {
                if is_deafened.load(Ordering::Relaxed) {
                    data.fill(0.0);
                    return;
                }

                let vol = output_volume.get();
                let num_frames = data.len() / channels.max(1);

                if let Ok(mut q) = queue.lock() {
                    for frame_idx in 0..num_frames {
                        accum += ratio;
                        while accum >= 1.0 {
                            accum -= 1.0;
                            current_sample = q.pop_front().unwrap_or(0.0);
                        }
                        let out_val = current_sample * vol;
                        for ch in 0..channels {
                            data[frame_idx * channels + ch] = out_val;
                        }
                    }
                } else {
                    data.fill(0.0);
                }
            },
            |err| log::error!("Audio playback error: {}", err),
            None,
        );

        if let Ok(s) = stream {
            let _ = s.play();
            if let Ok(mut lock) = self.playback_stream.lock() {
                *lock = Some(s);
            }
        }
    }

    pub fn ensure_capture_stream(&self, app: &AppHandle) {
        if let Ok(lock) = self.capture_stream.lock() {
            if lock.is_some() {
                return;
            }
        }

        let host = cpal::default_host();
        let in_id = self.selected_input_device.lock().ok().and_then(|g| *g);
        let device = match Self::get_input_device(&host, in_id) {
            Some(d) => d,
            None => {
                log::warn!("No input audio device found");
                return;
            }
        };

        let config = match device.default_input_config() {
            Ok(c) => c,
            Err(e) => {
                log::error!("Failed to get input config: {}", e);
                return;
            }
        };

        let in_sample_rate = config.sample_rate().0 as f64;
        let in_channels = config.channels() as usize;
        let stream_config: cpal::StreamConfig = config.into();

        let is_muted = self.is_muted.clone();
        let is_deafened = self.is_deafened.clone();
        let ptt_mode = self.ptt_mode.clone();
        let ptt_active = self.ptt_active.clone();
        let mic_volume = self.mic_volume.clone();
        let vad_threshold = self.vad_threshold.clone();
        let voice_target = self.voice_target.clone();
        let udp_sender = self.udp_sender.clone();
        let app_clone = app.clone();

        let ns_mode = self.noise_suppression.clone();

        let ratio = 48000.0 / in_sample_rate.max(1.0);
        let mut accum = 0.0f64;
        let mut outgoing_buf: Vec<u8> = Vec::with_capacity(1920);
        let mut last_speaking = false;
        
        // buffers for 48kHz and nnnoiseless
        let mut buf_48k = Vec::new();
        let mut denoise = nnnoiseless::DenoiseState::new();

        let stream = device.build_input_stream(
            &stream_config,
            move |data: &[f32], _: &cpal::InputCallbackInfo| {
                let muted = is_muted.load(Ordering::Relaxed) || is_deafened.load(Ordering::Relaxed);
                let mic_vol = mic_volume.get();
                let vad_thresh = vad_threshold.get();
                let num_frames = data.len() / in_channels.max(1);
                let use_ns = ns_mode.load(Ordering::Relaxed);

                let mut sum_sq = 0.0f32;
                for frame_idx in 0..num_frames {
                    let mut s = 0.0f32;
                    for ch in 0..in_channels {
                        s += data[frame_idx * in_channels + ch];
                    }
                    s = (s / in_channels as f32) * mic_vol;
                    sum_sq += s * s;
                    
                    // Resample to 48kHz for noise suppression processing
                    accum += ratio;
                    while accum >= 1.0 {
                        accum -= 1.0;
                        buf_48k.push(s);
                    }
                }
                
                let rms = (sum_sq / num_frames.max(1) as f32).sqrt();

                let is_ptt = ptt_mode.load(Ordering::Relaxed);
                let speaking = if muted {
                    false
                } else if is_ptt {
                    ptt_active.load(Ordering::Relaxed)
                } else {
                    rms > vad_thresh
                };

                if speaking != last_speaking {
                    last_speaking = speaking;
                    crate::net_tcp::dispatch_event(&app_clone, "local_speaking", serde_json::json!({
                        "is_speaking": speaking
                    }));
                }

                if speaking {
                    // Process through nnnoiseless in 480-sample blocks
                    while buf_48k.len() >= 480 {
                        let chunk_in: Vec<f32> = buf_48k.drain(0..480).collect();
                        let mut chunk_out = [0.0f32; 480];
                        
                        if use_ns {
                            denoise.process_frame(&mut chunk_out, &chunk_in);
                        } else {
                            chunk_out.copy_from_slice(&chunk_in);
                        }
                        
                        // Resample back to 24kHz for Opus/Network transmission (drop every other sample)
                        for i in (0..480).step_by(2) {
                            let clamped = chunk_out[i].clamp(-1.0, 1.0);
                            let sample_i16 = (clamped * 32767.0) as i16;
                            outgoing_buf.extend_from_slice(&sample_i16.to_le_bytes());
                        }
                    }

                    // Flush complete 20ms frames (480 samples at 24kHz * 2 bytes = 960 bytes)
                    while outgoing_buf.len() >= 960 {
                        let frame: Vec<u8> = outgoing_buf.drain(0..960).collect();
                        if let Ok(target_guard) = voice_target.lock() {
                            if let Some((pkt_type, ref target_id)) = *target_guard {
                                if let Ok(sender_guard) = udp_sender.lock() {
                                    if let Some(tx) = &*sender_guard {
                                        let _ = tx.send((pkt_type, target_id.clone(), frame));
                                    }
                                }
                            }
                        }
                    }
                } else {
                    buf_48k.clear();
                    outgoing_buf.clear();
                }
            },
            |err| log::error!("Audio capture error: {}", err),
            None,
        );

        if let Ok(s) = stream {
            let _ = s.play();
            if let Ok(mut lock) = self.capture_stream.lock() {
                *lock = Some(s);
            }
        }
    }

    pub fn ensure_capture_and_playback(&self, app: &AppHandle) {
        self.ensure_capture_stream(app);
        self.ensure_playback_stream(app);
    }

    pub fn stop_capture_and_playback(&self) {
        if let Ok(mut lock) = self.capture_stream.lock() {
            *lock = None;
        }
        if let Ok(mut lock) = self.playback_stream.lock() {
            *lock = None;
        }
        if let Ok(mut q) = self.incoming_playback_queue.lock() {
            q.clear();
        }
    }

    pub fn start_mic_test_loop(&self, app: AppHandle) {
        self.stop_mic_test_loop(app.clone());
        self.is_testing_mic.store(true, Ordering::SeqCst);

        let host = cpal::default_host();
        let in_id = self.selected_input_device.lock().ok().and_then(|g| *g);
        let out_id = self.selected_output_device.lock().ok().and_then(|g| *g);

        let in_dev = Self::get_input_device(&host, in_id);
        let out_dev = Self::get_output_device(&host, out_id);

        if in_dev.is_none() || out_dev.is_none() {
            log::warn!("Missing audio device for mic test");
            return;
        }

        let in_device = in_dev.unwrap();
        let out_device = out_dev.unwrap();

        let in_config = match in_device.default_input_config() {
            Ok(c) => c,
            Err(_) => return,
        };
        let out_config = match out_device.default_output_config() {
            Ok(c) => c,
            Err(_) => return,
        };

        let in_sample_rate = in_config.sample_rate().0 as f64;
        let in_channels = in_config.channels() as usize;
        let out_sample_rate = out_config.sample_rate().0 as f64;
        let out_channels = out_config.channels() as usize;

        let in_stream_config: cpal::StreamConfig = in_config.into();
        let out_stream_config: cpal::StreamConfig = out_config.into();

        let queue = self.mic_test_queue.clone();
        if let Ok(mut q) = queue.lock() {
            q.clear();
        }

        let is_testing = self.is_testing_mic.clone();
        let app_clone = app.clone();
        let mic_vol = self.mic_volume.clone();

        // Build mic test input stream
        let queue_in = queue.clone();
        let is_testing_in = is_testing.clone();
        let in_stream = in_device.build_input_stream(
            &in_stream_config,
            move |data: &[f32], _: &cpal::InputCallbackInfo| {
                if !is_testing_in.load(Ordering::Relaxed) {
                    return;
                }
                let vol = mic_vol.get();
                let num_frames = data.len() / in_channels.max(1);

                let mut sum_sq = 0.0f32;
                for frame_idx in 0..num_frames {
                    let mut s = 0.0f32;
                    for ch in 0..in_channels {
                        s += data[frame_idx * in_channels + ch];
                    }
                    s = (s / in_channels as f32) * vol;
                    sum_sq += s * s;
                }
                let rms = (sum_sq / num_frames.max(1) as f32).sqrt();
                let pct = ((rms * 500.0) as u32).min(100);
                let speaking = rms > 0.005;

                crate::net_tcp::dispatch_event(&app_clone, "mic_test_level", serde_json::json!({
                    "level": pct,
                    "speaking": speaking
                }));

                // Push samples into loopback queue for headphones
                if let Ok(mut q) = queue_in.lock() {
                    for frame_idx in 0..num_frames {
                        let mut s = 0.0f32;
                        for ch in 0..in_channels {
                            s += data[frame_idx * in_channels + ch];
                        }
                        s = (s / in_channels as f32) * vol;
                        q.push_back(s);
                    }
                    // Prevent latency buildup: cap loopback queue to ~100ms
                    let max_samples = (in_sample_rate * 0.1) as usize;
                    if q.len() > max_samples {
                        let excess = q.len() - max_samples;
                        q.drain(0..excess);
                    }
                }
            },
            |err| log::warn!("Mic test input error: {}", err),
            None,
        );

        // Build mic test output stream (loopback to headphones)
        let queue_out = queue.clone();
        let is_testing_out = is_testing.clone();
        let out_vol = self.output_volume.clone();
        let ratio = in_sample_rate / out_sample_rate.max(1.0);
        let mut accum = 0.0f64;
        let mut curr_sample = 0.0f32;

        let out_stream = out_device.build_output_stream(
            &out_stream_config,
            move |data: &mut [f32], _: &cpal::OutputCallbackInfo| {
                if !is_testing_out.load(Ordering::Relaxed) {
                    data.fill(0.0);
                    return;
                }

                let vol = out_vol.get();
                let num_frames = data.len() / out_channels.max(1);

                if let Ok(mut q) = queue_out.lock() {
                    for frame_idx in 0..num_frames {
                        accum += ratio;
                        while accum >= 1.0 {
                            accum -= 1.0;
                            curr_sample = q.pop_front().unwrap_or(0.0);
                        }
                        let out_val = curr_sample * vol;
                        for ch in 0..out_channels {
                            data[frame_idx * out_channels + ch] = out_val;
                        }
                    }
                } else {
                    data.fill(0.0);
                }
            },
            |err| log::warn!("Mic test output error: {}", err),
            None,
        );

        if let (Ok(in_s), Ok(out_s)) = (in_stream, out_stream) {
            let _ = in_s.play();
            let _ = out_s.play();
            if let Ok(mut lock) = self.mic_test_input_stream.lock() {
                *lock = Some(in_s);
            }
            if let Ok(mut lock) = self.mic_test_output_stream.lock() {
                *lock = Some(out_s);
            }
        }
    }

    pub fn stop_mic_test_loop(&self, app: AppHandle) {
        self.is_testing_mic.store(false, Ordering::SeqCst);
        if let Ok(mut lock) = self.mic_test_input_stream.lock() {
            *lock = None;
        }
        if let Ok(mut lock) = self.mic_test_output_stream.lock() {
            *lock = None;
        }
        if let Ok(mut q) = self.mic_test_queue.lock() {
            q.clear();
        }
        crate::net_tcp::dispatch_event(&app, "mic_test_level", serde_json::json!({
            "level": 0,
            "speaking": false
        }));
    }

    pub fn restart_streams_if_active(&self, app: &AppHandle) {
        if self.is_testing_mic.load(Ordering::Relaxed) {
            self.start_mic_test_loop(app.clone());
        }
        let voice_active = self.voice_target.lock().map(|g| g.is_some()).unwrap_or(false);
        if voice_active {
            self.stop_capture_and_playback();
            self.ensure_capture_and_playback(app);
        }
    }
}
