/**
 * VimCord Web Frontend Application Logic
 * Full PyQt feature parity: Auth, servers/channels (voice & text), friends & DMs,
 * voice stage with live user presence & speaking indicators, direct calls,
 * screen sharing, 3-page settings dialog, clipboard paste (Ctrl+V) & drag-drop,
 * global Push-to-Talk, i18n localization, and system tray integration.
 */

// ---------------- Application State ----------------

const state = {
    user: null,
    rooms: {},
    users: {},
    friends: [],
    voiceUsers: {}, // channel_id -> [{ user_id, username, display_name, avatar_color, avatar_image, is_muted, is_deafened, is_speaking }]
    currentRoomId: null,
    currentChannelId: null,
    currentDmPeerId: null,
    currentVoiceChannelId: null,
    currentVoiceRoomId: null,
    activeTab: 'home', // 'home' or 'server'
    activeFriendsTab: 'online', // 'online', 'all', 'pending', 'add'
    activeCallId: null,
    callStartTime: null,
    callTimerInterval: null,
    isMuted: false,
    isDeafened: false,
    isSharingScreen: false,
    isRecordingVoice: false,
    voiceRecordStart: 0,
    currentAttachment: null,
    pttMode: false,
    pttKey: 'Space',
    theme: 'dark',
    language: 'en',
    dndMode: false,
    config: {},
    isTestingMic: false
};

const settingsDraft = {
    displayName: '',
    customStatus: '',
    bio: '',
    avatarColor: '#5865F2',
    bannerColor: '#5865F2',
    avatarImage: '',
    bannerImage: ''
};

let currentAuthTab = 'login';
let currentPromptCallback = null;

const DISCORD_COLORS = [
    { hex: '#5865F2', name: 'Blurple' },
    { hex: '#57F287', name: 'Green' },
    { hex: '#FEE75C', name: 'Yellow' },
    { hex: '#EB459E', name: 'Fuchsia' },
    { hex: '#ED4245', name: 'Red' },
    { hex: '#FFFFFF', name: 'White' },
    { hex: '#2B2D31', name: 'Dark Gray' }
];

// ---------------- Localization Dictionary ----------------

const I18N = {
    en: {
        friends: "Friends", direct_messages: "DIRECT MESSAGES", text_channels: "TEXT CHANNELS",
        voice_channels: "VOICE CHANNELS", voice_connected: "Voice Connected", mute_mic: "Mute",
        unmute_mic: "Unmute", deafen_audio: "Deafen", undeafen_audio: "Undeafen", user_settings: "User Settings",
        about_me: "My Account", voice_channel: "Voice & Video", appearance: "Appearance",
        record_keybind: "Record Keybind", send_message: "Send a message...",
        pasted_from_clipboard: "Attached from clipboard", disconnect: "Disconnect", screen_share: "Screen Share",
        online: "Online", all: "All", pending: "Pending", add_friend: "Add Friend", display_name: "DISPLAY NAME",
        banner_color: "BANNER COLOR"
    },
    ru: {
        friends: "Друзья", direct_messages: "ЛИЧНЫЕ СООБЩЕНИЯ", text_channels: "ТЕКСТОВЫЕ КАНАЛЫ",
        voice_channels: "ГОЛОСОВЫЕ КАНАЛЫ", voice_connected: "Голос подключен", mute_mic: "Заглушить",
        unmute_mic: "Включить", deafen_audio: "Заглушить звук", undeafen_audio: "Включить звук",
        user_settings: "Настройки пользователя", about_me: "Моя учетная запись", voice_channel: "Голос и видео",
        appearance: "Внешний вид", record_keybind: "Задать кнопку", send_message: "Написать сообщение...",
        pasted_from_clipboard: "Вставлено из буфера обмена", disconnect: "Отключиться", screen_share: "Демонстрация",
        online: "В сети", all: "Все", pending: "Ожидание", add_friend: "Добавить в друзья", display_name: "ОТОБРАЖАЕМОЕ ИМЯ",
        banner_color: "ЦВЕТ БАННЕРА"
    }
};

function t(key, fallback = "") {
    const lang = state.language || 'en';
    if (I18N[lang] && I18N[lang][key]) {
        return I18N[lang][key];
    }
    return fallback || key;
}

// ---------------- Lifecycle & Initialization ----------------

let isAppReady = false;

window.addEventListener('pywebviewready', () => {
    initApp();
});

document.addEventListener('DOMContentLoaded', () => {
    if (window.pywebview && window.pywebview.api) {
        initApp();
    }
});

async function initApp() {
    if (isAppReady) return;
    isAppReady = true;

    bindDomEvents();

    try {
        const initData = await window.pywebview.api.get_initial_state();
        state.config = initData.config || {};
        state.language = initData.language || 'en';
        state.theme = initData.theme || 'dark';
        state.pttMode = !!initData.ptt_mode;
        state.pttKey = initData.ptt_key || 'Space';
        state.dndMode = !!initData.dnd_mode;

        applyTheme(state.theme);
        applyLanguage(state.language);

        // Populate audio controls
        if (initData.mic_volume !== undefined) {
            document.getElementById('slider-mic-volume').value = initData.mic_volume;
            document.getElementById('label-mic-volume').textContent = `${initData.mic_volume}%`;
        }
        if (initData.output_volume !== undefined) {
            document.getElementById('slider-output-volume').value = initData.output_volume;
            document.getElementById('label-output-volume').textContent = `${initData.output_volume}%`;
        }
        if (initData.vad_threshold !== undefined) {
            const vadSliderVal = Math.round(initData.vad_threshold * 1000);
            document.getElementById('slider-vad-thresh').value = vadSliderVal;
            document.getElementById('label-vad-thresh').textContent = initData.vad_threshold.toFixed(3);
        }
        if (initData.stream_resolution) {
            document.getElementById('select-screen-res').value = initData.stream_resolution;
        }
        if (initData.stream_fps) {
            document.getElementById('select-screen-fps').value = String(initData.stream_fps);
        }
        if (initData.stream_quality) {
            document.getElementById('slider-screen-quality').value = initData.stream_quality;
            document.getElementById('label-screen-quality').textContent = `${initData.stream_quality}%`;
        }

        document.getElementById('cb-dnd-mode').checked = state.dndMode;

        renderPttSettings(state.pttMode, state.pttKey);
        populateAudioDevices(initData.audio_devices || {});

        // Pre-fill login credentials if saved
        if (initData.saved_username) {
            document.getElementById('auth-username').value = initData.saved_username;
        }
        if (initData.saved_password) {
            document.getElementById('auth-password').value = initData.saved_password;
        }
        document.getElementById('auth-autologin').checked = !!initData.auto_login;

        // Auto-login trigger
        if (initData.auto_login && initData.saved_username && initData.saved_password) {
            doLogin(initData.saved_username, initData.saved_password, true);
        }
    } catch (e) {
        console.error('Initialization error:', e);
    }
}

// ---------------- DOM Event Bindings ----------------

