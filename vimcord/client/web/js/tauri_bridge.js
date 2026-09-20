/**
 * Tauri IPC Polyfill Bridge for VimCord.
 * Seamlessly maps `window.pywebview.api.*` calls to Tauri v2 `invoke(...)`
 * and routes Tauri events to `window.onVimCordEvent(...)`.
 * This preserves 100% of the existing frontend logic and styling.
 */

(function() {
    console.log("[VimCord Tauri Bridge] Initializing...");

    // Check if running inside Tauri
    const isTauri = window.__TAURI__ || window.__TAURI_INTERNALS__;

    if (isTauri) {
        const invoke = window.__TAURI__.core.invoke;
        const listen = window.__TAURI__.event.listen;

        // Polyfill pywebview API
        window.pywebview = {
            api: new Proxy({}, {
                get: function(target, propKey) {
                    return function(...args) {
                        // Map method call to tauri invoke
                        const cmd = String(propKey);
                        
                        // Handle special parameter signatures
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
                        }

                        // Default zero-argument or simple command call
                        return invoke(cmd, {});
                    };
                }
            })
        };

        // Listen for backend events dispatched over Tauri event bus
        listen('vimcord://event', (event) => {
            const data = event.payload;
            if (data && data.event && typeof window.onVimCordEvent === 'function') {
                window.onVimCordEvent(data.event, data.payload);
            }
        });

        // Trigger pywebviewready event so app.js initializes automatically
        function triggerReady() {
            window.dispatchEvent(new Event('pywebviewready'));
            if (typeof window.initApp === 'function') {
                window.initApp();
            }
        }

        if (document.readyState === 'loading') {
            window.addEventListener('DOMContentLoaded', () => setTimeout(triggerReady, 10));
        } else {
            setTimeout(triggerReady, 10);
        }
    }
})();
