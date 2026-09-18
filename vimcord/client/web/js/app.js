/**
 * VimCord Web Frontend Application Logic
 * Supports auth flow, chat, voice, direct calls, screen sharing, global hotkeys,
 * settings, i18n, custom prompt modals, server/channel management, and clipboard paste.
 */

// ---------------- Application State ----------------

const state = {
    user: null,
    rooms: {},
    users: {},
    friends: [],
    currentRoomId: null,
    currentChannelId: null,
    currentDmPeerId: null,
    activeTab: 'home', // 'home' or 'server'
    activeCallId: null,
    callStartTime: null,
    callTimerInterval: null,
    isMuted: false,
    isDeafened: false,
    isSharingScreen: false,
    isRecordingVoice: false,
    voiceRecordStart: 0,
    voiceRecordTimer: null,
    currentAttachment: null,
    pttMode: false,
    pttKey: 'Space',
    theme: 'dark',
    language: 'en',
    config: {}
};

let currentAuthTab = 'login';
let currentPromptCallback = null;

// ---------------- Localization Dictionary (Frontend) ----------------

const I18N = {
    en: {
        friends: "Friends", direct_messages: "DIRECT MESSAGES", text_channels: "TEXT CHANNELS",
        voice_channels: "VOICE CHANNELS", voice_connected: "Voice Connected", mute: "Mute",
        unmute: "Unmute", deafen: "Deafen", undeafen: "Undeafen", user_settings: "User Settings",
        about_me: "My Account", voice_channel: "Voice & Video", input_mode: "INPUT MODE",
        record_keybind: "Record Keybind", send_message: "Send a message...",
        pasted_from_clipboard: "Attached from clipboard", save: "Save", in_call: "In Call",
        create_server: "Create Server", join_server: "Join Server", create_channel: "Create Channel",
        server_invite: "Server Invite"
    },
    ru: {
        friends: "Друзья", direct_messages: "ЛИЧНЫЕ СООБЩЕНИЯ", text_channels: "ТЕКСТОВЫЕ КАНАЛЫ",
        voice_channels: "ГОЛОСОВЫЕ КАНАЛЫ", voice_connected: "Голос подключен", mute: "Заглушить микрофон",
        unmute: "Включить микрофон", deafen: "Заглушить звук", undeafen: "Включить звук",
        user_settings: "Настройки пользователя", about_me: "Моя учетная запись", voice_channel: "Голос и видео",
        input_mode: "РЕЖИМ ВВОДА", record_keybind: "Задать кнопку", pasted_from_clipboard: "Вставлено из буфера обмена",
        send_message: "Написать сообщение...", save: "Сохранить", in_call: "В звонке",
        create_server: "Создать сервер", join_server: "Присоединиться к серверу", create_channel: "Создать канал",
        server_invite: "Приглашение на сервер"
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

window.addEventListener('pywebviewready', () => {
    initApp();
});

document.addEventListener('DOMContentLoaded', () => {
    if (window.pywebview && window.pywebview.api) {
        initApp();
    }
});

let isInitialized = false;

async function initApp() {
    if (isInitialized) return;
    isInitialized = true;

    bindDomEvents();

    try {
        const initData = await window.pywebview.api.get_initial_state();
        state.config = initData.config || {};
        state.language = initData.language || 'en';
        state.theme = initData.theme || 'dark';
        state.pttMode = initData.ptt_mode || false;
        state.pttKey = initData.ptt_key || 'Space';

        applyTheme(state.theme);
        applyLanguage(state.language);
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

        // Attempt auto-login if enabled
        if (initData.auto_login && initData.saved_username && initData.saved_password) {
            doLogin(initData.saved_username, initData.saved_password, true);
        }
    } catch (e) {
        console.error('Failed to get initial state:', e);
    }
}

// ---------------- DOM Event Bindings ----------------

function bindDomEvents() {
    // Window Titlebar Controls
    document.getElementById('btn-win-min').onclick = () => window.pywebview.api.minimize_window();
    document.getElementById('btn-win-max').onclick = () => window.pywebview.api.toggle_maximize_window();
    document.getElementById('btn-win-close').onclick = () => window.pywebview.api.close_window();

    // Server Rail Home & Navigation
    document.getElementById('btn-rail-home').onclick = () => switchMode('home');
    document.getElementById('btn-rail-add').onclick = () => promptCreateRoom();
    document.getElementById('btn-rail-join').onclick = () => promptJoinInvite();

    // Channel Header Buttons
    document.getElementById('btn-create-channel').onclick = () => promptCreateChannel();
    document.getElementById('btn-server-invite').onclick = () => promptServerInvite();

    // Friends Tab Filter Buttons
    document.getElementById('btn-tab-friends').onclick = () => switchMode('home');
    document.querySelectorAll('.friends-tab').forEach(tab => {
        tab.onclick = () => {
            document.querySelectorAll('.friends-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
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

    // Toggle Member List
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

    // Clipboard Paste Listener (Ctrl + V for images and files)
    document.addEventListener('paste', handlePasteEvent);

    // Voice / Call Disconnect
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
            document.getElementById(`settings-tab-${item.dataset.tab}`).classList.remove('hidden');
        };
    });

    document.getElementById('btn-record-keybind').onclick = startRecordKeybind;
    document.getElementById('radio-vad').onchange = () => updateInputMode(false);
    document.getElementById('radio-ptt').onchange = () => updateInputMode(true);

    document.getElementById('btn-save-profile').onclick = saveProfileSettings;
    document.getElementById('btn-save-password').onclick = savePasswordChange;

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

    // Incoming Call Modal
    document.getElementById('btn-accept-call').onclick = acceptIncomingCall;
    document.getElementById('btn-decline-call').onclick = declineIncomingCall;

    // Lightbox Close
    document.getElementById('btn-close-lightbox').onclick = () => {
        document.getElementById('lightbox-modal').classList.add('hidden');
    };
}

// ---------------- Clipboard Paste Handler (Ctrl + V) ----------------

async function handlePasteEvent(e) {
    const items = (e.clipboardData || window.clipboardData)?.items;
    let handled = false;

    if (items && items.length > 0) {
        for (let i = 0; i < items.length; i++) {
            const item = items[i];

            // 1. Image pasted (Snipping Tool, browser screenshot, Paint, etc.)
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
            }
            // 2. File pasted (copied from File Explorer)
            else if (item.kind === 'file') {
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

    // Fallback: If clipboardData items didn't contain image/file, check OS clipboard via Python API
    if (!handled && window.pywebview?.api?.get_clipboard_image) {
        try {
            const clipImg = await window.pywebview.api.get_clipboard_image();
            if (clipImg && clipImg.data) {
                setAttachment(clipImg);
                showToast(t('pasted_from_clipboard', 'Attached image from clipboard'));
                e.preventDefault();
            }
        } catch (err) {
            // Ignore normal text paste
        }
    }
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
            onCallRinging(payload);
            break;
        case 'call_accepted':
            onCallAccepted(payload);
            break;
        case 'call_declined':
        case 'call_ended':
        case 'call_failed':
            onCallTerminated(eventName, payload);
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
    }
};

// ---------------- Auth Logic ----------------

function switchAuthTab(tab) {
    currentAuthTab = tab;
    document.getElementById('tab-btn-login').classList.toggle('active', tab === 'login');
    document.getElementById('tab-btn-register').classList.toggle('active', tab === 'register');
    document.getElementById('btn-auth-submit').textContent = (tab === 'login') ? 'Log In' : 'Register';
    document.getElementById('row-auto-login').style.display = (tab === 'login') ? 'block' : 'none';
    const err = document.getElementById('auth-error');
    if (err) err.classList.add('hidden');
}

function handleAuthSubmit(e) {
    e.preventDefault();
    const u = document.getElementById('auth-username').value.trim();
    const p = document.getElementById('auth-password').value;
    const autologin = document.getElementById('auth-autologin').checked;

    const btn = document.getElementById('btn-auth-submit');
    btn.disabled = true;
    btn.textContent = 'Connecting...';

    const err = document.getElementById('auth-error');
    if (err) err.classList.add('hidden');

    if (currentAuthTab === 'login') {
        window.pywebview.api.login(u, p, '', 0, 0, autologin);
    } else {
        window.pywebview.api.register(u, p, '', 0, 0);
    }
}

function doLogin(u, p, autologin) {
    const btn = document.getElementById('btn-auth-submit');
    if (btn) {
        btn.disabled = true;
        btn.textContent = 'Connecting...';
    }
    const err = document.getElementById('auth-error');
    if (err) err.classList.add('hidden');

    window.pywebview.api.login(u, p, '', 0, 0, autologin);
}

function onLoginResponse(res) {
    const btn = document.getElementById('btn-auth-submit');
    if (btn) {
        btn.disabled = false;
        btn.textContent = (currentAuthTab === 'login') ? 'Log In' : 'Register';
    }

    if (!res.success) {
        const err = document.getElementById('auth-error');
        err.textContent = res.data?.message || 'Login failed.';
        err.classList.remove('hidden');
        return;
    }

    // Success: Transition from dedicated auth screen to main workspace
    document.getElementById('auth-container').classList.add('hidden');
    document.getElementById('app-container').classList.remove('hidden');
    window.pywebview.api.set_window_size(1280, 800);

    state.user = res.data;
    state.rooms = {};
    (res.data.rooms || []).forEach(r => state.rooms[r.room_id] = r);
    state.users = {};
    (res.data.users || []).forEach(u => state.users[u.user_id] = u);
    state.friends = res.data.friends || [];

    updateUserPanelProfile();
    renderServerRail();
    renderSidebar();
    renderFriendsTab('online');
    showToast(`Welcome back, ${state.user.display_name || state.user.username}!`);
}

function onRegisterResponse(res) {
    const btn = document.getElementById('btn-auth-submit');
    if (btn) {
        btn.disabled = false;
        btn.textContent = 'Register';
    }

    if (!res.success) {
        const err = document.getElementById('auth-error');
        err.textContent = res.message || 'Registration failed.';
        err.classList.remove('hidden');
    } else {
        showToast('Account created successfully! Logging in...');
        switchAuthTab('login');
        const u = document.getElementById('auth-username').value.trim();
        const p = document.getElementById('auth-password').value;
        doLogin(u, p, false);
    }
}

function doLogout() {
    closeSettings();
    document.getElementById('app-container').classList.add('hidden');
    document.getElementById('auth-container').classList.remove('hidden');
    state.user = null;
    window.pywebview.api.logout();
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

        // Right-click menu for server options (Delete or Leave)
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
        const item = document.createElement('button');
        item.className = 'sidebar-item';
        if (state.currentDmPeerId === f.peer_id) {
            item.classList.add('active');
        }
        item.innerHTML = `
            <div class="avatar-wrap">
                <div class="avatar" style="background-color: ${f.avatar_color || '#5865F2'}">${(f.peer_display_name || f.peer_name).charAt(0).toUpperCase()}</div>
                <div class="status-dot ${f.is_online ? 'status-online' : 'status-offline'}"></div>
            </div>
            <span class="item-name">${f.peer_display_name || f.peer_name}</span>
        `;
        item.onclick = () => selectDmUser(f.peer_id, f.peer_display_name || f.peer_name);
        list.appendChild(item);
    });
}

function renderServerChannels(room) {
    const textList = document.getElementById('text-channel-list');
    const voiceList = document.getElementById('voice-channel-list');
    textList.innerHTML = '';
    voiceList.innerHTML = '';

    (room.channels || []).forEach(ch => {
        const item = document.createElement('div');
        item.style.display = 'flex';
        item.style.alignItems = 'center';
        item.style.position = 'relative';

        const btn = document.createElement('button');
        btn.className = 'sidebar-item';
        btn.style.flex = '1';

        if (ch.type === 'voice') {
            btn.innerHTML = `<span class="item-icon">🔊</span><span class="item-name">${ch.name}</span>`;
            btn.onclick = () => selectVoiceChannel(room.room_id, ch.channel_id, ch.name);
            item.appendChild(btn);
            voiceList.appendChild(item);
        } else {
            btn.innerHTML = `<span class="item-icon">#</span><span class="item-name">${ch.name}</span>`;
            if (state.currentChannelId === ch.channel_id) {
                btn.classList.add('active');
            }
            btn.onclick = () => selectTextChannel(room.room_id, ch.channel_id, ch.name);
            item.appendChild(btn);
            textList.appendChild(item);
        }

        // Delete channel option for server owner
        if (room.owner_id === state.user?.user_id && room.channels.length > 1) {
            const delBtn = document.createElement('button');
            delBtn.style.background = 'transparent';
            delBtn.style.border = 'none';
            delBtn.style.color = 'var(--text-muted)';
            delBtn.style.cursor = 'pointer';
            delBtn.style.padding = '4px 8px';
            delBtn.style.fontSize = '14px';
            delBtn.title = 'Delete Channel';
            delBtn.innerHTML = '&times;';
            delBtn.onclick = (e) => {
                e.stopPropagation();
                if (confirm(`Delete channel #${ch.name}?`)) {
                    window.pywebview.api.delete_channel(room.room_id, ch.channel_id);
                }
            };
            item.appendChild(delBtn);
        }
    });

    // Select first text channel by default if none selected
    if (!state.currentChannelId) {
        const firstText = (room.channels || []).find(c => c.type !== 'voice');
        if (firstText) {
            selectTextChannel(room.room_id, firstText.channel_id, firstText.name);
        }
    }
}

function showFriendsView() {
    state.activeTab = 'friends';
    state.currentChannelId = null;
    state.currentDmPeerId = null;

    document.getElementById('friends-view').classList.remove('hidden');
    document.getElementById('chat-view').classList.add('hidden');
    document.getElementById('voice-stage-view').classList.add('hidden');

    document.getElementById('chat-header-title').textContent = t('friends', 'Friends');
    document.getElementById('chat-header-desc').textContent = '';
    document.getElementById('btn-header-call').classList.add('hidden');
    document.getElementById('btn-toggle-members').classList.add('hidden');
}

function selectTextChannel(roomId, channelId, channelName) {
    state.currentRoomId = roomId;
    state.currentChannelId = channelId;
    state.currentDmPeerId = null;

    document.querySelectorAll('.sidebar-item').forEach(b => b.classList.remove('active'));
    document.getElementById('friends-view').classList.add('hidden');
    document.getElementById('chat-view').classList.remove('hidden');
    document.getElementById('voice-stage-view').classList.add('hidden');

    document.getElementById('chat-header-title').textContent = `# ${channelName}`;
    document.getElementById('chat-header-desc').textContent = `Welcome to #${channelName}!`;
    document.getElementById('chat-text-input').placeholder = `Message #${channelName}`;
    document.getElementById('btn-header-call').classList.add('hidden');
    document.getElementById('btn-toggle-members').classList.remove('hidden');

    document.getElementById('messages-list').innerHTML = '';
    window.pywebview.api.get_history('channel', channelId);
}

function selectDmUser(peerId, peerName) {
    state.currentDmPeerId = peerId;
    state.currentChannelId = null;
    state.currentRoomId = null;

    document.querySelectorAll('.sidebar-item').forEach(b => b.classList.remove('active'));
    document.getElementById('friends-view').classList.add('hidden');
    document.getElementById('chat-view').classList.remove('hidden');
    document.getElementById('voice-stage-view').classList.add('hidden');

    document.getElementById('chat-header-title').textContent = `@ ${peerName}`;
    document.getElementById('chat-header-desc').textContent = `Direct message with ${peerName}`;
    document.getElementById('chat-text-input').placeholder = `Message @${peerName}`;
    document.getElementById('btn-header-call').classList.remove('hidden');
    document.getElementById('btn-toggle-members').classList.add('hidden');

    document.getElementById('messages-list').innerHTML = '';
    window.pywebview.api.get_history('dm', peerId);
}

function selectVoiceChannel(roomId, channelId, channelName) {
    document.getElementById('voice-status-bar').classList.remove('hidden');
    document.getElementById('voice-status-channel').textContent = `${channelName} / Voice Connected`;

    document.getElementById('friends-view').classList.add('hidden');
    document.getElementById('chat-view').classList.add('hidden');
    document.getElementById('voice-stage-view').classList.remove('hidden');
    document.getElementById('voice-stage-channel-name').textContent = channelName;

    renderVoiceStage(channelName);
    window.pywebview.api.join_voice(roomId, channelId);
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
            if (val.trim()) {
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
            if (name.trim()) {
                window.pywebview.api.create_channel(state.currentRoomId, name.trim(), channelType || 'text');
            }
        }
    });
}