function bindDomEvents() {
    // Window Titlebar
    document.getElementById('btn-win-min').onclick = () => window.pywebview.api.minimize_window();
    document.getElementById('btn-win-max').onclick = () => window.pywebview.api.toggle_maximize_window();
    document.getElementById('btn-win-close').onclick = () => window.pywebview.api.close_window();

    // Server Rail
    document.getElementById('btn-rail-home').onclick = () => switchMode('home');
    document.getElementById('btn-rail-add').onclick = () => promptCreateRoom();
    document.getElementById('btn-rail-join').onclick = () => promptJoinInvite();

    // Channel Header Buttons
    document.getElementById('btn-create-channel').onclick = () => promptCreateChannel();
    document.getElementById('btn-server-invite').onclick = () => promptServerInvite();

    // Friends Navigation
    document.getElementById('btn-tab-friends').onclick = () => switchMode('home');
    document.querySelectorAll('.friends-tab').forEach(tab => {
        tab.onclick = () => {
            document.querySelectorAll('.friends-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            state.activeFriendsTab = tab.dataset.tab;
            renderFriendsTab(tab.dataset.tab);
        };
    });

    document.getElementById('friends-search').oninput = (e) => filterFriends(e.target.value);
    document.getElementById('btn-send-friend-req').onclick = sendFriendRequest;

    // Direct Call Header Button
    document.getElementById('btn-header-call').onclick = () => {
        if (state.currentDmPeerId) {
            window.pywebview.api.start_call(state.currentDmPeerId);
        }
    };

    // Member Sidebar Toggle
    document.getElementById('btn-toggle-members').onclick = () => {
        document.getElementById('member-sidebar').classList.toggle('hidden');
    };

    // Chat Composer
    const chatInput = document.getElementById('chat-text-input');
    chatInput.onkeydown = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    };

    document.getElementById('btn-attach-file').onclick = chooseAttachment;
    document.getElementById('btn-clear-attachment').onclick = clearAttachment;
    document.getElementById('btn-voice-msg').onclick = toggleVoiceRecording;

    // Clipboard Paste Listener (Ctrl + V for images & files)
    document.addEventListener('paste', handlePasteEvent);

    // Drag & Drop onto chat container
    setupDragAndDrop();

    // Voice & Call Action Buttons
    document.getElementById('btn-voice-disconnect').onclick = () => window.pywebview.api.leave_voice();
    document.getElementById('btn-voice-screenshare').onclick = toggleScreenShare;
    document.getElementById('btn-stage-screen').onclick = toggleScreenShare;
    document.getElementById('btn-call-screenshare').onclick = toggleScreenShare;
    document.getElementById('btn-call-end').onclick = () => window.pywebview.api.end_call();
    document.getElementById('btn-stage-leave').onclick = () => window.pywebview.api.leave_voice();

    // User Panel Controls
    document.getElementById('btn-toggle-mic').onclick = toggleMic;
    document.getElementById('btn-stage-mute').onclick = toggleMic;
    document.getElementById('btn-toggle-deafen').onclick = toggleDeafen;
    document.getElementById('btn-stage-deafen').onclick = toggleDeafen;
    document.getElementById('btn-open-settings').onclick = openSettings;
    document.getElementById('user-panel-profile').onclick = openSettings;

    // Settings Modal
    document.getElementById('btn-close-settings').onclick = closeSettings;
    document.querySelectorAll('.settings-nav-item').forEach(item => {
        if (item.id === 'btn-settings-logout') {
            item.onclick = doLogout;
            return;
        }
        item.onclick = () => {
            document.querySelectorAll('.settings-nav-item').forEach(i => i.classList.remove('active'));
            item.classList.add('active');
            document.querySelectorAll('.settings-page').forEach(p => p.classList.add('hidden'));
            const targetPage = document.getElementById(`settings-tab-${item.dataset.tab}`);
            if (targetPage) targetPage.classList.remove('hidden');
        };
    });

    // Settings Profile Card Buttons
    document.getElementById('btn-upload-banner').onclick = uploadBanner;
    document.getElementById('btn-remove-banner').onclick = removeBanner;
    document.getElementById('btn-upload-avatar').onclick = uploadAvatar;
    document.getElementById('btn-remove-avatar').onclick = removeAvatar;
    document.getElementById('btn-save-profile').onclick = saveProfileSettings;
    document.getElementById('btn-save-password').onclick = savePasswordChange;

    // Settings Audio Controls
    document.getElementById('select-audio-input').onchange = (e) => {
        const val = e.target.value ? parseInt(e.target.value) : null;
        window.pywebview.api.set_audio_devices(val, null);
    };
    document.getElementById('select-audio-output').onchange = (e) => {
        const val = e.target.value ? parseInt(e.target.value) : null;
        window.pywebview.api.set_audio_devices(null, val);
    };

    document.getElementById('slider-mic-volume').oninput = (e) => {
        const v = parseInt(e.target.value);
        document.getElementById('label-mic-volume').textContent = `${v}%`;
        window.pywebview.api.set_mic_volume(v / 100.0);
    };
    document.getElementById('slider-output-volume').oninput = (e) => {
        const v = parseInt(e.target.value);
        document.getElementById('label-output-volume').textContent = `${v}%`;
        window.pywebview.api.set_output_volume(v / 100.0);
    };

    document.getElementById('radio-vad').onchange = () => updateInputMode(false);
    document.getElementById('radio-ptt').onchange = () => updateInputMode(true);

    document.getElementById('slider-vad-thresh').oninput = (e) => {
        const thresh = parseInt(e.target.value) / 1000.0;
        document.getElementById('label-vad-thresh').textContent = thresh.toFixed(3);
        window.pywebview.api.set_vad_threshold(thresh);
    };

    document.getElementById('btn-record-keybind').onclick = startRecordKeybind;
    document.getElementById('select-ptt-preset').onchange = (e) => {
        const k = e.target.value;
        state.pttKey = k;
        document.getElementById('ptt-key-display').textContent = k;
        window.pywebview.api.set_ptt_config(true, k);
    };

    document.getElementById('btn-test-mic').onclick = toggleMicTest;

    // Settings Screen Share Presets
    const onStreamSettingChange = () => {
        const res = document.getElementById('select-screen-res').value;
        const fps = parseInt(document.getElementById('select-screen-fps').value);
        const q = parseInt(document.getElementById('slider-screen-quality').value);
        document.getElementById('label-screen-quality').textContent = `${q}%`;
        window.pywebview.api.set_stream_settings(res, fps, q);
    };
    document.getElementById('select-screen-res').onchange = onStreamSettingChange;
    document.getElementById('select-screen-fps').onchange = onStreamSettingChange;
    document.getElementById('slider-screen-quality').oninput = onStreamSettingChange;

    // Settings Appearance & DND
    document.querySelectorAll('input[name="theme_select"]').forEach(radio => {
        radio.onchange = () => {
            applyTheme(radio.value);
            window.pywebview.api.set_theme(radio.value);
        };
    });

    document.querySelectorAll('input[name="lang_select"]').forEach(radio => {
        radio.onchange = () => {
            applyLanguage(radio.value);
            window.pywebview.api.set_language(radio.value);
        };
    });

    document.getElementById('cb-dnd-mode').onchange = (e) => {
        state.dndMode = e.target.checked;
        window.pywebview.api.set_dnd_mode(state.dndMode);
    };

    // Auth Form Submit & Tabs
    document.getElementById('form-auth').onsubmit = handleAuthSubmit;
    document.getElementById('tab-btn-login').onclick = () => switchAuthTab('login');
    document.getElementById('tab-btn-register').onclick = () => switchAuthTab('register');

    // Prompt Modal Actions
    document.getElementById('btn-prompt-cancel').onclick = closePromptModal;
    document.getElementById('btn-prompt-confirm').onclick = () => {
        const val = document.getElementById('prompt-input').value;
        const typeSelect = document.getElementById('prompt-channel-type');
        const chType = typeSelect ? typeSelect.value : 'text';
        if (currentPromptCallback) {
            currentPromptCallback(val, chType);
        }
        closePromptModal();
    };
    document.getElementById('prompt-input').onkeydown = (e) => {
        if (e.key === 'Enter') {
            document.getElementById('btn-prompt-confirm').click();
        } else if (e.key === 'Escape') {
            closePromptModal();
        }
    };

    // Incoming Call Modal Actions
    document.getElementById('btn-accept-call').onclick = acceptIncomingCall;
    document.getElementById('btn-decline-call').onclick = declineIncomingCall;

    // Lightbox
    document.getElementById('btn-close-lightbox').onclick = () => {
        document.getElementById('lightbox-modal').classList.add('hidden');
    };
}

// ---------------- Clipboard & Drag/Drop Handlers ----------------

async function handlePasteEvent(e) {
    const items = (e.clipboardData || window.clipboardData)?.items;
    let handled = false;

    if (items && items.length > 0) {
        for (let i = 0; i < items.length; i++) {
            const item = items[i];
            if (item.type.indexOf('image') !== -1) {
                const blob = item.getAsFile();
                if (blob) {
                    const reader = new FileReader();
                    reader.onload = function(evt) {
                        const base64Data = evt.target.result.split(',')[1];
                        const timestamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-');
                        setAttachment({
                            name: `screenshot_${timestamp}.png`,
                            size: blob.size,
                            is_image: true,
                            data: base64Data
                        });
                        showToast(t('pasted_from_clipboard', 'Attached image from clipboard'));
                    };
                    reader.readAsDataURL(blob);
                    e.preventDefault();
                    handled = true;
                    return;
                }
            } else if (item.kind === 'file') {
                const file = item.getAsFile();
                if (file) {
                    const reader = new FileReader();
                    reader.onload = function(evt) {
                        const base64Data = evt.target.result.split(',')[1];
                        setAttachment({
                            name: file.name,
                            size: file.size,
                            is_image: file.type.startsWith('image/'),
                            data: base64Data
                        });
                        showToast(t('pasted_from_clipboard', 'Attached file from clipboard'));
                    };
                    reader.readAsDataURL(file);
                    e.preventDefault();
                    handled = true;
                    return;
                }
            }
        }
    }

    if (!handled && window.pywebview?.api?.get_clipboard_image) {
        try {
            const clipImg = await window.pywebview.api.get_clipboard_image();
            if (clipImg && clipImg.data) {
                setAttachment(clipImg);
                showToast(t('pasted_from_clipboard', 'Attached image from clipboard'));
                e.preventDefault();
            }
        } catch (err) {
            // Normal text paste
        }
    }
}

function setupDragAndDrop() {
    const dropZone = document.getElementById('view-chat');
    if (!dropZone) return;

    ['dragenter', 'dragover'].forEach(name => {
        dropZone.addEventListener(name, (e) => {
            e.preventDefault();
            dropZone.classList.add('drag-over');
        });
    });

    ['dragleave', 'drop'].forEach(name => {
        dropZone.addEventListener(name, (e) => {
            e.preventDefault();
            dropZone.classList.remove('drag-over');
        });
    });

    dropZone.addEventListener('drop', (e) => {
        const files = e.dataTransfer?.files;
        if (files && files.length > 0) {
            const file = files[0];
            const reader = new FileReader();
            reader.onload = function(evt) {
                const base64Data = evt.target.result.split(',')[1];
                setAttachment({
                    name: file.name,
                    size: file.size,
                    is_image: file.type.startsWith('image/'),
                    data: base64Data
                });
                showToast(`Attached ${file.name}`);
            };
            reader.readAsDataURL(file);
        }
    });
}

// ---------------- Event Dispatcher from Python ----------------

