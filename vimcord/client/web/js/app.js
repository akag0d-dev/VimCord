/**
 * VimCord Client Frontend Application Logic
 * Integrates with pywebview Python API bridge.
 */

// Global App State
const state = {
    apiReady: false,
    config: {},
    language: 'en',
    theme: 'dark',
    user: null,
    rooms: {},
    users: {},
    friends: [],
    currentRoomId: null,
    currentChannelId: null,
    currentDmPeerId: null,
    currentVoiceChannelId: null,
    activeCallId: null,
    callTimerInterval: null,
    callStartTime: null,
    isMuted: false,
    isDeafened: false,
    pttMode: false,
    pttKey: 'Space',
    isRecordingVoice: false,
    voiceTimerInterval: null,
    voiceRecordSeconds: 0,
    currentAttachment: null,
    isTestingMic: false,
    activeTab: 'friends' // 'friends', 'chat', 'voice'
};

// UI Translations Dictionary
const TRANSLATIONS = {
    en: {
        online: "Online", offline: "Offline", friends: "Friends", all: "All", pending: "Pending",
        add_friend: "Add Friend", direct_messages: "DIRECT MESSAGES", text_channels: "TEXT CHANNELS",
        voice_channels: "VOICE CHANNELS", voice_connected: "Voice Connected", mute_mic: "Mute",
        deafen_audio: "Deafen", screen_share: "Screen", disconnect: "Disconnect", about_me: "My Account",
        display_name: "Display Name", banner_color: "Banner Color", record_keybind: "Record Keybind",
        pasted_from_clipboard: "Attached from clipboard", save: "Save", in_call: "In Call"
    },
    ru: {
        online: "В сети", offline: "Не в сети", friends: "Друзья", all: "Все", pending: "Ожидание",
        add_friend: "Добавить в друзья", direct_messages: "ЛИЧНЫЕ СООБЩЕНИЯ", text_channels: "ТЕКСТОВЫЕ КАНАЛЫ",
        voice_channels: "ГОЛОСОВЫЕ КАНАЛЫ", voice_connected: "Голос подключен", mute_mic: "Заглушить",
        deafen_audio: "Заглушить звук", screen_share: "Демонстрация", disconnect: "Отключиться",
        about_me: "О себе", display_name: "Отображаемое имя", banner_color: "Цвет баннера",
        record_keybind: "Задать кнопку", pasted_from_clipboard: "Вставлено из буфера обмена",
        save: "Сохранить", in_call: "В звонке"
    }
};

function t(key, defaultVal = '') {
    const lang = TRANSLATIONS[state.language] || TRANSLATIONS.en;
    return lang[key] || defaultVal || key;
}

// ---------------- Initialization ----------------

window.addEventListener('pywebviewready', () => {
    initApp();
});

// Fallback polling for pywebview API
if (!state.apiReady) {
    const checkInterval = setInterval(() => {
        if (window.pywebview && window.pywebview.api) {
            clearInterval(checkInterval);
            initApp();
        }
    }, 100);
}

async function initApp() {
    if (state.apiReady) return;
    state.apiReady = true;

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

        // Pre-fill login credentials
        if (initData.saved_username) {
            document.getElementById('auth-username').value = initData.saved_username;
        }
        if (initData.saved_password) {
            document.getElementById('auth-password').value = initData.saved_password;
        }
        document.getElementById('auth-autologin').checked = !!initData.auto_login;

        // Attempt auto login
        if (initData.auto_login && initData.saved_username && initData.saved_password) {
            doLogin(initData.saved_username, initData.saved_password, true);
        }
    } catch (e) {
        console.error('Failed to get initial state:', e);
    }
}

// ---------------- DOM Event Bindings ----------------

function bindDomEvents() {
    // Window Titlebar
    document.getElementById('btn-win-min').onclick = () => window.pywebview.api.minimize_window();
    document.getElementById('btn-win-max').onclick = () => window.pywebview.api.toggle_maximize_window();
    document.getElementById('btn-win-close').onclick = () => window.pywebview.api.close_window();

    // Server Rail Home Button
    document.getElementById('btn-rail-home').onclick = () => switchMode('home');
    document.getElementById('btn-rail-add').onclick = () => promptCreateRoom();
    document.getElementById('btn-rail-join').onclick = () => promptJoinInvite();

    // Friends Tab
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

    // Auth Form
    document.getElementById('form-auth').onsubmit = handleAuthSubmit;
    document.getElementById('tab-btn-login').onclick = () => switchAuthTab('login');
    document.getElementById('tab-btn-register').onclick = () => switchAuthTab('register');

    // Incoming Call Modal
    document.getElementById('btn-accept-call').onclick = acceptIncomingCall;
    document.getElementById('btn-decline-call').onclick = declineIncomingCall;

    // Lightbox Close
    document.getElementById('btn-close-lightbox').onclick = () => {
        document.getElementById('lightbox-modal').classList.add('hidden');
    };
}

