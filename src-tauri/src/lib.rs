pub mod audio;
pub mod commands;
pub mod config;
pub mod net_tcp;
pub mod net_udp;
pub mod protocol;

use commands::AppState;
use tauri::{tray::TrayIconBuilder, Manager};

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_notification::init())
        .manage(AppState::new())
        .setup(|app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }

            // Setup system tray
            let _ = TrayIconBuilder::new()
                .tooltip("VimCord")
                .on_tray_icon_event(|tray, event| {
                    if let tauri::tray::TrayIconEvent::Click { button: tauri::tray::MouseButton::Left, .. } = event {
                        let app = tray.app_handle();
                        if let Some(window) = app.get_webview_window("main") {
                            let _ = window.show();
                            let _ = window.set_focus();
                        }
                    }
                })
                .build(app);

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::get_initial_state,
            commands::minimize_window,
            commands::toggle_maximize_window,
            commands::close_window,
            commands::set_window_size,
            commands::quit_app,
            commands::login,
            commands::register,
            commands::logout,
            commands::send_chat_message,
            commands::delete_message,
            commands::get_history,
            commands::open_file_dialog,
            commands::save_file_to_disk,
            commands::join_voice,
            commands::leave_voice,
            commands::start_call,
            commands::accept_call,
            commands::decline_call,
            commands::end_call,
            commands::set_mic_muted,
            commands::set_deafened,
            commands::set_mic_volume,
            commands::set_output_volume,
            commands::set_vad_threshold,
            commands::set_theme,
            commands::set_language,
            commands::set_dnd_mode,
            commands::create_room,
            commands::delete_room,
            commands::leave_room,
            commands::create_channel,
            commands::delete_channel,
            commands::rename_channel,
            commands::send_friend_request,
            commands::accept_friend_request,
            commands::decline_friend_request,
            commands::update_profile,
            commands::change_password,
            commands::reconnect,
            commands::create_room_invite,
            commands::join_room_by_invite,
            commands::get_room_members,
            commands::get_audio_devices,
            commands::set_audio_devices,
            commands::set_ptt_config,
            commands::set_noise_suppression,
            commands::set_stream_settings,
            commands::start_mic_test,
            commands::stop_mic_test,
            commands::start_voice_record,
            commands::stop_voice_record,
            commands::play_voice_message,
            commands::start_screen_share,
            commands::stop_screen_share,
            commands::send_screen_frame,
            commands::record_keybind_start,
            commands::get_clipboard_image,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