window.onVimCordEvent = function(eventName, payload) {
    switch (eventName) {
        case 'login_response':
            onLoginResponse(payload);
            break;
        case 'register_response':
            onRegisterResponse(payload);
            break;
        case 'chat_message':
            onChatMessageReceived(payload);
            break;
        case 'history_response':
            onHistoryReceived(payload);
            break;
        case 'message_deleted':
            onMessageDeleted(payload);
            break;
        case 'user_presence':
            onUserPresence(payload);
            break;
        case 'friends_update':
            onFriendsUpdate(payload);
            break;
        case 'friend_request_resp':
            onFriendRequestResp(payload);
            break;
        case 'incoming_call':
            onIncomingCall(payload);
            break;
        case 'call_ringing':
            showToast('Calling...');
            break;
        case 'call_accepted':
            onCallAccepted(payload);
            break;
        case 'call_declined':
        case 'call_ended':
        case 'call_failed':
            onCallTerminated(eventName, payload);
            break;
        case 'voice_state_update':
            onVoiceStateUpdate(payload);
            break;
        case 'peer_speaking':
            onPeerSpeaking(payload);
            break;
        case 'local_speaking':
            onLocalSpeaking(payload);
            break;
        case 'screen_frame':
            onScreenFrame(payload);
            break;
        case 'screen_stop':
            onScreenStop(payload);
            break;
        case 'mic_test_level':
            onMicTestLevel(payload);
            break;
        case 'keybind_captured':
            onKeybindCaptured(payload);
            break;
        case 'pong':
            onPong(payload);
            break;
        case 'room_created':
            onRoomCreated(payload);
            break;
        case 'room_deleted':
            onRoomDeleted(payload);
            break;
        case 'channel_created':
            onChannelCreated(payload);
            break;
        case 'channel_deleted':
            onChannelDeleted(payload);
            break;
        case 'channel_renamed':
            onChannelRenamed(payload);
            break;
        case 'room_invite_created':
            onRoomInviteCreated(payload);
            break;
        case 'room_invite_joined':
            onRoomInviteJoined(payload);
            break;
        case 'leave_room_resp':
            onLeaveRoomResp(payload);
            break;
        case 'room_members_resp':
            onRoomMembersResp(payload);
            break;
        case 'profile_update_resp':
            onProfileUpdateResp(payload);
            break;
        case 'change_password_resp':
            onChangePasswordResp(payload);
            break;
    }
};

// ---------------- Auth Logic ----------------

function switchAuthTab(tab) {
    currentAuthTab = tab;
    document.getElementById('tab-btn-login').classList.toggle('active', tab === 'login');
    document.getElementById('tab-btn-register').classList.toggle('active', tab === 'register');
    document.getElementById('btn-auth-submit').textContent = (tab === 'login') ? 'Log In' : 'Register';
    document.getElementById('row-auto-login').style.display = (tab === 'login') ? 'block' : 'none';
    hideAuthError();
}

function showAuthError(msg) {
    const err = document.getElementById('auth-error');
    if (err) {
        err.textContent = msg;
        err.classList.remove('hidden');
    }
}

function hideAuthError() {
    const err = document.getElementById('auth-error');
    if (err) err.classList.add('hidden');
}

async function handleAuthSubmit(e) {
    if (e) e.preventDefault();
    const u = document.getElementById('auth-username').value.trim();
    const p = document.getElementById('auth-password').value;
    const autologin = document.getElementById('auth-autologin').checked;

    if (!u) {
        showAuthError("Please enter a username.");
        return;
    }

    const btn = document.getElementById('btn-auth-submit');
    btn.disabled = true;
    btn.textContent = 'Connecting...';
    hideAuthError();

    try {
        let res;
        if (currentAuthTab === 'login') {
            res = await window.pywebview.api.login(u, p, '', 0, 0, autologin);
        } else {
            res = await window.pywebview.api.register(u, p, '', 0, 0);
        }
        if (res && res.success === false) {
            btn.disabled = false;
            btn.textContent = (currentAuthTab === 'login') ? 'Log In' : 'Register';
            showAuthError(res.message || 'Connection failed.');
        }
    } catch (err) {
        btn.disabled = false;
        btn.textContent = (currentAuthTab === 'login') ? 'Log In' : 'Register';
        showAuthError(String(err));
    }
}

function doLogin(u, p, autologin) {
    const btn = document.getElementById('btn-auth-submit');
    if (btn) {
        btn.disabled = true;
        btn.textContent = 'Connecting...';
    }
    hideAuthError();
    window.pywebview.api.login(u, p, '', 0, 0, autologin);
}

function onLoginResponse(res) {
    const btn = document.getElementById('btn-auth-submit');
    if (btn) {
        btn.disabled = false;
        btn.textContent = (currentAuthTab === 'login') ? 'Log In' : 'Register';
    }

    if (!res.success) {
        showAuthError(res.data?.message || res.message || 'Login failed. Please check credentials.');
        return;
    }

    // Success: Transition to main workspace
    document.getElementById('auth-container').classList.add('hidden');
    document.getElementById('app-container').classList.remove('hidden');

    state.user = res.data;
    state.rooms = {};
    (res.data.rooms || []).forEach(r => state.rooms[r.room_id] = r);
    state.users = {};
    (res.data.users || []).forEach(u => state.users[u.user_id] = u);
    state.friends = res.data.friends || [];

    updateUserPanelProfile();
    renderServerRail();
    renderSidebar();
    switchMode('home');
    showToast(`Welcome back, ${state.user.display_name || state.user.username}!`);
}

function onRegisterResponse(res) {
    const btn = document.getElementById('btn-auth-submit');
    if (btn) {
        btn.disabled = false;
        btn.textContent = 'Register';
    }

    if (!res.success) {
        showAuthError(res.message || 'Registration failed.');
    } else {
        showToast('Account created successfully! Logging in...');
        switchAuthTab('login');
        const u = document.getElementById('auth-username').value.trim();
        const p = document.getElementById('auth-password').value;
        doLogin(u, p, false);
    }
}

function doLogout() {
    if (confirm("Are you sure you want to log out of your account?")) {
        closeSettings();
        document.getElementById('app-container').classList.add('hidden');
        document.getElementById('auth-container').classList.remove('hidden');
        state.user = null;
        window.pywebview.api.logout();
    }
}

// ---------------- Profile & User Panel ----------------

function updateUserPanelProfile() {
    if (!state.user) return;
    const disp = state.user.display_name || state.user.username;
    document.getElementById('user-panel-display').textContent = disp;
    document.getElementById('user-panel-sub').textContent = `@${state.user.username}`;

    const av = document.getElementById('user-panel-avatar');
    if (state.user.avatar_image) {
        av.style.backgroundImage = `url(data:image/png;base64,${state.user.avatar_image})`;
        av.textContent = '';
    } else {
        av.style.backgroundImage = '';
        av.style.backgroundColor = state.user.avatar_color || '#5865F2';
        av.textContent = disp.charAt(0).toUpperCase();
    }
}

// ---------------- Server & Channel Management ----------------

function switchMode(mode, targetId = null) {
    state.activeTab = mode;
    const homeRailBtn = document.getElementById('btn-rail-home');

    if (mode === 'home') {
        homeRailBtn.classList.add('active');
        document.querySelectorAll('.server-rail-btn').forEach(b => b.classList.remove('active'));
        document.getElementById('sidebar-title').textContent = t('direct_messages', 'Direct Messages');
        document.getElementById('home-sidebar').classList.remove('hidden');
        document.getElementById('server-sidebar').classList.add('hidden');
        document.getElementById('btn-create-channel').classList.add('hidden');
        document.getElementById('btn-server-invite').classList.add('hidden');
        state.currentRoomId = null;

        showFriendsView();
    } else if (mode === 'server') {
        homeRailBtn.classList.remove('active');
        state.currentRoomId = targetId;
        const room = state.rooms[targetId];
        if (!room) return;

        document.getElementById('sidebar-title').textContent = room.name;
        document.getElementById('home-sidebar').classList.add('hidden');
        document.getElementById('server-sidebar').classList.remove('hidden');
        document.getElementById('btn-create-channel').classList.remove('hidden');
        document.getElementById('btn-server-invite').classList.remove('hidden');

        renderServerChannels(room);
        window.pywebview.api.get_room_members(targetId);
    }
}

