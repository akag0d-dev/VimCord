/**
 * Tauri IPC Polyfill Bridge for VimCord.
 * Seamlessly maps `window.pywebview.api.*` calls to Tauri v2 `invoke(...)`
 * and routes events to `window.onVimCordEvent(...)`.
 * This preserves 100% of the existing frontend logic and styling.
 */

(function() {
    console.log("[VimCord Tauri Bridge] Initializing...");

    // Safe invoke accessor for Tauri v2
    function getInvoke() {
        if (window.__TAURI__ && window.__TAURI__.core && typeof window.__TAURI__.core.invoke === 'function') {
            return window.__TAURI__.core.invoke;
        }
        if (window.__TAURI_INTERNALS__ && typeof window.__TAURI_INTERNALS__.invoke === 'function') {
            return window.__TAURI_INTERNALS__.invoke;
        }
        return null;
    }

    function invoke(cmd, args = {}) {
        const inv = getInvoke();
        if (!inv) {
            console.warn(`[VimCord Bridge] Tauri invoke not yet ready for: ${cmd}`);
            return Promise.reject(new Error(`Tauri invoke not available for ${cmd}`));
        }
        return inv(cmd, args);
    }

    // Global event dispatcher invoked either by Rust eval or by Tauri event listener
    window.dispatchVimCordEvent = function(eventName, payload) {
        console.log(`[VimCord Event] ${eventName}:`, payload);
        if (typeof window.onVimCordEvent === 'function') {
            try {
                window.onVimCordEvent(eventName, payload);
            } catch (err) {
                console.error(`[VimCord Event Error] Handler failed for ${eventName}:`, err);
            }
        }
    };

    // Polyfill pywebview API
    window.pywebview = {
        api: new Proxy({}, {
            get: function(target, propKey) {
                return function(...args) {
                    const cmd = String(propKey);
                    
                    // Handle special parameter signatures matching Tauri commands (camelCase)
                    if (cmd === 'login') {
                        return invoke('login', {
                            username: args[0],
                            password: args[1] || "",
                            host: args[2] || "",
                            tcpPort: args[3] || 0,
                            udpPort: args[4] || 0,
                            autoLogin: !!args[5]
                        });
                    } else if (cmd === 'register') {
                        return invoke('register', {
                            username: args[0],
                            password: args[1] || "",
                            host: args[2] || "",
                            tcpPort: args[3] || 0,
                            udpPort: args[4] || 0
                        });
                    } else if (cmd === 'send_chat_message') {
                        return invoke('send_chat_message', {
                            targetType: args[0],
                            targetId: args[1],
                            content: args[2] || "",
                            imageData: args[3] || "",
                            voiceData: args[4] || "",
                            voiceDuration: args[5] || 0.0,
                            fileData: args[6] || "",
                            fileName: args[7] || "",
                            fileSize: args[8] || 0
                        });
                    } else if (cmd === 'delete_message') {
                        return invoke('delete_message', {
                            msgId: args[0],
                            targetType: args[1],
                            targetId: args[2]
                        });
                    } else if (cmd === 'get_history') {
                        return invoke('get_history', {
                            targetType: args[0],
                            targetId: args[1]
                        });
                    } else if (cmd === 'set_window_size') {
                        return invoke('set_window_size', {
                            width: args[0],
                            height: args[1]
                        });
                    } else if (cmd === 'join_voice') {
                        return invoke('join_voice', {
                            roomId: args[0],
                            channelId: args[1]
                        });
                    } else if (cmd === 'leave_voice') {
                        return invoke('leave_voice', {});
                    } else if (cmd === 'start_call') {
                        return invoke('start_call', {
                            targetUserId: args[0]
                        });
                    } else if (cmd === 'accept_call') {
                        return invoke('accept_call', {
                            callId: args[0]
                        });
                    } else if (cmd === 'decline_call') {
                        return invoke('decline_call', {
                            callId: args[0]
                        });
                    } else if (cmd === 'end_call') {
                        return invoke('end_call', {
                            callId: args[0] || null
                        });
                    } else if (cmd === 'set_mic_muted') {
                        return invoke('set_mic_muted', {
                            muted: !!args[0]
                        });
                    } else if (cmd === 'set_deafened') {
                        return invoke('set_deafened', {
                            deafened: !!args[0]
                        });
                    } else if (cmd === 'set_mic_volume') {
                        return invoke('set_mic_volume', {
                            volume: Number(args[0]) / 100.0
                        });
                    } else if (cmd === 'set_output_volume') {
                        return invoke('set_output_volume', {
                            volume: Number(args[0]) / 100.0
                        });
                    } else if (cmd === 'set_vad_threshold') {
                        return invoke('set_vad_threshold', {
                            threshold: Number(args[0])
                        });
                    } else if (cmd === 'set_theme') {
                        return invoke('set_theme', {
                            themeName: String(args[0])
                        });
                    } else if (cmd === 'set_language') {
                        return invoke('set_language', {
                            lang: String(args[0])
                        });
                    } else if (cmd === 'set_dnd_mode') {
                        return invoke('set_dnd_mode', {
                            enabled: !!args[0]
                        });
                    } else if (cmd === 'create_room') {
                        return invoke('create_room', {
                            name: String(args[0])
                        });
                    } else if (cmd === 'delete_room') {
                        return invoke('delete_room', {
                            roomId: String(args[0])
                        });
                    } else if (cmd === 'leave_room') {
                        return invoke('leave_room', {
                            roomId: String(args[0])
                        });
                    } else if (cmd === 'create_channel') {
                        return invoke('create_channel', {
                            roomId: String(args[0]),
                            name: String(args[1]),
                            channelType: args[2] || "text"
                        });
                    } else if (cmd === 'delete_channel') {
                        return invoke('delete_channel', {
                            roomId: String(args[0]),
                            channelId: String(args[1])
                        });
                    } else if (cmd === 'rename_channel') {
                        return invoke('rename_channel', {
                            roomId: String(args[0]),
                            channelId: String(args[1]),
                            name: String(args[2])
                        });
                    } else if (cmd === 'create_room_invite') {
                        return invoke('create_room_invite', {
                            roomId: String(args[0])
                        });
                    } else if (cmd === 'join_room_by_invite') {
                        return invoke('join_room_by_invite', {
                            code: String(args[0])
                        });
                    } else if (cmd === 'get_room_members') {
                        return invoke('get_room_members', {
                            roomId: String(args[0])
                        });
                    } else if (cmd === 'send_friend_request') {
                        return invoke('send_friend_request', {
                            username: String(args[0])
                        });
                    } else if (cmd === 'accept_friend_request') {
                        return invoke('accept_friend_request', {
                            senderId: String(args[0])
                        });
                    } else if (cmd === 'decline_friend_request') {
                        return invoke('decline_friend_request', {
                            peerId: String(args[0])
                        });
                    } else if (cmd === 'update_profile') {
                        return invoke('update_profile', {
                            displayName: args[0] || null,
                            statusText: args[1] || null,
                            avatarColor: args[2] || null,
                            bannerColor: args[3] || null,
                            avatarImage: args[4] || null,
                            bannerImage: args[5] || null,
                            bio: args[6] || null
                        });
                    } else if (cmd === 'change_password') {
                        return invoke('change_password', {
                            oldPass: String(args[0]),
                            newPass: String(args[1])
                        });
                    } else if (cmd === 'save_file_to_disk') {
                        return invoke('save_file_to_disk', {
                            filename: String(args[0]),
                            b64Data: String(args[1])
                        });
                    } else if (cmd === 'open_file_dialog') {
                        return invoke('open_file_dialog', {});
                    } else if (cmd === 'set_audio_devices') {
                        return invoke('set_audio_devices', {
                            inputDevice: args[0] !== undefined ? args[0] : null,
                            outputDevice: args[1] !== undefined ? args[1] : null
                        });
                    } else if (cmd === 'set_ptt_config') {
                        return invoke('set_ptt_config', {
                            enabled: !!args[0],
                            hotkey: args[1] ? String(args[1]) : null
                        });
                    } else if (cmd === 'set_stream_settings') {
                        return invoke('set_stream_settings', {
                            resolution: String(args[0]),
                            fps: Number(args[1]) || 30,
                            quality: Number(args[2]) || 45
                        });
                    } else if (cmd === 'start_mic_test') {
                        return invoke('start_mic_test', {});
                    } else if (cmd === 'stop_mic_test') {
                        return invoke('stop_mic_test', {});
                    } else if (cmd === 'start_voice_record') {
                        return invoke('start_voice_record', {});
                    } else if (cmd === 'stop_voice_record') {
                        return invoke('stop_voice_record', {});
                    } else if (cmd === 'play_voice_message') {
                        return invoke('play_voice_message', {
                            voiceData: String(args[0] || ""),
                            duration: Number(args[1]) || 0.0
                        });
                    } else if (cmd === 'start_screen_share') {
                        return invoke('start_screen_share', {
                            targetType: String(args[0] || "channel"),
                            targetId: String(args[1] || "")
                        });
                    } else if (cmd === 'stop_screen_share') {
                        return invoke('stop_screen_share', {
                            targetType: args[0] ? String(args[0]) : null,
                            targetId: args[1] ? String(args[1]) : null
                        });
                    } else if (cmd === 'record_keybind_start') {
                        return invoke('record_keybind_start', {});
                    } else if (cmd === 'get_clipboard_image') {
                        return invoke('get_clipboard_image', {});
                    } else if (cmd === 'reconnect') {
                        return invoke('reconnect', {});
                    } else if (cmd === 'logout') {
                        return invoke('logout', {});
                    }

                    // Default zero-argument or simple command call
                    return invoke(cmd, {});
                };
            }
        })
    };

    // Listen for backend events dispatched over Tauri event bus if available
    try {
        if (window.__TAURI__ && window.__TAURI__.event && typeof window.__TAURI__.event.listen === 'function') {
            window.__TAURI__.event.listen('vimcord://event', (event) => {
                const data = event.payload;
                if (data && data.event) {
                    window.dispatchVimCordEvent(data.event, data.payload);
                }
            });
        }
    } catch (e) {
        console.warn("[VimCord Bridge] Could not attach Tauri event listener:", e);
    }

    // Trigger pywebviewready event so app.js initializes automatically
    function triggerReady() {
        console.log("[VimCord Bridge] Dispatching pywebviewready...");
        window.dispatchEvent(new Event('pywebviewready'));
        if (typeof window.initApp === 'function') {
            window.initApp();
        }
    }

    if (document.readyState === 'loading') {
        window.addEventListener('DOMContentLoaded', () => setTimeout(triggerReady, 20));
    } else {
        setTimeout(triggerReady, 20);
    }
})();