function promptServerInvite() {
    if (!state.currentRoomId) return;
    window.pywebview.api.create_room_invite(state.currentRoomId);
}

// ---------------- Structure Event Handlers ----------------

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
        showToast(`Channel "#${channel.name}" created.`);
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
    showToast(`Invite code copied to clipboard: ${code}`);
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
    const list = document.getElementById('member-list');
    if (!list) return;
    list.innerHTML = '';
    (members || []).forEach(m => {
        const item = document.createElement('div');
        item.className = 'member-item';
        item.style.display = 'flex';
        item.style.alignItems = 'center';
        item.style.padding = '6px 8px';
        item.style.borderRadius = '4px';
        item.style.cursor = 'pointer';
        item.innerHTML = `
            <div class="avatar-wrap">
                <div class="avatar" style="background-color: ${m.avatar_color || '#5865F2'}">${(m.display_name || m.username).charAt(0).toUpperCase()}</div>
                <div class="status-dot ${m.is_online ? 'status-online' : 'status-offline'}"></div>
            </div>
            <div class="member-info" style="margin-left: 8px;">
                <div class="member-name" style="font-weight: 600; color: var(--text-bright);">${m.display_name || m.username}</div>
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
    const bar = document.getElementById('attachment-preview-bar');
    const nameEl = document.getElementById('attachment-preview-name');
    nameEl.textContent = `${att.name} (${formatBytes(att.size)})`;
    bar.classList.remove('hidden');
}

function clearAttachment() {
    state.currentAttachment = null;
    document.getElementById('attachment-preview-bar').classList.add('hidden');
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

    appendMessage(localMsg);
    input.value = '';
    clearAttachment();

    window.pywebview.api.send_chat_message(
        targetType, targetId, text,
        imgData, '', 0.0,
        fileData, fileName, fileSize
    );
}

function onChatMessageReceived(msg) {
    const currentTarget = state.currentDmPeerId || state.currentChannelId;
    if (msg.target_id === currentTarget || (msg.target_type === 'dm' && msg.sender_id === state.currentDmPeerId)) {
        appendMessage(msg);
    }
}

function onHistoryReceived(data) {
    const list = document.getElementById('messages-list');
    list.innerHTML = '';
    (data.messages || []).forEach(msg => appendMessage(msg));
    list.scrollTop = list.scrollHeight;
}

function appendMessage(msg) {
    const list = document.getElementById('messages-list');
    const existing = document.getElementById(`msg-${msg.msg_id}`);
    if (existing) return;

    const wrap = document.createElement('div');
    wrap.className = 'message-group';
    wrap.id = `msg-${msg.msg_id}`;

    const dateStr = new Date(msg.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const isMine = msg.sender_id === state.user?.user_id;

    let mediaHtml = '';
    if (msg.image_data) {
        mediaHtml += `<div class="message-image"><img src="data:image/png;base64,${msg.image_data}" alt="Image" onclick="openLightbox(this.src)"></div>`;
    }
    if (msg.file_data) {
        mediaHtml += `
            <div class="message-file">
                <div class="file-icon">📄</div>
                <div class="file-info">
                    <div class="file-name">${msg.file_name}</div>
                    <div class="file-size">${formatBytes(msg.file_size)}</div>
                </div>
                <button class="btn-download" onclick="downloadAttachment('${msg.file_name}', '${msg.file_data}')">⬇ Download</button>
            </div>
        `;
    }
    if (msg.voice_data) {
        mediaHtml += `
            <div class="message-voice">
                <button class="btn-voice-play" onclick="playVoiceMsg('${msg.voice_data}', ${msg.voice_duration || 0})">▶ Play (${(msg.voice_duration || 0).toFixed(1)}s)</button>
            </div>
        `;
    }

    const deleteBtn = isMine ? `<button class="btn-delete-msg" onclick="deleteMessage('${msg.msg_id}', '${msg.target_type}', '${msg.target_id}')" title="Delete message">&times;</button>` : '';

    wrap.innerHTML = `
        <div class="avatar-wrap">
            <div class="avatar" style="background-color: #5865F2">${(msg.sender_name || 'U').charAt(0).toUpperCase()}</div>
        </div>
        <div class="message-content-wrap">
            <div class="message-header">
                <span class="message-sender">${msg.sender_name || 'User'}</span>
                <span class="message-timestamp">${dateStr}</span>
                ${deleteBtn}
            </div>
            ${msg.content ? `<div class="message-text">${escapeHtml(msg.content)}</div>` : ''}
            ${mediaHtml}
        </div>
    `;

    list.appendChild(wrap);
    list.scrollTop = list.scrollHeight;
}

function deleteMessage(msgId, targetType, targetId) {
    const el = document.getElementById(`msg-${msgId}`);
    if (el) el.remove();
    window.pywebview.api.delete_message(msgId, targetType, targetId);
}

function onMessageDeleted(data) {
    const el = document.getElementById(`msg-${data.msg_id}`);
    if (el) el.remove();
}

async function downloadAttachment(filename, b64) {
    const res = await window.pywebview.api.save_file_to_disk(filename, b64);
    if (res.success) {
        showToast(`Saved to ${res.path}`);
    } else {
        showToast(`Failed to save: ${res.error}`);
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
        showToast('Recording voice message... Click again to send');
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
        showToast('Voice message was too short.');
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

function onCallRinging(data) {
    showToast('Calling...');
}

function onCallAccepted(data) {
    state.activeCallId = data.call_id;
    document.getElementById('dm-call-widget').classList.remove('hidden');
    document.getElementById('dm-call-status-text').textContent = t('in_call', 'In Call');
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
        showToast(`Call failed: ${payload.reason}`);
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

// ---------------- Voice Stage & Activity ----------------

function renderVoiceStage(chName) {
    const grid = document.getElementById('voice-participants-grid');
    grid.innerHTML = '';

    if (state.user) {
        const card = document.createElement('div');
        card.className = 'voice-card';
        card.id = `voice-card-${state.user.user_id}`;
        card.innerHTML = `
            <div class="voice-card-avatar" style="background-color: ${state.user.avatar_color || '#5865F2'}">${(state.user.display_name || state.user.username).charAt(0).toUpperCase()}</div>
            <div class="voice-card-name">${state.user.display_name || state.user.username}</div>
        `;
        grid.appendChild(card);
    }
}

function onLocalSpeaking(data) {
    if (!state.user) return;
    const card = document.getElementById(`voice-card-${state.user.user_id}`);
    if (card) {
        card.classList.toggle('speaking', data.is_speaking);
    }
}

function onPeerSpeaking(data) {
    const card = document.getElementById(`voice-card-${data.user_id}`);
    if (card) {
        card.classList.toggle('speaking', data.is_speaking);
    }
}

// ---------------- Screen Sharing ----------------

function toggleScreenShare() {
    state.isSharingScreen = !state.isSharingScreen;
    const targetType = state.currentDmPeerId ? 'dm' : 'channel';
    const targetId = state.currentDmPeerId || state.currentChannelId;

    if (state.isSharingScreen) {
        window.pywebview.api.start_screen_share(targetType, targetId);
        showToast('Screen sharing started');
    } else {
        window.pywebview.api.stop_screen_share();
        showToast('Screen sharing stopped');
        document.getElementById('screen-share-stream-container').classList.add('hidden');
    }
}

function onScreenFrame(data) {
    const cont = document.getElementById('screen-share-stream-container');
    const img = document.getElementById('screen-share-img');
    if (cont && img) {
        cont.classList.remove('hidden');
        img.src = `data:image/jpeg;base64,${data.frame}`;
    }
}

function onScreenStop(data) {
    document.getElementById('screen-share-stream-container').classList.add('hidden');
    showToast('Screen share ended by peer');
}

// ---------------- Audio Controls (Mute / Deafen) ----------------

function toggleMic() {
    state.isMuted = !state.isMuted;
    const btn = document.getElementById('btn-toggle-mic');
    btn.classList.toggle('active', state.isMuted);
    btn.title = state.isMuted ? t('unmute', 'Unmute') : t('mute', 'Mute');
    window.pywebview.api.set_mic_muted(state.isMuted);
}

function toggleDeafen() {
    state.isDeafened = !state.isDeafened;
    const btn = document.getElementById('btn-toggle-deafen');
    btn.classList.toggle('active', state.isDeafened);
    btn.title = state.isDeafened ? t('undeafen', 'Undeafen') : t('deafen', 'Deafen');
    window.pywebview.api.set_deafened(state.isDeafened);
}

// ---------------- Settings & Preferences ----------------

function openSettings() {
    document.getElementById('modal-settings').classList.remove('hidden');
    if (state.user) {
        document.getElementById('setting-display-name').value = state.user.display_name || '';
        document.getElementById('setting-bio').value = state.user.bio || '';
    }
}

function closeSettings() {
    document.getElementById('modal-settings').classList.add('hidden');
}

function renderPttSettings(isPtt, key) {
    document.getElementById('radio-ptt').checked = isPtt;
    document.getElementById('radio-vad').checked = !isPtt;
    document.getElementById('ptt-key-display').textContent = key || 'Space';
    document.getElementById('ptt-keybind-container').style.display = isPtt ? 'block' : 'none';
}

function updateInputMode(isPtt) {
    state.pttMode = isPtt;
    document.getElementById('ptt-keybind-container').style.display = isPtt ? 'block' : 'none';
    window.pywebview.api.set_ptt_config(isPtt, state.pttKey);
}

function startRecordKeybind() {
    const disp = document.getElementById('ptt-key-display');
    disp.textContent = 'Press any key / mouse button...';
    disp.style.borderColor = 'var(--accent)';
    window.pywebview.api.record_keybind_start();
}

function onKeybindCaptured(data) {
    state.pttKey = data.key;
    const disp = document.getElementById('ptt-key-display');
    disp.textContent = data.key;
    disp.style.borderColor = 'var(--border-color)';
    showToast(`Push-to-Talk key bound to: ${data.key}`);
}

function saveProfileSettings() {
    const disp = document.getElementById('setting-display-name').value.trim();
    const bio = document.getElementById('setting-bio').value.trim();
    window.pywebview.api.update_profile(disp, '', '', '', '', '', bio);
    if (state.user) {
        state.user.display_name = disp;
        state.user.bio = bio;
        updateUserPanelProfile();
    }
    showToast('Profile updated!');
    closeSettings();
}

function savePasswordChange() {
    const oldP = document.getElementById('setting-old-pass').value;
    const newP = document.getElementById('setting-new-pass').value;
    if (!oldP || !newP) return;
    window.pywebview.api.change_password(oldP, newP);
    document.getElementById('setting-old-pass').value = '';
    document.getElementById('setting-new-pass').value = '';
    showToast('Password change requested...');
}

function applyTheme(th) {
    document.body.className = `theme-${th}`;
}

function applyLanguage(lng) {
    state.language = lng;
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
        filtered = state.friends.filter(f => f.is_online && f.friendship_status === 'accepted');
    } else if (tab === 'all') {
        filtered = state.friends.filter(f => f.friendship_status === 'accepted');
    } else if (tab === 'pending') {
        filtered = state.friends.filter(f => f.friendship_status === 'pending');
    }

    document.getElementById('friends-count-label').textContent = `${tab.toUpperCase()} — ${filtered.length}`;

    filtered.forEach(f => {
        const row = document.createElement('div');
        row.className = 'friend-row';

        let actionsHtml = '';
        if (f.friendship_status === 'pending') {
            if (f.is_incoming) {
                actionsHtml = `
                    <button class="circle-btn" title="Accept" onclick="acceptFriend('${f.peer_id}')" style="color: #23a55a;">✓</button>
                    <button class="circle-btn" title="Decline" onclick="declineFriend('${f.peer_id}')" style="color: #f23f43;">✕</button>
                `;
            } else {
                actionsHtml = `<span style="font-size: 12px; color: var(--text-muted); padding: 4px 8px;">Pending Outgoing</span>`;
            }
        } else {
            actionsHtml = `
                <button class="circle-btn" title="Message" onclick="selectDmUser('${f.peer_id}', '${f.peer_display_name || f.peer_name}')">💬</button>
                <button class="circle-btn" title="Call" onclick="startCallUser('${f.peer_id}')">📞</button>
            `;
        }

        row.innerHTML = `
            <div class="friend-info">
                <div class="avatar-wrap">
                    <div class="avatar" style="background-color: ${f.avatar_color || '#5865F2'}">${(f.peer_display_name || f.peer_name).charAt(0).toUpperCase()}</div>
                    <div class="status-dot ${f.is_online ? 'status-online' : 'status-offline'}"></div>
                </div>
                <div class="friend-names">
                    <div class="disp-name">${f.peer_display_name || f.peer_name}</div>
                    <div class="user-handle">@${f.peer_name}</div>
                </div>
            </div>
            <div class="friend-actions">
                ${actionsHtml}
            </div>
        `;
        itemsCont.appendChild(row);
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
    const activeTab = document.querySelector('.friends-tab.active')?.dataset.tab || 'online';
    renderFriendsTab(activeTab);
}

function onFriendRequestResp(res) {
    showToast(res.message);
}

function onUserPresence(user) {
    if (state.users[user.user_id]) {
        Object.assign(state.users[user.user_id], user);
    }
    const fr = state.friends.find(f => f.peer_id === user.user_id);
    if (fr) {
        fr.is_online = user.is_online;
        fr.status = user.status;
    }
    renderDmList();
    const activeTab = document.querySelector('.friends-tab.active')?.dataset.tab || 'online';
    renderFriendsTab(activeTab);
}

function onPong(data) {
    const el = document.getElementById('voice-status-channel');
    if (el && state.currentRoomId) {
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
    return str.replace(/[&<>"']/g, m => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    }[m]));
}