function renderServerRail() {
    const railList = document.getElementById('server-rail-list');
    railList.innerHTML = '';

    Object.values(state.rooms).forEach(room => {
        const btn = document.createElement('button');
        btn.className = 'rail-btn server-rail-btn';
        if (state.currentRoomId === room.room_id) {
            btn.classList.add('active');
        }
        btn.title = room.name;
        btn.innerHTML = `<span class="rail-icon">${room.name.charAt(0).toUpperCase()}</span><div class="pill-indicator"></div>`;
        btn.onclick = () => {
            document.querySelectorAll('.server-rail-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            switchMode('server', room.room_id);
        };

        btn.oncontextmenu = (e) => {
            e.preventDefault();
            const isOwner = room.owner_id === state.user?.user_id;
            const action = isOwner ? 'Delete Server' : 'Leave Server';
            if (confirm(`${action} "${room.name}"?`)) {
                if (isOwner) {
                    window.pywebview.api.delete_room(room.room_id);
                } else {
                    window.pywebview.api.leave_room(room.room_id);
                }
            }
        };

        railList.appendChild(btn);
    });
}

function renderSidebar() {
    renderDmList();
}

function renderDmList() {
    const list = document.getElementById('dm-list');
    list.innerHTML = '';

    const peers = state.friends.filter(f => f.friendship_status === 'accepted');
    peers.forEach(f => {
        const friendId = f.peer_id || f.user_id;
        const username = f.username || f.peer_name || '';
        const displayName = f.display_name || f.peer_display_name || username;
        const isOnline = Boolean(state.users[friendId]?.online || state.users[friendId]?.is_online || f.online || f.is_online);

        const item = document.createElement('button');
        item.className = 'sidebar-item';
        if (state.currentDmPeerId === friendId) {
            item.classList.add('active');
        }

        const avatarStyle = f.avatar_image ? `background-image: url(data:image/png;base64,${f.avatar_image});` : `background-color: ${f.avatar_color || '#5865F2'};`;
        const avatarLetter = f.avatar_image ? '' : displayName.charAt(0).toUpperCase();

        item.innerHTML = `
            <div class="avatar-wrap">
                <div class="avatar" style="${avatarStyle}">${avatarLetter}</div>
                <div class="status-dot ${isOnline ? 'status-online' : 'status-offline'}"></div>
            </div>
            <span class="item-name">${escapeHtml(displayName)}</span>
        `;
        item.onclick = () => selectDmUser(friendId, displayName);
        list.appendChild(item);
    });
}

function renderServerChannels(room) {
    const textList = document.getElementById('text-channel-list');
    const voiceList = document.getElementById('voice-channel-list');
    textList.innerHTML = '';
    voiceList.innerHTML = '';

    (room.channels || []).forEach(ch => {
        const isVoice = (ch.channel_type === 'voice' || ch.type === 'voice');

        const item = document.createElement('div');
        item.style.display = 'flex';
        item.style.flexDirection = 'column';
        item.style.position = 'relative';

        const row = document.createElement('div');
        row.style.display = 'flex';
        row.style.alignItems = 'center';

        const btn = document.createElement('button');
        btn.className = 'sidebar-item';
        btn.style.flex = '1';

        if (isVoice) {
            btn.innerHTML = `<span class="material-symbols-outlined item-icon">volume_up</span><span class="item-name">${escapeHtml(ch.name)}</span>`;
            if (state.currentVoiceChannelId === ch.channel_id) {
                btn.classList.add('active');
            }
            btn.onclick = () => selectVoiceChannel(room.room_id, ch.channel_id, ch.name);
            row.appendChild(btn);

            // Channel options for owner
            if (room.owner_id === state.user?.user_id && room.channels.length > 1) {
                appendChannelDeleteBtn(row, room.room_id, ch.channel_id, ch.name);
            }
            item.appendChild(row);

            // Connected users list under voice channel
            const usersCont = document.createElement('div');
            usersCont.className = 'channel-voice-users';
            usersCont.id = `voice-users-${ch.channel_id}`;
            renderChannelVoiceUsers(usersCont, ch.channel_id);
            item.appendChild(usersCont);

            voiceList.appendChild(item);
        } else {
            btn.innerHTML = `<span class="material-symbols-outlined item-icon">tag</span><span class="item-name">${escapeHtml(ch.name)}</span>`;
            if (state.currentChannelId === ch.channel_id && state.activeTab === 'server') {
                btn.classList.add('active');
            }
            btn.onclick = () => selectTextChannel(room.room_id, ch.channel_id, ch.name);
            row.appendChild(btn);

            if (room.owner_id === state.user?.user_id && room.channels.length > 1) {
                appendChannelDeleteBtn(row, room.room_id, ch.channel_id, ch.name);
            }
            item.appendChild(row);
            textList.appendChild(item);
        }
    });

    // Default select first text channel if none active
    if (!state.currentChannelId && state.activeTab === 'server') {
        const firstText = (room.channels || []).find(c => !(c.channel_type === 'voice' || c.type === 'voice'));
        if (firstText) {
            selectTextChannel(room.room_id, firstText.channel_id, firstText.name);
        }
    }
}

function appendChannelDeleteBtn(container, roomId, channelId, name) {
    const delBtn = document.createElement('button');
    delBtn.style.background = 'transparent';
    delBtn.style.border = 'none';
    delBtn.style.color = 'var(--text-muted)';
    delBtn.style.cursor = 'pointer';
    delBtn.style.padding = '4px 8px';
    delBtn.title = 'Delete Channel';
    delBtn.innerHTML = `<span class="material-symbols-outlined" style="font-size:16px;">close</span>`;
    delBtn.onclick = (e) => {
        e.stopPropagation();
        if (confirm(`Delete channel "${name}"?`)) {
            window.pywebview.api.delete_channel(roomId, channelId);
        }
    };
    container.appendChild(delBtn);
}

function renderChannelVoiceUsers(container, channelId) {
    container.innerHTML = '';
    const users = state.voiceUsers[channelId] || [];
    users.forEach(u => {
        const row = document.createElement('div');
        row.className = `channel-voice-user ${u.is_speaking ? 'speaking' : ''}`;
        row.id = `v-user-${channelId}-${u.user_id}`;

        const avStyle = u.avatar_image ? `background-image: url(data:image/png;base64,${u.avatar_image});` : `background-color: ${u.avatar_color || '#5865F2'};`;
        const avLetter = u.avatar_image ? '' : (u.display_name || u.username).charAt(0).toUpperCase();

        let icons = '';
        if (u.is_muted) icons += `<span class="material-symbols-outlined" style="color:var(--red);">mic_off</span>`;
        if (u.is_deafened) icons += `<span class="material-symbols-outlined" style="color:var(--red);">headset_off</span>`;

        row.innerHTML = `
            <div class="vu-avatar" style="${avStyle}">${avLetter}</div>
            <div class="vu-name">${escapeHtml(u.display_name || u.username)}</div>
            <div class="vu-icons">${icons}</div>
        `;
        container.appendChild(row);
    });
}

function showFriendsView() {
    state.activeTab = 'home';
    state.currentChannelId = null;
    state.currentDmPeerId = null;

    document.getElementById('view-friends').classList.remove('hidden');
    document.getElementById('view-chat').classList.add('hidden');
    document.getElementById('view-voice-stage').classList.add('hidden');

    document.getElementById('channel-header-icon').textContent = 'group';
    document.getElementById('channel-header-title').textContent = t('friends', 'Friends');
    document.getElementById('channel-header-desc').textContent = '';
    document.getElementById('btn-header-call').classList.add('hidden');
    document.getElementById('btn-toggle-members').classList.add('hidden');

    renderFriendsTab(state.activeFriendsTab || 'online');
}

function selectTextChannel(roomId, channelId, channelName) {
    state.currentRoomId = roomId;
    state.currentChannelId = channelId;
    state.currentDmPeerId = null;

    document.querySelectorAll('.sidebar-item').forEach(b => b.classList.remove('active'));
    document.getElementById('view-friends').classList.add('hidden');
    document.getElementById('view-chat').classList.remove('hidden');
    document.getElementById('view-voice-stage').classList.add('hidden');

    document.getElementById('channel-header-icon').textContent = 'tag';
    document.getElementById('channel-header-title').textContent = channelName;
    document.getElementById('channel-header-desc').textContent = `Welcome to #${channelName}!`;
    document.getElementById('chat-text-input').placeholder = `Message #${channelName}`;
    document.getElementById('btn-header-call').classList.add('hidden');
    document.getElementById('btn-toggle-members').classList.remove('hidden');

    document.getElementById('chat-messages-list').innerHTML = '';
    window.pywebview.api.get_history('channel', channelId);
}

function selectDmUser(peerId, peerName) {
    state.currentDmPeerId = peerId;
    state.currentChannelId = null;
    state.currentRoomId = null;

    document.querySelectorAll('.sidebar-item').forEach(b => b.classList.remove('active'));
    document.getElementById('view-friends').classList.add('hidden');
    document.getElementById('view-chat').classList.remove('hidden');
    document.getElementById('view-voice-stage').classList.add('hidden');

    document.getElementById('channel-header-icon').textContent = 'forum';
    document.getElementById('channel-header-title').textContent = `@${peerName}`;
    document.getElementById('channel-header-desc').textContent = `Direct message with ${peerName}`;
    document.getElementById('chat-text-input').placeholder = `Message @${peerName}`;
    document.getElementById('btn-header-call').classList.remove('hidden');
    document.getElementById('btn-toggle-members').classList.add('hidden');

    document.getElementById('chat-messages-list').innerHTML = '';
    window.pywebview.api.get_history('dm', peerId);
}

function selectVoiceChannel(roomId, channelId, channelName) {
    state.currentVoiceChannelId = channelId;
    state.currentVoiceRoomId = roomId;

    document.getElementById('voice-status-bar').classList.remove('hidden');
    document.getElementById('voice-status-channel').textContent = `${channelName} / Connected`;

    document.getElementById('view-friends').classList.add('hidden');
    document.getElementById('view-chat').classList.add('hidden');
    document.getElementById('view-voice-stage').classList.remove('hidden');

    document.getElementById('channel-header-icon').textContent = 'volume_up';
    document.getElementById('channel-header-title').textContent = channelName;
    document.getElementById('channel-header-desc').textContent = `Voice Channel - RTC Connected`;
    document.getElementById('btn-header-call').classList.add('hidden');
    document.getElementById('btn-toggle-members').classList.add('hidden');

    renderVoiceStage(channelName);
    window.pywebview.api.join_voice(roomId, channelId);
}

function onVoiceStateUpdate(payload) {
    const { user_id, room_id, channel_id, action, is_muted, is_deafened } = payload;
    if (!channel_id) return;

    state.voiceUsers[channel_id] = state.voiceUsers[channel_id] || [];

    if (action === 'join') {
        const u = state.users[user_id] || { user_id, username: user_id, display_name: user_id };
        const existing = state.voiceUsers[channel_id].find(x => x.user_id === user_id);
        if (!existing) {
            state.voiceUsers[channel_id].push({
                user_id,
                username: u.username || user_id,
                display_name: u.display_name || u.username || user_id,
                avatar_color: u.avatar_color || '#5865F2',
                avatar_image: u.avatar_image || '',
                is_muted: !!is_muted,
                is_deafened: !!is_deafened,
                is_speaking: false
            });
        }
    } else if (action === 'leave') {
        state.voiceUsers[channel_id] = state.voiceUsers[channel_id].filter(x => x.user_id !== user_id);
        if (user_id === state.user?.user_id && state.currentVoiceChannelId === channel_id) {
            state.currentVoiceChannelId = null;
            state.currentVoiceRoomId = null;
            document.getElementById('voice-status-bar').classList.add('hidden');
            if (!document.getElementById('view-voice-stage').classList.contains('hidden')) {
                showFriendsView();
            }
        }
    }

    const cont = document.getElementById(`voice-users-${channel_id}`);
    if (cont) {
        renderChannelVoiceUsers(cont, channel_id);
    }
    if (state.currentVoiceChannelId === channel_id) {
        renderVoiceStage(channel_id);
    }
}

// ---------------- Custom Prompt Modal Helper ----------------

function showPromptModal({ title, desc, placeholder = '', initialValue = '', confirmText = 'Confirm', showChannelType = false, onConfirm }) {
    const modal = document.getElementById('modal-prompt');
    document.getElementById('prompt-title').textContent = title || 'VimCord';
    document.getElementById('prompt-desc').textContent = desc || '';
    const input = document.getElementById('prompt-input');
    input.value = initialValue;
    input.placeholder = placeholder;

    const typeRow = document.getElementById('prompt-channel-type-row');
    if (typeRow) {
        typeRow.classList.toggle('hidden', !showChannelType);
        if (showChannelType) {
            document.getElementById('prompt-channel-type').value = 'text';
        }
    }

    document.getElementById('btn-prompt-confirm').textContent = confirmText;
    currentPromptCallback = onConfirm;
    modal.classList.remove('hidden');
    input.focus();
}

function closePromptModal() {
    document.getElementById('modal-prompt').classList.add('hidden');
    currentPromptCallback = null;
}

function promptCreateRoom() {
    showPromptModal({
        title: 'Create a Server',
        desc: 'Enter a name for your new server:',
        placeholder: 'e.g. My Gaming Server',
        confirmText: 'Create Server',
        showChannelType: false,
        onConfirm: (val) => {
            if (val && val.trim()) {
                window.pywebview.api.create_room(val.trim());
            }
        }
    });
}

function promptJoinInvite() {
    showPromptModal({
        title: 'Join a Server',
        desc: 'Enter an invite link or code:',
        placeholder: 'e.g. vc-abc12345',
        confirmText: 'Join Server',
        showChannelType: false,
        onConfirm: (code) => {
            const cleanCode = code.trim().replace(/^.*\/invite\//, '').replace(/^.*code=/, '');
            if (cleanCode) {
                window.pywebview.api.join_room_by_invite(cleanCode);
            }
        }
    });
}

function promptCreateChannel() {
    if (!state.currentRoomId) return;
    showPromptModal({
        title: 'Create Channel',
        desc: 'Enter channel name and select type:',
        placeholder: 'e.g. general',
        confirmText: 'Create Channel',
        showChannelType: true,
        onConfirm: (name, channelType) => {
            if (name && name.trim()) {
                window.pywebview.api.create_channel(state.currentRoomId, name.trim(), channelType || 'text');
            }
        }
    });
}

function promptServerInvite() {
    if (!state.currentRoomId) return;
    window.pywebview.api.create_room_invite(state.currentRoomId);
}

// ---------------- Server & Room Structure Events ----------------

function onRoomCreated(room) {
    if (!room || !room.room_id) return;
    state.rooms[room.room_id] = room;
    renderServerRail();
    switchMode('server', room.room_id);
    showToast(`Server "${room.name}" created!`);
}

function onRoomDeleted(payload) {
    const roomId = typeof payload === 'string' ? payload : payload.room_id;
    if (state.rooms[roomId]) {
        delete state.rooms[roomId];
        renderServerRail();
        if (state.currentRoomId === roomId) {
            switchMode('home');
        }
        showToast('Server deleted.');
    }
}

function onChannelCreated(payload) {
    const { room_id, channel } = payload;
    if (state.rooms[room_id]) {
        state.rooms[room_id].channels = state.rooms[room_id].channels || [];
        if (!state.rooms[room_id].channels.some(c => c.channel_id === channel.channel_id)) {
            state.rooms[room_id].channels.push(channel);
        }
        if (state.currentRoomId === room_id) {
            renderServerChannels(state.rooms[room_id]);
        }
        showToast(`Channel "${channel.name}" created.`);
    }
}

function onChannelDeleted(payload) {
    const { room_id, channel_id } = payload;
    if (state.rooms[room_id] && state.rooms[room_id].channels) {
        state.rooms[room_id].channels = state.rooms[room_id].channels.filter(c => c.channel_id !== channel_id);
        if (state.currentRoomId === room_id) {
            renderServerChannels(state.rooms[room_id]);
        }
        showToast('Channel deleted.');
    }
}

function onChannelRenamed(payload) {
    const { room_id, channel_id, name } = payload;
    if (state.rooms[room_id] && state.rooms[room_id].channels) {
        const ch = state.rooms[room_id].channels.find(c => c.channel_id === channel_id);
        if (ch) ch.name = name;
        if (state.currentRoomId === room_id) {
            renderServerChannels(state.rooms[room_id]);
        }
    }
}

function onRoomInviteCreated(payload) {
    const code = payload.code || payload;
    if (navigator.clipboard) {
        navigator.clipboard.writeText(code);
    }
    showToast(`Invite code copied: ${code}`);
}

function onRoomInviteJoined(payload) {
    if (payload.success && payload.data) {
        const room = payload.data;
        state.rooms[room.room_id] = room;
        renderServerRail();
        switchMode('server', room.room_id);
        showToast(`Joined server "${room.name}"!`);
    } else {
        showToast(payload.message || 'Failed to join server.');
    }
}

function onLeaveRoomResp(payload) {
    if (payload.success) {
        const roomId = payload.room_id;
        if (state.rooms[roomId]) {
            delete state.rooms[roomId];
            renderServerRail();
            if (state.currentRoomId === roomId) {
                switchMode('home');
            }
        }
        showToast('Left server.');
    } else {
        showToast(payload.message || 'Could not leave server.');
    }
}

function onRoomMembersResp(payload) {
    const { room_id, members } = payload;
    if (state.currentRoomId === room_id) {
        renderMemberList(members);
    }
}

function renderMemberList(members) {
    const list = document.getElementById('members-list-content');
    if (!list) return;
    list.innerHTML = '';
    (members || []).forEach(m => {
        const isOnline = Boolean(m.is_online || state.users[m.user_id]?.online);
        const item = document.createElement('div');
        item.className = 'member-item';
        item.style.display = 'flex';
        item.style.alignItems = 'center';
        item.style.padding = '6px 8px';
        item.style.borderRadius = '4px';
        item.style.cursor = 'pointer';

        const avStyle = m.avatar_image ? `background-image: url(data:image/png;base64,${m.avatar_image});` : `background-color: ${m.avatar_color || '#5865F2'};`;
        const avLetter = m.avatar_image ? '' : (m.display_name || m.username).charAt(0).toUpperCase();

        item.innerHTML = `
            <div class="avatar-wrap">
                <div class="avatar" style="${avStyle}">${avLetter}</div>
                <div class="status-dot ${isOnline ? 'status-online' : 'status-offline'}"></div>
            </div>
            <div class="member-info" style="margin-left: 8px;">
                <div class="member-name" style="font-weight: 600; color: var(--text-bright);">${escapeHtml(m.display_name || m.username)}</div>
                <div class="member-role" style="font-size: 11px; color: var(--text-muted);">${m.is_owner ? 'Owner' : 'Member'}</div>
            </div>
        `;
        if (m.user_id !== state.user?.user_id) {
            item.onclick = () => selectDmUser(m.user_id, m.display_name || m.username);
        }
        list.appendChild(item);
    });
}

// ---------------- Chat & File Upload ----------------

async function chooseAttachment() {
    const res = await window.pywebview.api.open_file_dialog();
    if (!res) return;
    if (res.error) {
        showToast(res.error);
        return;
    }
    setAttachment(res);
}

function setAttachment(att) {
    state.currentAttachment = att;
    const strip = document.getElementById('attachment-preview-strip');
    const nameEl = document.getElementById('preview-filename');
    const sizeEl = document.getElementById('preview-filesize');
    const thumbImg = document.getElementById('preview-thumb-img');
    const thumbIcon = document.getElementById('preview-thumb-icon');

    nameEl.textContent = att.name;
    sizeEl.textContent = formatBytes(att.size);

    if (att.is_image && att.data) {
        thumbImg.src = `data:image/png;base64,${att.data}`;
        thumbImg.classList.remove('hidden');
        thumbIcon.classList.add('hidden');
    } else {
        thumbImg.classList.add('hidden');
        thumbIcon.classList.remove('hidden');
    }

    strip.classList.remove('hidden');
}

function clearAttachment() {
    state.currentAttachment = null;
    document.getElementById('attachment-preview-strip').classList.add('hidden');
}

function sendMessage() {
    const input = document.getElementById('chat-text-input');
    const text = input.value.trim();
    if (!text && !state.currentAttachment) return;

    const targetType = state.currentDmPeerId ? 'dm' : 'channel';
    const targetId = state.currentDmPeerId || state.currentChannelId;
    if (!targetId) return;

    let imgData = "";
    let fileData = "";
    let fileName = "";
    let fileSize = 0;

    if (state.currentAttachment) {
        if (state.currentAttachment.is_image) {
            imgData = state.currentAttachment.data;
        } else {
            fileData = state.currentAttachment.data;
            fileName = state.currentAttachment.name;
            fileSize = state.currentAttachment.size;
        }
    }

    const localMsg = {
        msg_id: `temp-${Date.now()}`,
        sender_id: state.user?.user_id,
        sender_name: state.user?.display_name || state.user?.username,
        target_type: targetType,
        target_id: targetId,
        content: text,
        image_data: imgData,
        file_data: fileData,
        file_name: fileName,
        file_size: fileSize,
        timestamp: Date.now() / 1000,
        pending: false
    };

    appendChatMessage(localMsg);
    input.value = '';
    clearAttachment();

    window.pywebview.api.send_chat_message(
        targetType, targetId, text,
        imgData, '', 0.0,
        fileData, fileName, fileSize
    );
}

function onChatMessageReceived(msg) {
    const activeTargetId = state.currentDmPeerId || state.currentChannelId;
    if (msg.target_id === activeTargetId || (msg.target_type === 'dm' && msg.sender_id === state.currentDmPeerId)) {
        appendChatMessage(msg);
    } else if (!state.dndMode && msg.sender_id !== state.user?.user_id) {
        showToast(`New message from ${msg.sender_name || 'User'}`);
    }
}

function onHistoryReceived(data) {
    const list = document.getElementById('chat-messages-list');
    list.innerHTML = '';
    (data.messages || []).forEach(m => appendChatMessage(m, false));
    scrollToBottom();
}

function onMessageDeleted(data) {
    const el = document.getElementById(`msg-${data.msg_id}`);
    if (el) el.remove();
}

function appendChatMessage(msg, autoScroll = true) {
    const list = document.getElementById('chat-messages-list');
    const existing = document.getElementById(`msg-${msg.msg_id}`);
    if (existing) return;

    const row = document.createElement('div');
    row.className = 'chat-message-row';
    row.id = `msg-${msg.msg_id}`;

    const senderUser = state.users[msg.sender_id] || {};
    const avColor = senderUser.avatar_color || '#5865F2';
    const avImg = senderUser.avatar_image || '';
    const senderName = msg.sender_name || senderUser.display_name || senderUser.username || 'User';

    const avStyle = avImg ? `background-image: url(data:image/png;base64,${avImg});` : `background-color: ${avColor};`;
    const avLetter = avImg ? '' : senderName.charAt(0).toUpperCase();

    const timeStr = new Date((msg.timestamp || Date.now() / 1000) * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    let mediaHtml = '';
    if (msg.image_data) {
        mediaHtml += `<div class="msg-image-wrap"><img src="data:image/png;base64,${msg.image_data}" class="msg-image" alt="Image" onclick="openLightbox(this.src)"></div>`;
    }
    if (msg.file_data) {
        mediaHtml += `
            <div class="msg-file-card" onclick="downloadFile('${escapeHtml(msg.file_name)}', '${msg.file_data}')">
                <span class="material-symbols-outlined" style="font-size: 28px; color: var(--accent);">description</span>
                <div class="file-card-info">
                    <div class="file-name">${escapeHtml(msg.file_name)}</div>
                    <div class="file-size">${formatBytes(msg.file_size)} • Click to Download</div>
                </div>
            </div>
        `;
    }
    if (msg.voice_data) {
        mediaHtml += `
            <div class="msg-voice-card">
                <button class="voice-play-btn" onclick="playVoiceMsg('${msg.voice_data}', ${msg.voice_duration || 0})">
                    <span class="material-symbols-outlined">play_arrow</span>
                </button>
                <div class="voice-wave-bar"></div>
                <span class="voice-duration">${(msg.voice_duration || 0).toFixed(1)}s</span>
            </div>
        `;
    }

    const isMine = msg.sender_id === state.user?.user_id;
    let deleteHtml = '';
    if (isMine) {
        deleteHtml = `
            <button class="msg-delete-btn" title="Delete Message" onclick="deleteMessage('${msg.msg_id}', '${msg.target_type}', '${msg.target_id}')">
                <span class="material-symbols-outlined" style="font-size:14px;">delete</span>
            </button>
        `;
    }

    row.innerHTML = `
        <div class="avatar-wrap">
            <div class="avatar" style="${avStyle}">${avLetter}</div>
        </div>
        <div class="msg-content-wrap">
            <div class="msg-header">
                <span class="msg-sender">${escapeHtml(senderName)}</span>
                <span class="msg-time">${timeStr}</span>
                ${deleteHtml}
            </div>
            ${msg.content ? `<div class="msg-text">${escapeHtml(msg.content)}</div>` : ''}
            ${mediaHtml}
        </div>
    `;

    list.appendChild(row);
    if (autoScroll) scrollToBottom();
}

function scrollToBottom() {
    const container = document.getElementById('chat-messages-container');
    if (container) {
        container.scrollTop = container.scrollHeight;
    }
}

function deleteMessage(msgId, targetType, targetId) {
    window.pywebview.api.delete_message(msgId, targetType, targetId);
    const el = document.getElementById(`msg-${msgId}`);
    if (el) el.remove();
}

async function downloadFile(name, b64) {
    showToast(`Downloading ${name}...`);
    const res = await window.pywebview.api.save_file_to_disk(name, b64);
    if (res && res.success) {
        showToast(`Saved to Downloads: ${name}`);
    } else {
        showToast(`Failed to save: ${res?.error || 'Error'}`);
    }
}

function playVoiceMsg(b64, dur) {
    window.pywebview.api.play_voice_message(b64, dur);
}

// ---------------- Voice Message Recording ----------------

function toggleVoiceRecording() {
    const btn = document.getElementById('btn-voice-msg');
    if (!state.isRecordingVoice) {
        state.isRecordingVoice = true;
        btn.classList.add('recording');
        state.voiceRecordStart = Date.now();
        window.pywebview.api.start_voice_record();
        showToast('Recording voice message... Click again to stop & send');
    } else {
        state.isRecordingVoice = false;
        btn.classList.remove('recording');
        stopAndSendVoiceMsg();
    }
}

async function stopAndSendVoiceMsg() {
    const res = await window.pywebview.api.stop_voice_record();
    if (res && res.data && res.duration > 0.3) {
        const targetType = state.currentDmPeerId ? 'dm' : 'channel';
        const targetId = state.currentDmPeerId || state.currentChannelId;
        if (targetId) {
            window.pywebview.api.send_chat_message(targetType, targetId, '', '', res.data, res.duration, '', '', 0);
        }
    } else {
        showToast('Voice message too short');
    }
}

// ---------------- Direct Calls ----------------

function onIncomingCall(data) {
    state.activeCallId = data.call_id;
    document.getElementById('incoming-caller-name').textContent = data.from_username;
    document.getElementById('incoming-caller-avatar').textContent = data.from_username.charAt(0).toUpperCase();
    document.getElementById('modal-incoming-call').classList.remove('hidden');
}

function acceptIncomingCall() {
    document.getElementById('modal-incoming-call').classList.add('hidden');
    if (state.activeCallId) {
        window.pywebview.api.accept_call(state.activeCallId);
    }
}

function declineIncomingCall() {
    document.getElementById('modal-incoming-call').classList.add('hidden');
    if (state.activeCallId) {
        window.pywebview.api.decline_call(state.activeCallId);
        state.activeCallId = null;
    }
}

function onCallAccepted(data) {
    state.activeCallId = data.call_id;
    document.getElementById('dm-call-widget').classList.remove('hidden');
    document.getElementById('dm-call-status-text').textContent = 'In Call';
    document.getElementById('call-peer-name').textContent = data.peer_name;
    document.getElementById('call-peer-avatar').textContent = data.peer_name.charAt(0).toUpperCase();

    startCallTimer();
}

function onCallTerminated(evtName, payload) {
    stopCallTimer();
    state.activeCallId = null;
    document.getElementById('dm-call-widget').classList.add('hidden');
    document.getElementById('modal-incoming-call').classList.add('hidden');
    if (evtName === 'call_failed') {
        showToast(`Call failed: ${payload.reason || 'Disconnected'}`);
    } else {
        showToast('Call ended');
    }
}

function startCallTimer() {
    stopCallTimer();
    state.callStartTime = Date.now();
    state.callTimerInterval = setInterval(() => {
        const elapsed = Math.floor((Date.now() - state.callStartTime) / 1000);
        const m = Math.floor(elapsed / 60);
        const s = elapsed % 60;
        document.getElementById('dm-call-timer').textContent = `${m < 10 ? '0' : ''}${m}:${s < 10 ? '0' : ''}${s}`;
    }, 1000);
}

function stopCallTimer() {
    if (state.callTimerInterval) {
        clearInterval(state.callTimerInterval);
        state.callTimerInterval = null;
    }
}

// ---------------- Voice Stage & Speaking ----------------

function renderVoiceStage(chName) {
    const grid = document.getElementById('voice-participants-grid');
    grid.innerHTML = '';

    const users = state.voiceUsers[state.currentVoiceChannelId] || [];
    if (state.user && !users.some(u => u.user_id === state.user.user_id)) {
        users.push({
            user_id: state.user.user_id,
            username: state.user.username,
            display_name: state.user.display_name || state.user.username,
            avatar_color: state.user.avatar_color || '#5865F2',
            avatar_image: state.user.avatar_image || '',
            is_speaking: false
        });
    }

    users.forEach(u => {
        const card = document.createElement('div');
        card.className = `voice-card ${u.is_speaking ? 'speaking' : ''}`;
        card.id = `stage-card-${u.user_id}`;

        const avStyle = u.avatar_image ? `background-image: url(data:image/png;base64,${u.avatar_image});` : `background-color: ${u.avatar_color || '#5865F2'};`;
        const avLetter = u.avatar_image ? '' : (u.display_name || u.username).charAt(0).toUpperCase();

        card.innerHTML = `
            <div class="voice-card-avatar" style="${avStyle}">${avLetter}</div>
            <div class="voice-card-name">${escapeHtml(u.display_name || u.username)}</div>
        `;
        grid.appendChild(card);
    });
}

function onLocalSpeaking(data) {
    if (!state.user) return;
    updateUserSpeakingState(state.user.user_id, data.is_speaking);
}

function onPeerSpeaking(data) {
    updateUserSpeakingState(data.user_id, data.is_speaking);
}

function updateUserSpeakingState(userId, isSpeaking) {
    // 1. Stage Card
    const card = document.getElementById(`stage-card-${userId}`);
    if (card) card.classList.toggle('speaking', isSpeaking);

    // 2. Channel user tree
    if (state.currentVoiceChannelId) {
        const treeUser = document.getElementById(`v-user-${state.currentVoiceChannelId}-${userId}`);
        if (treeUser) treeUser.classList.toggle('speaking', isSpeaking);
    }
}

// ---------------- Screen Sharing ----------------

function toggleScreenShare() {
    state.isSharingScreen = !state.isSharingScreen;
    const targetType = state.currentDmPeerId ? 'dm' : 'channel';
    const targetId = state.currentDmPeerId || state.currentVoiceChannelId || state.currentChannelId;

    if (state.isSharingScreen) {
        window.pywebview.api.start_screen_share(targetType, targetId);
        showToast('Screen sharing started');
    } else {
        window.pywebview.api.stop_screen_share(targetType, targetId);
        showToast('Screen sharing stopped');
        document.getElementById('voice-screen-stream-box').classList.add('hidden');
        document.getElementById('dm-call-screen-container').classList.add('hidden');
    }
}

function onScreenFrame(data) {
    // Stage Screen Box
    const stageBox = document.getElementById('voice-screen-stream-box');
    const stageImg = document.getElementById('voice-stage-screen-img');
    if (stageBox && stageImg) {
        stageBox.classList.remove('hidden');
        stageImg.src = `data:image/jpeg;base64,${data.frame}`;
    }

    // Direct Call Screen Box
    const dmBox = document.getElementById('dm-call-screen-container');
    const dmImg = document.getElementById('dm-call-screen-img');
    if (dmBox && dmImg && state.activeCallId) {
        dmBox.classList.remove('hidden');
        dmImg.src = `data:image/jpeg;base64,${data.frame}`;
    }
}

function onScreenStop(data) {
    document.getElementById('voice-screen-stream-box').classList.add('hidden');
    document.getElementById('dm-call-screen-container').classList.add('hidden');
    showToast('Screen share ended by peer');
}

// ---------------- Audio Controls (Mute / Deafen) ----------------

function toggleMic() {
    state.isMuted = !state.isMuted;
    const btn = document.getElementById('btn-toggle-mic');
    btn.classList.toggle('active', state.isMuted);
    document.getElementById('mic-icon-svg').textContent = state.isMuted ? 'mic_off' : 'mic';
    btn.title = state.isMuted ? t('unmute_mic', 'Unmute') : t('mute_mic', 'Mute');
    window.pywebview.api.set_mic_muted(state.isMuted);
}

function toggleDeafen() {
    state.isDeafened = !state.isDeafened;
    const btn = document.getElementById('btn-toggle-deafen');
    btn.classList.toggle('active', state.isDeafened);
    document.getElementById('deafen-icon-svg').textContent = state.isDeafened ? 'headset_off' : 'headphones';
    btn.title = state.isDeafened ? t('undeafen_audio', 'Undeafen') : t('deafen_audio', 'Deafen');
    window.pywebview.api.set_deafened(state.isDeafened);
}

// ---------------- Settings Dialog (3-Page PyQt Parity) ----------------

function openSettings() {
    document.getElementById('modal-settings').classList.remove('hidden');
    if (!state.user) return;

    // Load initial settings drafts
    settingsDraft.displayName = state.user.display_name || state.user.username;
    settingsDraft.customStatus = state.user.status_text || '';
    settingsDraft.bio = state.user.bio || '';
    settingsDraft.avatarColor = state.user.avatar_color || '#5865F2';
    settingsDraft.bannerColor = state.user.banner_color || '#5865F2';
    settingsDraft.avatarImage = state.user.avatar_image || '';
    settingsDraft.bannerImage = state.user.banner_image || '';

    // Populate Account Page
    document.getElementById('settings-display-name').value = settingsDraft.displayName;
    document.getElementById('settings-username').value = `@${state.user.username}`;
    document.getElementById('settings-custom-status').value = settingsDraft.customStatus;
    document.getElementById('settings-bio').value = settingsDraft.bio;

    renderSettingsPalettes();
    refreshProfilePreview();
}

function closeSettings() {
    if (state.isTestingMic) {
        toggleMicTest();
    }
    document.getElementById('modal-settings').classList.add('hidden');
}

function renderSettingsPalettes() {
    const avCont = document.getElementById('avatar-color-palette');
    const bnCont = document.getElementById('banner-color-palette');
    avCont.innerHTML = '';
    bnCont.innerHTML = '';

    DISCORD_COLORS.forEach(c => {
        // Avatar color swatch
        const avBtn = document.createElement('button');
        avBtn.className = `color-swatch ${settingsDraft.avatarColor.toLowerCase() === c.hex.toLowerCase() ? 'active' : ''}`;
        avBtn.style.backgroundColor = c.hex;
        avBtn.title = c.name;
        avBtn.onclick = () => {
            settingsDraft.avatarColor = c.hex;
            renderSettingsPalettes();
            refreshProfilePreview();
        };
        avCont.appendChild(avBtn);

        // Banner color swatch
        const bnBtn = document.createElement('button');
        bnBtn.className = `color-swatch ${settingsDraft.bannerColor.toLowerCase() === c.hex.toLowerCase() ? 'active' : ''}`;
        bnBtn.style.backgroundColor = c.hex;
        bnBtn.title = c.name;
        bnBtn.onclick = () => {
            settingsDraft.bannerColor = c.hex;
            renderSettingsPalettes();
            refreshProfilePreview();
        };
        bnCont.appendChild(bnBtn);
    });
}

function refreshProfilePreview() {
    // Banner preview
    const bannerEl = document.getElementById('settings-banner-preview');
    if (settingsDraft.bannerImage) {
        bannerEl.style.backgroundImage = `url(data:image/png;base64,${settingsDraft.bannerImage})`;
        bannerEl.style.backgroundColor = '';
    } else {
        bannerEl.style.backgroundImage = '';
        bannerEl.style.backgroundColor = settingsDraft.bannerColor || '#5865F2';
    }

    // Avatar preview
    const avEl = document.getElementById('settings-avatar-preview');
    const dName = document.getElementById('settings-display-name').value.trim() || state.user?.username || 'User';
    if (settingsDraft.avatarImage) {
        avEl.style.backgroundImage = `url(data:image/png;base64,${settingsDraft.avatarImage})`;
        avEl.textContent = '';
    } else {
        avEl.style.backgroundImage = '';
        avEl.style.backgroundColor = settingsDraft.avatarColor || '#5865F2';
        avEl.textContent = dName.charAt(0).toUpperCase();
    }

    // Names preview
    document.getElementById('settings-disp-preview').textContent = dName;
    document.getElementById('settings-user-preview').textContent = `@${state.user?.username || 'user'} • ID: ${state.user?.user_id || ''}`;
    const stVal = document.getElementById('settings-custom-status').value.trim();
    document.getElementById('settings-status-preview').textContent = stVal || 'Online';
}

async function uploadBanner() {
    const res = await window.pywebview.api.open_file_dialog();
    if (!res) return;
    if (res.error) {
        showToast(res.error);
        return;
    }
    if (!res.is_image) {
        showToast('Please choose an image file (PNG/JPG/WEBP)');
        return;
    }
    settingsDraft.bannerImage = res.data;
    refreshProfilePreview();
    showToast('Banner loaded. Click "Save Profile Changes" to apply.');
}

function removeBanner() {
    settingsDraft.bannerImage = '';
    refreshProfilePreview();
    showToast('Banner image cleared');
}

async function uploadAvatar() {
    const res = await window.pywebview.api.open_file_dialog();
    if (!res) return;
    if (res.error) {
        showToast(res.error);
        return;
    }
    if (!res.is_image) {
        showToast('Please choose an image file (PNG/JPG/WEBP)');
        return;
    }
    settingsDraft.avatarImage = res.data;
    refreshProfilePreview();
    showToast('Avatar loaded. Click "Save Profile Changes" to apply.');
}

function removeAvatar() {
    settingsDraft.avatarImage = '';
    refreshProfilePreview();
    showToast('Avatar reset to default accent');
}

function saveProfileSettings() {
    const disp = document.getElementById('settings-display-name').value.trim();
    const st = document.getElementById('settings-custom-status').value.trim();
    const bio = document.getElementById('settings-bio').value.trim();

    window.pywebview.api.update_profile(
        disp, st,
        settingsDraft.avatarColor, settingsDraft.bannerColor,
        settingsDraft.avatarImage, settingsDraft.bannerImage,
        bio
    );

    if (state.user) {
        state.user.display_name = disp;
        state.user.status_text = st;
        state.user.bio = bio;
        state.user.avatar_color = settingsDraft.avatarColor;
        state.user.banner_color = settingsDraft.bannerColor;
        state.user.avatar_image = settingsDraft.avatarImage;
        state.user.banner_image = settingsDraft.bannerImage;
        updateUserPanelProfile();
    }

    showToast('Profile updated successfully!');
    closeSettings();
}

function onProfileUpdateResp(payload) {
    if (payload.success && payload.user) {
        Object.assign(state.user, payload.user);
        updateUserPanelProfile();
    }
}

function savePasswordChange() {
    const oldP = document.getElementById('input-old-pass').value;
    const newP = document.getElementById('input-new-pass').value;
    if (!oldP || !newP) {
        showToast('Please fill in both password fields');
        return;
    }
    if (newP.length < 4) {
        showToast('New password must be at least 4 characters');
        return;
    }
    window.pywebview.api.change_password(oldP, newP);
    document.getElementById('input-old-pass').value = '';
    document.getElementById('input-new-pass').value = '';
    showToast('Updating password...');
}

function onChangePasswordResp(payload) {
    showToast(payload.message || (payload.success ? 'Password updated successfully!' : 'Failed to change password'));
}

function renderPttSettings(isPtt, key) {
    document.getElementById('radio-ptt').checked = isPtt;
    document.getElementById('radio-vad').checked = !isPtt;
    document.getElementById('ptt-key-display').textContent = key || 'Space';
    document.getElementById('ptt-keybind-container').classList.toggle('hidden', !isPtt);
    document.getElementById('vad-slider-container').classList.toggle('hidden', isPtt);
}

function updateInputMode(isPtt) {
    state.pttMode = isPtt;
    document.getElementById('ptt-keybind-container').classList.toggle('hidden', !isPtt);
    document.getElementById('vad-slider-container').classList.toggle('hidden', isPtt);
    window.pywebview.api.set_ptt_config(isPtt, state.pttKey);
}

function startRecordKeybind() {
    const disp = document.getElementById('ptt-key-display');
    disp.textContent = 'Press any key / mouse button...';
    disp.classList.add('pulsing');
    window.pywebview.api.record_keybind_start();
}

function onKeybindCaptured(data) {
    state.pttKey = data.key;
    const disp = document.getElementById('ptt-key-display');
    disp.textContent = data.key;
    disp.classList.remove('pulsing');
    showToast(`PTT key bound to: ${data.key}`);
}

function toggleMicTest() {
    state.isTestingMic = !state.isTestingMic;
    const btn = document.getElementById('btn-test-mic');
    if (state.isTestingMic) {
        btn.textContent = 'Stop Checking';
        window.pywebview.api.start_mic_test();
    } else {
        btn.textContent = "Let's Check";
        window.pywebview.api.stop_mic_test();
        document.getElementById('mic-level-bar').style.width = '0%';
    }
}

function onMicTestLevel(data) {
    if (state.isTestingMic) {
        document.getElementById('mic-level-bar').style.width = `${data.level}%`;
    }
}

function applyTheme(th) {
    document.body.className = `theme-${th}`;
    document.querySelectorAll('input[name="theme_select"]').forEach(radio => {
        radio.checked = (radio.value === th);
    });
}

function applyLanguage(lng) {
    state.language = lng;
    document.querySelectorAll('input[name="lang_select"]').forEach(radio => {
        radio.checked = (radio.value === lng);
    });
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.dataset.i18n;
        if (I18N[lng] && I18N[lng][key]) {
            el.textContent = I18N[lng][key];
        }
    });
}

function populateAudioDevices(devs) {
    const inSel = document.getElementById('select-audio-input');
    const outSel = document.getElementById('select-audio-output');
    if (!inSel || !outSel) return;

    inSel.innerHTML = '<option value="">Default System Microphone</option>';
    outSel.innerHTML = '<option value="">Default System Speakers</option>';

    (devs.inputs || []).forEach(d => {
        const opt = document.createElement('option');
        opt.value = d.id;
        opt.textContent = d.name;
        inSel.appendChild(opt);
    });

    (devs.outputs || []).forEach(d => {
        const opt = document.createElement('option');
        opt.value = d.id;
        opt.textContent = d.name;
        outSel.appendChild(opt);
    });
}

// ---------------- Friends Tab Logic ----------------

function renderFriendsTab(tab) {
    state.activeFriendsTab = tab;
    const listCont = document.getElementById('friends-list-container');
    const addCont = document.getElementById('friends-add-container');

    if (tab === 'add') {
        listCont.classList.add('hidden');
        addCont.classList.remove('hidden');
        return;
    }

    listCont.classList.remove('hidden');
    addCont.classList.add('hidden');

    const itemsCont = document.getElementById('friends-items-list');
    itemsCont.innerHTML = '';

    let filtered = state.friends;
    if (tab === 'online') {
        filtered = state.friends.filter(f => {
            const fid = f.peer_id || f.user_id;
            const isOnline = Boolean(state.users[fid]?.online || state.users[fid]?.is_online || f.online || f.is_online);
            return isOnline && f.friendship_status === 'accepted';
        });
    } else if (tab === 'all') {
        filtered = state.friends.filter(f => f.friendship_status === 'accepted');
    } else if (tab === 'pending') {
        filtered = state.friends.filter(f => f.friendship_status === 'pending');
    }

    document.getElementById('friends-count-label').textContent = `${tab.toUpperCase()} — ${filtered.length}`;

    if (filtered.length === 0) {
        itemsCont.innerHTML = `<div style="text-align: center; color: var(--text-muted); padding: 40px;">No friends found in this list.</div>`;
        return;
    }

    filtered.forEach(f => {
        const friendId = f.peer_id || f.user_id;
        const username = f.username || f.peer_name || '';
        const displayName = f.display_name || f.peer_display_name || username;
        const isOnline = Boolean(state.users[friendId]?.online || state.users[friendId]?.is_online || f.online || f.is_online);
        const statusText = f.status_text || state.users[friendId]?.status_text || (isOnline ? 'Online' : 'Offline');

        const row = document.createElement('div');
        row.className = 'friend-row';

        const avStyle = f.avatar_image ? `background-image: url(data:image/png;base64,${f.avatar_image});` : `background-color: ${f.avatar_color || '#5865F2'};`;
        const avLetter = f.avatar_image ? '' : displayName.charAt(0).toUpperCase();

        let actionsHtml = '';
        if (f.friendship_status === 'pending') {
            if (f.is_incoming) {
                actionsHtml = `
                    <button class="circle-btn" title="Accept" onclick="acceptFriend('${friendId}')" style="color: #23a55a;">
                        <span class="material-symbols-outlined">check</span>
                    </button>
                    <button class="circle-btn" title="Decline" onclick="declineFriend('${friendId}')" style="color: #f23f43;">
                        <span class="material-symbols-outlined">close</span>
                    </button>
                `;
            } else {
                actionsHtml = `<span style="font-size: 12px; color: var(--text-muted); padding: 4px 8px;">Pending Outgoing</span>`;
            }
        } else {
            actionsHtml = `
                <button class="circle-btn" title="Message" onclick="selectDmUser('${friendId}', '${escapeHtml(displayName)}')">
                    <span class="material-symbols-outlined">chat</span>
                </button>
                <button class="circle-btn" title="Call" onclick="startCallUser('${friendId}')">
                    <span class="material-symbols-outlined">call</span>
                </button>
            `;
        }

        row.innerHTML = `
            <div class="friend-info">
                <div class="avatar-wrap">
                    <div class="avatar" style="${avStyle}">${avLetter}</div>
                    <div class="status-dot ${isOnline ? 'status-online' : 'status-offline'}"></div>
                </div>
                <div class="friend-names">
                    <div class="disp-name">${escapeHtml(displayName)}</div>
                    <div class="user-handle">@${escapeHtml(username)} • ${escapeHtml(statusText)}</div>
                </div>
            </div>
            <div class="friend-actions">
                ${actionsHtml}
            </div>
        `;
        itemsCont.appendChild(row);
    });
}

function filterFriends(q) {
    const query = q.toLowerCase();
    document.querySelectorAll('.friend-row').forEach(row => {
        const text = row.textContent.toLowerCase();
        row.style.display = text.includes(query) ? 'flex' : 'none';
    });
}

function acceptFriend(peerId) {
    window.pywebview.api.accept_friend_request(peerId);
}

function declineFriend(peerId) {
    window.pywebview.api.decline_friend_request(peerId);
}

function startCallUser(peerId) {
    window.pywebview.api.start_call(peerId);
}

function sendFriendRequest() {
    const input = document.getElementById('input-add-friend-name');
    const u = input.value.trim();
    if (!u) return;
    window.pywebview.api.send_friend_request(u);
    input.value = '';
    showToast(`Friend request sent to ${u}`);
}

function onFriendsUpdate(fl) {
    state.friends = fl;
    renderDmList();
    renderFriendsTab(state.activeFriendsTab || 'online');
}

function onFriendRequestResp(res) {
    showToast(res.message);
}

function onUserPresence(user) {
    if (state.users[user.user_id]) {
        Object.assign(state.users[user.user_id], user);
    } else {
        state.users[user.user_id] = user;
    }

    const fr = state.friends.find(f => (f.peer_id || f.user_id) === user.user_id);
    if (fr) {
        fr.online = user.online;
        fr.is_online = user.online;
        fr.status_text = user.status_text;
    }

    renderDmList();
    renderFriendsTab(state.activeFriendsTab || 'online');
}

function onPong(data) {
    const el = document.getElementById('voice-status-channel');
    if (el && state.currentVoiceChannelId) {
        el.textContent = `Connected / ${data.ping_ms}ms`;
    }
}

// ---------------- Helpers & Toast ----------------

function openLightbox(src) {
    document.getElementById('lightbox-img').src = src;
    document.getElementById('lightbox-modal').classList.remove('hidden');
}

function showToast(text) {
    const cont = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.textContent = text;
    cont.appendChild(toast);
    setTimeout(() => {
        toast.style.animation = 'fadeOut 0.3s forwards';
        setTimeout(() => toast.remove(), 300);
    }, 3200);
}

function formatBytes(bytes) {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/[&<>"']/g, m => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    }[m]));
}