// ---------------- Clipboard Paste Handler (Ctrl + V) ----------------

function handlePasteEvent(e) {
    const items = (e.clipboardData || window.clipboardData)?.items;
    if (!items || items.length === 0) return;

    for (let i = 0; i < items.length; i++) {
        const item = items[i];

        // 1. Image pasted (Snipping Tool, browser screenshot, Paint, etc.)
        if (item.type.indexOf('image') !== -1) {
            const blob = item.getAsFile();
            if (blob) {
                const reader = new FileReader();
                reader.onload = function(evt) {
                    const base64Data = evt.target.result.split(',')[1];
                    const timestamp = new Date().toISOString().slice(0,19).replace(/[:T]/g, '-');
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
                return;
            }
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
        case 'channel_created':
        case 'channel_renamed':
        case 'channel_deleted':
            onStructureUpdate();
            break;
    }
};

// ---------------- Auth Logic ----------------

let currentAuthTab = 'login';
function switchAuthTab(tab) {
    currentAuthTab = tab;
    document.getElementById('tab-btn-login').classList.toggle('active', tab === 'login');
    document.getElementById('tab-btn-register').classList.toggle('active', tab === 'register');
    document.getElementById('btn-auth-submit').textContent = (tab === 'login') ? 'Log In' : 'Register';
    document.getElementById('row-auto-login').style.display = (tab === 'login') ? 'block' : 'none';
}

function handleAuthSubmit(e) {
    e.preventDefault();
    const host = document.getElementById('auth-host').value.trim();
    const tcp = parseInt(document.getElementById('auth-tcp').value.trim(), 10);
    const udp = parseInt(document.getElementById('auth-udp').value.trim(), 10);
    const u = document.getElementById('auth-username').value.trim();
    const p = document.getElementById('auth-password').value;
    const autologin = document.getElementById('auth-autologin').checked;

    const btn = document.getElementById('btn-auth-submit');
    btn.disabled = true;
    btn.textContent = 'Connecting...';

    if (currentAuthTab === 'login') {
        window.pywebview.api.login(u, p, host, tcp, udp, autologin);
    } else {
        window.pywebview.api.register(u, p, host, tcp, udp);
    }
}

function doLogin(u, p, autologin) {
    const host = document.getElementById('auth-host').value.trim();
    const tcp = parseInt(document.getElementById('auth-tcp').value.trim(), 10);
    const udp = parseInt(document.getElementById('auth-udp').value.trim(), 10);
    window.pywebview.api.login(u, p, host, tcp, udp, autologin);
}

function onLoginResponse(res) {
    const btn = document.getElementById('btn-auth-submit');
    btn.disabled = false;
    btn.textContent = 'Log In';

    if (!res.success) {
        const err = document.getElementById('auth-error');
        err.textContent = res.data?.message || 'Login failed.';
        err.classList.remove('hidden');
        return;
    }

    // Success
    document.getElementById('modal-login').classList.add('hidden');
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
    btn.disabled = false;
    btn.textContent = 'Register';

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
    document.getElementById('modal-login').classList.remove('hidden');
    state.user = null;
    window.pywebview.api.leave_voice();
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

// ---------------- Navigation & Sidebar ----------------

function switchMode(mode, targetId = null) {
    const homeRailBtn = document.getElementById('btn-rail-home');
    document.querySelectorAll('.server-rail-btn').forEach(b => b.classList.remove('active'));

    if (mode === 'home') {
        homeRailBtn.classList.add('active');
        document.getElementById('sidebar-title').textContent = 'Direct Messages';
        document.getElementById('home-sidebar').classList.remove('hidden');
        document.getElementById('server-sidebar').classList.add('hidden');
        document.getElementById('btn-create-channel').classList.add('hidden');
        document.getElementById('btn-server-invite').classList.add('hidden');

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
    }
}

function renderServerRail() {
    const railList = document.getElementById('server-rail-list');
    railList.innerHTML = '';

    Object.values(state.rooms).forEach(room => {
        const btn = document.createElement('button');
        btn.className = 'rail-btn server-rail-btn';
        btn.title = room.name;
        btn.innerHTML = `<span class="rail-icon">${room.name.charAt(0).toUpperCase()}</span><div class="pill-indicator"></div>`;
        btn.onclick = () => {
            document.querySelectorAll('.server-rail-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            switchMode('server', room.room_id);
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

    // DM list with friends/users
    const peers = state.friends.filter(f => f.friendship_status === 'accepted');
    peers.forEach(f => {
        const item = document.createElement('button');
        item.className = 'sidebar-item';
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
        const item = document.createElement('button');
        item.className = 'sidebar-item';
        if (ch.type === 'voice') {
            item.innerHTML = `<span class="item-icon">🔊</span><span class="item-name">${ch.name}</span>`;
            item.onclick = () => selectVoiceChannel(room.room_id, ch.channel_id, ch.name);
            voiceList.appendChild(item);
        } else {
            item.innerHTML = `<span class="item-icon">#</span><span class="item-name">${ch.name}</span>`;
            item.onclick = () => selectTextChannel(room.room_id, ch.channel_id, ch.name);
            textList.appendChild(item);
        }
    });

    // Select first text channel by default
    const firstText = (room.channels || []).find(c => c.type !== 'voice');
    if (firstText) {
        selectTextChannel(room.room_id, firstText.channel_id, firstText.name);
    }
}

// ---------------- Channels & Workspaces ----------------

function showFriendsView() {
    state.activeTab = 'friends';
    state.currentChannelId = null;
    state.currentDmPeerId = null;

    document.getElementById('view-friends').classList.remove('hidden');
    document.getElementById('view-chat').classList.add('hidden');
    document.getElementById('view-voice-stage').classList.add('hidden');

    document.getElementById('channel-header-icon').textContent = '👥';
    document.getElementById('channel-header-title').textContent = 'Friends';
    document.getElementById('channel-header-desc').textContent = '';
    document.getElementById('btn-header-call').classList.add('hidden');
}

function selectTextChannel(roomId, channelId, channelName) {
    state.activeTab = 'chat';
    state.currentRoomId = roomId;
    state.currentChannelId = channelId;
    state.currentDmPeerId = null;

    document.getElementById('view-friends').classList.add('hidden');
    document.getElementById('view-chat').classList.remove('hidden');
    document.getElementById('view-voice-stage').classList.add('hidden');
    document.getElementById('dm-call-widget').classList.add('hidden');

    document.getElementById('channel-header-icon').textContent = '#';
    document.getElementById('channel-header-title').textContent = channelName;
    document.getElementById('channel-header-desc').textContent = 'Welcome to #' + channelName;
    document.getElementById('btn-header-call').classList.add('hidden');

    document.getElementById('chat-messages-list').innerHTML = '';
    window.pywebview.api.get_history('channel', channelId);
}

function selectDmUser(peerId, peerName) {
    state.activeTab = 'chat';
    state.currentChannelId = null;
    state.currentDmPeerId = peerId;

    document.getElementById('view-friends').classList.add('hidden');
    document.getElementById('view-chat').classList.remove('hidden');
    document.getElementById('view-voice-stage').classList.add('hidden');

    document.getElementById('channel-header-icon').textContent = '@';
    document.getElementById('channel-header-title').textContent = peerName;
    document.getElementById('channel-header-desc').textContent = '';
    document.getElementById('btn-header-call').classList.remove('hidden');

    document.getElementById('chat-messages-list').innerHTML = '';
    window.pywebview.api.get_history('dm', peerId);

    // If active direct call with this user, show call widget
    if (state.activeCallId) {
        document.getElementById('dm-call-widget').classList.remove('hidden');
    }
}

function selectVoiceChannel(roomId, channelId, channelName) {
    state.currentVoiceChannelId = channelId;
    window.pywebview.api.join_voice(roomId, channelId);

    document.getElementById('view-friends').classList.add('hidden');
    document.getElementById('view-chat').classList.add('hidden');
    document.getElementById('view-voice-stage').classList.remove('hidden');

    document.getElementById('voice-status-bar').classList.remove('hidden');
    document.getElementById('voice-status-channel').textContent = `${channelName} / RTC`;

    renderVoiceStage(channelName);
}

// ---------------- Chat & Messages ----------------

async function chooseAttachment() {
    const res = await window.pywebview.api.open_file_dialog();
    if (!res) return;
    if (res.error) {
        showToast(res.error);
        return;
    }
    setAttachment(res);
}

function setAttachment(attachObj) {
    state.currentAttachment = attachObj;
    const strip = document.getElementById('attachment-preview-strip');
    const thumbImg = document.getElementById('preview-thumb-img');
    const thumbIcon = document.getElementById('preview-thumb-icon');
    const nameEl = document.getElementById('preview-filename');
    const sizeEl = document.getElementById('preview-filesize');

    nameEl.textContent = attachObj.name;
    sizeEl.textContent = formatBytes(attachObj.size);

    if (attachObj.is_image) {
        thumbImg.src = `data:image/png;base64,${attachObj.data}`;
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
    const attach = state.currentAttachment;

    if (!text && !attach) return;

    const targetType = state.currentChannelId ? 'channel' : 'dm';
    const targetId = state.currentChannelId || state.currentDmPeerId;
    if (!targetId) return;

    let imgData = '';
    let fileData = '';
    let fileName = '';
    let fileSize = 0;

    if (attach) {
        if (attach.is_image) {
            imgData = attach.data;
        } else {
            fileData = attach.data;
            fileName = attach.name;
            fileSize = attach.size;
        }
    }

    input.value = '';
    clearAttachment();

    window.pywebview.api.send_chat_message(
        targetType, targetId, text, imgData, '', 0.0, fileData, fileName, fileSize
    );
}

function onChatMessageReceived(msg) {
    // Only append if message matches current view
    const isCurrentChannel = state.currentChannelId && msg.target_type === 'channel' && msg.target_id === state.currentChannelId;
    const isCurrentDm = state.currentDmPeerId && msg.target_type === 'dm' && (msg.target_id === state.currentDmPeerId || msg.sender_id === state.currentDmPeerId);

    if (isCurrentChannel || isCurrentDm) {
        appendMessageToDom(msg);
    }
}

function onHistoryReceived(data) {
    const list = document.getElementById('chat-messages-list');
    list.innerHTML = '';
    (data.messages || []).forEach(msg => appendMessageToDom(msg));
}

function appendMessageToDom(msg) {
    const list = document.getElementById('chat-messages-list');
    const group = document.createElement('div');
    group.className = 'message-group';
    group.id = `msg-${msg.msg_id}`;

    const disp = msg.display_name || msg.sender_name || 'User';
    const dateStr = new Date((msg.timestamp || Date.now() / 1000) * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    let avatarHtml = `<div class="msg-avatar" style="background-color: ${msg.avatar_color || '#5865F2'}">${disp.charAt(0).toUpperCase()}</div>`;
    if (msg.avatar_image) {
        avatarHtml = `<div class="msg-avatar" style="background-image: url(data:image/png;base64,${msg.avatar_image});"></div>`;
    }

    let attachmentHtml = '';
    if (msg.image_data) {
        attachmentHtml = `<img class="msg-img-preview" src="data:image/png;base64,${msg.image_data}" onclick="openLightbox(this.src)">`;
    } else if (msg.file_data) {
        attachmentHtml = `
            <div class="msg-file-card">
                <div class="file-card-icon">📄</div>
                <div class="file-card-details">
                    <div class="file-name">${escapeHtml(msg.file_name || 'file')}</div>
                    <div class="file-size">${formatBytes(msg.file_size || 0)}</div>
                </div>
                <button class="file-download-btn" onclick="saveFile('${escapeHtml(msg.file_name)}', '${msg.file_data}')">⬇️ ${t('save', 'Save')}</button>
            </div>
        `;
    } else if (msg.voice_data) {
        attachmentHtml = `
            <div class="msg-voice-card">
                <button class="voice-play-btn" onclick="playVoiceMsg('${msg.voice_data}', ${msg.voice_duration || 0})">▶</button>
                <span class="voice-wave">〰️〰️〰️〰️</span>
                <span class="voice-dur">${(msg.voice_duration || 0).toFixed(1)}s</span>
            </div>
        `;
    }

    const isOwn = state.user && (msg.sender_id === state.user.user_id);
    const deleteBtnHtml = isOwn ? `<button class="msg-delete-btn" onclick="deleteMsg('${msg.msg_id}', '${msg.target_type}', '${msg.target_id}')">🗑️</button>` : '';

    group.innerHTML = `
        ${avatarHtml}
        <div class="msg-content-wrap">
            <div class="msg-header">
                <span class="msg-author">${escapeHtml(disp)}</span>
                <span class="msg-timestamp">${dateStr}</span>
                ${deleteBtnHtml}
            </div>
            ${msg.content ? `<div class="msg-text">${escapeHtml(msg.content)}</div>` : ''}
            ${attachmentHtml}
        </div>
    `;

    list.appendChild(group);
    list.scrollTop = list.scrollHeight;
}

function deleteMsg(msgId, targetType, targetId) {
    window.pywebview.api.delete_message(msgId, targetType, targetId);
}

function onMessageDeleted(data) {
    const el = document.getElementById(`msg-${data.msg_id}`);
    if (el) el.remove();
}

async function saveFile(filename, b64) {
    const res = await window.pywebview.api.save_file_to_disk(filename, b64);
    if (res.success) {
        showToast(`Downloaded to: ${res.path}`);
    } else {
        showToast(`Save error: ${res.error}`);
    }
}

function playVoiceMsg(b64, dur) {
    window.pywebview.api.play_voice_message(b64, dur);
}

// ---------------- Voice Recording ----------------

async function toggleVoiceRecording() {
    const btn = document.getElementById('btn-voice-msg');
    if (!state.isRecordingVoice) {
        state.isRecordingVoice = true;
        state.voiceRecordSeconds = 0;
        btn.classList.add('recording');
        btn.textContent = '⏹️ 0:00';
        window.pywebview.api.start_voice_record();

        state.voiceTimerInterval = setInterval(() => {
            state.voiceRecordSeconds++;
            const m = Math.floor(state.voiceRecordSeconds / 60);
            const s = state.voiceRecordSeconds % 60;
            btn.textContent = `⏹️ ${m}:${s < 10 ? '0' : ''}${s}`;
        }, 1000);
    } else {
        clearInterval(state.voiceTimerInterval);
        state.isRecordingVoice = false;
        btn.classList.remove('recording');
        btn.textContent = '🎙️';

        const res = await window.pywebview.api.stop_voice_record();
        if (res.data && res.duration > 0.3) {
            const targetType = state.currentChannelId ? 'channel' : 'dm';
            const targetId = state.currentChannelId || state.currentDmPeerId;
            if (targetId) {
                window.pywebview.api.send_chat_message(targetType, targetId, '', '', res.data, res.duration, '', '', 0);
            }
        }
    }
}

// ---------------- 1-on-1 Direct Calls ----------------

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
    state.activeCallId = data.call_id;
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

    // Add local user
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

function onPeerSpeaking(data) {
    const card = document.getElementById(`voice-card-${data.user_id}`);
    if (card) {
        card.classList.toggle('speaking', data.is_speaking);
    }
    // Also update in DM call widget if active
    const dmCard = document.getElementById('call-card-peer');
    if (dmCard) {
        dmCard.classList.toggle('speaking', data.is_speaking);
    }
}

function onLocalSpeaking(data) {
    if (state.user) {
        const card = document.getElementById(`voice-card-${state.user.user_id}`);
        if (card) card.classList.toggle('speaking', data.is_speaking);
        const dmCard = document.getElementById('call-card-my');
        if (dmCard) dmCard.classList.toggle('speaking', data.is_speaking);
    }
}

// ---------------- Screen Share ----------------

let isScreenSharing = false;
function toggleScreenShare() {
    isScreenSharing = !isScreenSharing;
    if (isScreenSharing) {
        const targetType = state.currentVoiceChannelId ? 'channel' : 'dm';
        const targetId = state.currentVoiceChannelId || state.activeCallId || state.currentDmPeerId;
        window.pywebview.api.start_screen_share(targetType, targetId);
        showToast('Screen sharing started');
    } else {
        window.pywebview.api.stop_screen_share();
        document.getElementById('voice-screen-stream-box').classList.add('hidden');
        document.getElementById('dm-call-screen-container').classList.add('hidden');
        showToast('Screen sharing stopped');
    }
}

function onScreenFrame(data) {
    const src = `data:image/jpeg;base64,${data.frame}`;
    if (state.activeCallId) {
        const box = document.getElementById('dm-call-screen-container');
        box.classList.remove('hidden');
        document.getElementById('dm-call-screen-img').src = src;
    } else {
        const box = document.getElementById('voice-screen-stream-box');
        box.classList.remove('hidden');
        document.getElementById('voice-stage-screen-img').src = src;
    }
}

function onScreenStop(data) {
    document.getElementById('voice-screen-stream-box').classList.add('hidden');
    document.getElementById('dm-call-screen-container').classList.add('hidden');
}

// ---------------- Mic & Deafen Toggles ----------------

function toggleMic() {
    state.isMuted = !state.isMuted;
    window.pywebview.api.set_mic_muted(state.isMuted);

    const btn1 = document.getElementById('btn-toggle-mic');
    btn1.classList.toggle('active-red', state.isMuted);
    btn1.textContent = state.isMuted ? '🔇' : '🎙️';

    const btn2 = document.getElementById('btn-stage-mute');
    if (btn2) btn2.textContent = state.isMuted ? '🔇 Unmute' : '🎙️ Mute';
}

function toggleDeafen() {
    state.isDeafened = !state.isDeafened;
    window.pywebview.api.set_deafened(state.isDeafened);

    const btn1 = document.getElementById('btn-toggle-deafen');
    btn1.classList.toggle('active-red', state.isDeafened);
    btn1.textContent = state.isDeafened ? '🔕' : '🎧';

    const btn2 = document.getElementById('btn-stage-deafen');
    if (btn2) btn2.textContent = state.isDeafened ? '🔕 Undeafen' : '🎧 Deafen';
}

// ---------------- Settings & PTT ----------------

function openSettings() {
    document.getElementById('modal-settings').classList.remove('hidden');
    if (state.user) {
        document.getElementById('settings-display-name').value = state.user.display_name || '';
        document.getElementById('settings-bio').value = state.user.bio || '';
        document.getElementById('settings-disp-preview').textContent = state.user.display_name || state.user.username;
        document.getElementById('settings-user-preview').textContent = `@${state.user.username}`;
    }
}

function closeSettings() {
    document.getElementById('modal-settings').classList.add('hidden');
}

function renderPttSettings(enabled, key) {
    document.getElementById('radio-ptt').checked = enabled;
    document.getElementById('radio-vad').checked = !enabled;
    document.getElementById('ptt-key-display').textContent = key || 'Space';
}

function updateInputMode(isPtt) {
    state.pttMode = isPtt;
    window.pywebview.api.set_ptt_config(isPtt, state.pttKey);
}

function startRecordKeybind() {
    const badge = document.getElementById('ptt-key-display');
    badge.textContent = 'Press any key / mouse...';
    badge.classList.add('pulsing');
    window.pywebview.api.record_keybind_start();
}

function onKeybindCaptured(data) {
    state.pttKey = data.key;
    state.pttMode = true;
    const badge = document.getElementById('ptt-key-display');
    badge.textContent = data.key;
    badge.classList.remove('pulsing');
    document.getElementById('radio-ptt').checked = true;
    showToast(`Keybind saved: ${data.key}`);
}

function saveProfileSettings() {
    const disp = document.getElementById('settings-display-name').value.trim();
    const bio = document.getElementById('settings-bio').value.trim();
    window.pywebview.api.update_profile(disp, '', '', '', '', '', bio);
    if (state.user) {
        state.user.display_name = disp;
        state.user.bio = bio;
        updateUserPanelProfile();
    }
    showToast('Profile updated!');
}

function savePasswordChange() {
    const oldP = document.getElementById('input-old-pass').value;
    const newP = document.getElementById('input-new-pass').value;
    if (!oldP || !newP) return;
    window.pywebview.api.change_password(oldP, newP);
    document.getElementById('input-old-pass').value = '';
    document.getElementById('input-new-pass').value = '';
    showToast('Password update sent.');
}

function applyTheme(theme) {
    document.body.className = `theme-${theme}`;
}

function applyLanguage(lang) {
    state.language = lang;
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const k = el.dataset.i18n;
        el.textContent = t(k, el.textContent);
    });
}

function populateAudioDevices(devs) {
    const inSel = document.getElementById('select-audio-input');
    const outSel = document.getElementById('select-audio-output');
    inSel.innerHTML = '';
    outSel.innerHTML = '';

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
                <button class="circle-btn" title="Message" onclick="selectDmUser('${f.peer_id}', '${f.peer_display_name || f.peer_name}')">💬</button>
                <button class="circle-btn" title="Call" onclick="startCallUser('${f.peer_id}')">📞</button>
            </div>
        `;
        itemsCont.appendChild(row);
    });
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
    setTimeout(() => toast.remove(), 3500);
}

function formatBytes(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;')
              .replace(/</g, '&lt;')
              .replace(/>/g, '&gt;')
              .replace(/"/g, '&quot;')
              .replace(/'/g, '&#039;');
}
