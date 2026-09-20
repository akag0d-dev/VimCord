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
        voice_channels: "VOICE CHANNELS", voice_connected: "Voice Connected", rtc_connecting: "RTC Connecting...", mute_mic: "Mute",
        unmute_mic: "Unmute", deafen_audio: "Deafen", undeafen_audio: "Undeafen", user_settings: "User Settings",
        about_me: "My Account", voice_channel: "Voice & Video", appearance: "Appearance",
        record_keybind: "Record Keybind", send_message: "Send a message...",
        pasted_from_clipboard: "Attached from clipboard", disconnect: "Disconnect", screen_share: "Screen Share",
        online: "Online", all: "All", pending: "Pending", add_friend: "Add Friend", display_name: "DISPLAY NAME",
        banner_color: "BANNER COLOR", copy_server_id: "Copy Server ID", delete_server: "Delete Server",
        leave_server: "Leave Server", channel_type: "CHANNEL TYPE", text_channel: "Text Channel",
        cancel: "Cancel", confirm: "Confirm", are_you_sure: "Are you sure?",
        confirm_action_desc: "Do you really want to perform this action? This cannot be undone.",
        change_password: "CHANGE PASSWORD", current_password: "Current Password",
        new_password: "New Password (min 4 characters)", update_password: "Update Password",
        ctx_copy_text: "Copy Text", ctx_open_image: "Open Original", ctx_copy_image: "Copy Image",
        ctx_save_image: "Save Image", ctx_copy_id: "Copy ID", ctx_delete_msg: "Delete Message",
        create_server_title: "Create a Server", create_server_desc: "Enter a name for your new server:",
        create_server_placeholder: "e.g. My Gaming Server", create_server_btn: "Create Server",
        join_server_title: "Join a Server", join_server_desc: "Enter an invite link or code:",
        join_server_placeholder: "e.g. vc-abc12345", join_server_btn: "Join Server",
        create_channel_title: "Create Channel", create_channel_desc: "Enter channel name and select type:",
        create_channel_btn: "Create Channel", server_id_copied: "Server ID copied to clipboard!",
        server_created: "Server created!", server_deleted: "Server deleted.",
        joined_server: "Joined server!", left_server: "Left server.",
        text_copied: "Text copied to clipboard", image_copied: "Image copied to clipboard",
        copy_failed: "Failed to copy image", id_copied: "Message ID copied"
    },
    ru: {
        friends: "Друзья", direct_messages: "ЛИЧНЫЕ СООБЩЕНИЯ", text_channels: "ТЕКСТОВЫЕ КАНАЛЫ",
        voice_channels: "ГОЛОСОВЫЕ КАНАЛЫ", voice_connected: "Голос подключен", rtc_connecting: "Подключение к RTC...", mute_mic: "Заглушить",
        unmute_mic: "Включить", deafen_audio: "Заглушить звук", undeafen_audio: "Включить звук",
        user_settings: "Настройки пользователя", about_me: "Моя учетная запись", voice_channel: "Голос и видео",
        appearance: "Внешний вид", record_keybind: "Задать кнопку", send_message: "Написать сообщение...",
        pasted_from_clipboard: "Вставлено из буфера обмена", disconnect: "Отключиться", screen_share: "Демонстрация",
        online: "В сети", all: "Все", pending: "Ожидание", add_friend: "Добавить в друзья", display_name: "ОТОБРАЖАЕМОЕ ИМЯ",
        banner_color: "ЦВЕТ БАННЕРА", copy_server_id: "Копировать ID сервера", delete_server: "Удалить сервер",
        leave_server: "Покинуть сервер", channel_type: "ТИП КАНАЛА", text_channel: "Текстовый канал",
        cancel: "Отмена", confirm: "Подтвердить", are_you_sure: "Вы уверены?",
        confirm_action_desc: "Вы действительно хотите выполнить это действие? Его нельзя отменить.",
        change_password: "СМЕНИТЬ ПАРОЛЬ", current_password: "Текущий пароль",
        new_password: "Новый пароль (мин. 4 символа)", update_password: "Обновить пароль",
        ctx_copy_text: "Копировать текст", ctx_open_image: "Открыть оригинал", ctx_copy_image: "Копировать изображение",
        ctx_save_image: "Сохранить изображение", ctx_copy_id: "Копировать ID", ctx_delete_msg: "Удалить сообщение",
        create_server_title: "Создать сервер", create_server_desc: "Введите название нового сервера:",
        create_server_placeholder: "например, Мой сервер", create_server_btn: "Создать сервер",
        join_server_title: "Присоединиться к серверу", join_server_desc: "Введите код приглашения или ссылку:",
        join_server_placeholder: "например, vc-abc12345", join_server_btn: "Присоединиться",
        create_channel_title: "Создать канал", create_channel_desc: "Введите название и тип канала:",
        create_channel_btn: "Создать канал", server_id_copied: "ID сервера скопирован в буфер!",
        server_created: "Сервер создан!", server_deleted: "Сервер удален.",
        joined_server: "Вы присоединились к серверу!", left_server: "Вы покинули сервер.",
        text_copied: "Текст скопирован в буфер", image_copied: "Изображение скопировано в буфер",
        copy_failed: "Не удалось скопировать изображение", id_copied: "ID сообщения скопирован"
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
        if (initData.noise_suppression !== undefined) {
            document.getElementById('settings-noise-suppression').checked = initData.noise_suppression;
        }

        document.getElementById('cb-dnd-mode').checked = state.dndMode;

        renderPttSettings(state.pttMode, state.pttKey);
        populateAudioDevices(initData.audio_devices || {}, initData.input_device, initData.output_device);

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

    const sendBtn = document.getElementById('btn-send-message');
    if (sendBtn) {
        sendBtn.onclick = () => sendMessage();
    }

    document.getElementById('btn-attach-file').onclick = chooseAttachment;
    document.getElementById('btn-clear-attachment').onclick = clearAttachment;
    document.getElementById('btn-voice-msg').onclick = toggleVoiceRecording;

    // Custom Context Menu Setup
    setupCustomContextMenu();

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
    document.getElementById('btn-toggle-deafen').onclick = toggleDeafen;
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

    const nsCb = document.getElementById('settings-noise-suppression');
    if (nsCb) {
        nsCb.onchange = (e) => {
            window.pywebview.api.set_noise_suppression(e.target.checked);
        };
    }

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
    document.querySelectorAll('.theme-picker-card').forEach(card => {
        card.onclick = () => {
            const th = card.dataset.theme;
            applyTheme(th);
            window.pywebview.api.set_theme(th);
        };
    });

    document.querySelectorAll('.lang-picker-card').forEach(card => {
        card.onclick = () => {
            const lng = card.dataset.lang;
            applyLanguage(lng);
            window.pywebview.api.set_language(lng);
        };
    });

    document.getElementById('cb-dnd-mode').onchange = (e) => {
        state.dndMode = e.target.checked;
        window.pywebview.api.set_dnd_mode(state.dndMode);
    };

    // Reconnection Overlay Retry Button
    const btnReconn = document.getElementById('btn-reconnect-now');
    if (btnReconn) btnReconn.onclick = triggerReconnect;

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

    // User Profile Modal
    const btnCloseProfile = document.getElementById('btn-close-user-profile');
    if (btnCloseProfile) btnCloseProfile.onclick = closeUserProfileModal;

    // Server Options Dropdown Menu
    const btnServerHeader = document.getElementById('btn-server-header');
    const popupServerOpts = document.getElementById('server-options-popup');
    const arrowServer = document.getElementById('sidebar-server-arrow');

    if (btnServerHeader && popupServerOpts) {
        btnServerHeader.onclick = (e) => {
            if (state.activeTab !== 'server' || !state.currentRoomId) return;
            e.stopPropagation();
            const isHidden = popupServerOpts.classList.contains('hidden');
            if (isHidden) {
                const room = state.rooms[state.currentRoomId];
                const isDefault = state.currentRoomId === 'room-default';
                const isOwner = room && room.owner_id === state.user?.user_id;
                document.getElementById('menu-opt-delete-server').classList.toggle('hidden', isDefault || !isOwner);
                document.getElementById('menu-opt-leave-server').classList.toggle('hidden', isDefault);

                popupServerOpts.classList.remove('hidden');
                if (arrowServer) arrowServer.classList.add('open');
            } else {
                popupServerOpts.classList.add('hidden');
                if (arrowServer) arrowServer.classList.remove('open');
            }
        };

        document.addEventListener('click', (e) => {
            if (popupServerOpts && !popupServerOpts.contains(e.target) && !btnServerHeader.contains(e.target)) {
                popupServerOpts.classList.add('hidden');
                if (arrowServer) arrowServer.classList.remove('open');
            }
        });

        const optCopyId = document.getElementById('menu-opt-copy-server-id');
        if (optCopyId) {
            optCopyId.onclick = () => {
                popupServerOpts.classList.add('hidden');
                if (arrowServer) arrowServer.classList.remove('open');
                if (state.currentRoomId) {
                    navigator.clipboard.writeText(state.currentRoomId);
                    showToast(t('server_id_copied', 'Server ID copied to clipboard!'));
                }
            };
        }
        const optCreateCh = document.getElementById('menu-opt-create-channel');
        if (optCreateCh) {
            optCreateCh.onclick = () => {
                popupServerOpts.classList.add('hidden');
                if (arrowServer) arrowServer.classList.remove('open');
                promptCreateChannel();
            };
        }
        const optInvite = document.getElementById('menu-opt-invite');
        if (optInvite) {
            optInvite.onclick = () => {
                popupServerOpts.classList.add('hidden');
                if (arrowServer) arrowServer.classList.remove('open');
                promptServerInvite();
            };
        }

        document.getElementById('menu-opt-delete-server').onclick = () => {
            popupServerOpts.classList.add('hidden');
            if (arrowServer) arrowServer.classList.remove('open');
            const room = state.rooms[state.currentRoomId];
            if (!room) return;
            showConfirmModal({
                title: 'Delete Server',
                message: `Are you sure you want to delete server "${room.name}"? This action cannot be undone.`,
                confirmText: 'Delete Server',
                isDanger: true,
                onConfirm: () => {
                    window.pywebview.api.delete_room(room.room_id);
                }
            });
        };

        document.getElementById('menu-opt-leave-server').onclick = () => {
            popupServerOpts.classList.add('hidden');
            if (arrowServer) arrowServer.classList.remove('open');
            const room = state.rooms[state.currentRoomId];
            if (!room) return;
            showConfirmModal({
                title: 'Leave Server',
                message: `Are you sure you want to leave server "${room.name}"? You will need an invite to rejoin.`,
                confirmText: 'Leave Server',
                isDanger: true,
                onConfirm: () => {
                    window.pywebview.api.leave_room(room.room_id);
                }
            });
        };
    }

    // Global ESC key listener to dismiss any open modals
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            const confirmModal = document.getElementById('modal-confirm');
            if (confirmModal && !confirmModal.classList.contains('hidden')) {
                confirmModal.classList.add('hidden');
                return;
            }
            const profileModal = document.getElementById('modal-user-profile');
            if (profileModal && !profileModal.classList.contains('hidden')) {
                closeUserProfileModal();
                return;
            }
            const promptModal = document.getElementById('modal-prompt');
            if (promptModal && !promptModal.classList.contains('hidden')) {
                closePromptModal();
                return;
            }
            const settingsModal = document.getElementById('modal-settings');
            if (settingsModal && !settingsModal.classList.contains('hidden')) {
                closeSettings();
                return;
            }
            const lightboxModal = document.getElementById('lightbox-modal');
            if (lightboxModal && !lightboxModal.classList.contains('hidden')) {
                lightboxModal.classList.add('hidden');
                return;
            }
        }
    });
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
        case 'connected':
            onConnected();
            break;
        case 'disconnected':
            onDisconnected();
            break;
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
        case 'voice_channel_sync':
            onVoiceChannelSync(payload);
            break;
        case 'user_media_state':
            onUserMediaState(payload);
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
        case 'local_screen_frame':
            onLocalScreenFrame(payload);
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

let reconnectCountdownInterval = null;
let reconnectSecondsLeft = 5;

function showReconnectOverlay() {
    if (!state.user) return; // Only show if user was previously connected/authenticated
    const overlay = document.getElementById('connection-overlay');
    if (!overlay) return;

    overlay.classList.remove('hidden');
    reconnectSecondsLeft = 5;
    const txt = document.getElementById('conn-overlay-text');
    if (txt) {
        txt.textContent = state.language === 'ru' 
            ? `Повторное подключение через ${reconnectSecondsLeft}с...`
            : `Reconnecting in ${reconnectSecondsLeft}s...`;
    }
    const title = document.getElementById('conn-overlay-title');
    if (title) {
        title.textContent = state.language === 'ru' ? 'Подключение потеряно' : 'Connection Lost';
    }
    const retryBtn = document.getElementById('btn-reconnect-now');
    if (retryBtn) {
        retryBtn.textContent = state.language === 'ru' ? 'Подключиться сейчас' : 'Reconnect Now';
    }

    if (reconnectCountdownInterval) {
        clearInterval(reconnectCountdownInterval);
    }

    reconnectCountdownInterval = setInterval(() => {
        reconnectSecondsLeft -= 1;
        if (reconnectSecondsLeft <= 0) {
            clearInterval(reconnectCountdownInterval);
            reconnectCountdownInterval = null;
            if (txt) {
                txt.textContent = state.language === 'ru' ? 'Подключение...' : 'Connecting...';
            }
            triggerReconnect();
        } else {
            if (txt) {
                txt.textContent = state.language === 'ru' 
                    ? `Повторное подключение через ${reconnectSecondsLeft}с...`
                    : `Reconnecting in ${reconnectSecondsLeft}s...`;
            }
        }
    }, 1000);
}

function hideReconnectOverlay() {
    if (reconnectCountdownInterval) {
        clearInterval(reconnectCountdownInterval);
        reconnectCountdownInterval = null;
    }
    const overlay = document.getElementById('connection-overlay');
    if (overlay) overlay.classList.add('hidden');
}

function triggerReconnect() {
    if (reconnectCountdownInterval) {
        clearInterval(reconnectCountdownInterval);
        reconnectCountdownInterval = null;
    }
    const txt = document.getElementById('conn-overlay-text');
    if (txt) {
        txt.textContent = state.language === 'ru' ? 'Подключение...' : 'Connecting...';
    }
    window.pywebview.api.reconnect();
}

function onDisconnected() {
    showReconnectOverlay();
}

function onConnected() {
    hideReconnectOverlay();
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

    hideReconnectOverlay();

    if (state.lastLoginSuccessTime && (Date.now() - state.lastLoginSuccessTime < 4000)) {
        return;
    }
    state.lastLoginSuccessTime = Date.now();

    // Success: Transition to main workspace
    document.getElementById('auth-container').classList.add('hidden');
    document.getElementById('app-container').classList.remove('hidden');

    state.user = res.data;
    state.rooms = {};
    state.voiceUsers = {};
    state.users = {};
    (res.data.users || []).forEach(u => state.users[u.user_id] = u);
    (res.data.rooms || []).forEach(r => {
        state.rooms[r.room_id] = r;
        (r.channels || []).forEach(ch => {
            if (ch.voice_users && Array.isArray(ch.voice_users)) {
                state.voiceUsers[ch.channel_id] = ch.voice_users.map(uid => {
                    const u = state.users[uid] || { user_id: uid, username: uid, display_name: uid };
                    return {
                        user_id: uid,
                        username: u.username || uid,
                        display_name: u.display_name || u.username || uid,
                        avatar_color: u.avatar_color || '#5865F2',
                        avatar_image: u.avatar_image || '',
                        is_muted: false,
                        is_deafened: false,
                        is_speaking: false
                    };
                });
            }
        });
    });
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
    showConfirmModal({
        title: 'Log Out',
        message: 'Are you sure you want to log out of your account?',
        confirmText: 'Log Out',
        isDanger: true,
        onConfirm: () => {
            closeSettings();
            document.getElementById('app-container').classList.add('hidden');
            document.getElementById('auth-container').classList.remove('hidden');
            state.user = null;
            window.pywebview.api.logout();
        }
    });
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
    const arrowEl = document.getElementById('sidebar-server-arrow');
    const popupEl = document.getElementById('server-options-popup');
    if (popupEl) popupEl.classList.add('hidden');
    if (arrowEl) arrowEl.classList.remove('open');

    if (mode === 'home') {
        homeRailBtn.classList.add('active');
        document.querySelectorAll('.server-rail-btn').forEach(b => b.classList.remove('active'));
        document.getElementById('sidebar-title').textContent = t('direct_messages', 'Direct Messages');
        if (arrowEl) arrowEl.classList.add('hidden');
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
        if (arrowEl) arrowEl.classList.remove('hidden');
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
            if (room.room_id === 'room-default') return;
            const isOwner = room.owner_id === state.user?.user_id;
            const action = isOwner ? 'Delete Server' : 'Leave Server';
            showConfirmModal({
                title: action,
                message: isOwner
                    ? `Are you sure you want to delete server "${room.name}"? This action cannot be undone.`
                    : `Are you sure you want to leave server "${room.name}"?`,
                confirmText: action,
                isDanger: true,
                onConfirm: () => {
                    if (isOwner) {
                        window.pywebview.api.delete_room(room.room_id);
                    } else {
                        window.pywebview.api.leave_room(room.room_id);
                    }
                }
            });
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

    const isOwner = (room.owner_id === state.user?.user_id);

    (room.channels || []).forEach(ch => {
        const isVoice = (ch.channel_type === 'voice' || ch.type === 'voice');

        const item = document.createElement('div');
        item.style.display = 'flex';
        item.style.flexDirection = 'column';
        item.style.position = 'relative';

        const row = document.createElement('div');
        row.className = 'channel-item';

        const leftWrap = document.createElement('div');
        leftWrap.className = 'channel-left';

        const btn = document.createElement('button');
        btn.className = 'sidebar-item';
        btn.style.flex = '1';

        if (isVoice) {
            btn.innerHTML = `<span class="material-symbols-outlined item-icon">volume_up</span><span class="item-name">${escapeHtml(ch.name)}</span>`;
            if (state.currentVoiceChannelId === ch.channel_id) {
                btn.classList.add('active');
            }
            btn.onclick = () => selectVoiceChannel(room.room_id, ch.channel_id, ch.name);
            leftWrap.appendChild(btn);
            row.appendChild(leftWrap);

            // Channel actions for owner
            if (isOwner) {
                appendChannelActionBtns(row, room.room_id, ch.channel_id, ch.name, (room.channels || []).length > 1);
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
            leftWrap.appendChild(btn);
            row.appendChild(leftWrap);

            if (isOwner) {
                appendChannelActionBtns(row, room.room_id, ch.channel_id, ch.name, (room.channels || []).length > 1);
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

function appendChannelActionBtns(container, roomId, channelId, name, canDelete = true) {
    const actions = document.createElement('div');
    actions.className = 'channel-actions';

    const renameBtn = document.createElement('button');
    renameBtn.className = 'channel-action-btn';
    renameBtn.title = 'Rename Channel';
    renameBtn.innerHTML = `<span class="material-symbols-outlined">edit</span>`;
    renameBtn.onclick = (e) => {
        e.stopPropagation();
        openRenameChannelModal(roomId, channelId, name);
    };
    actions.appendChild(renameBtn);

    if (canDelete) {
        const delBtn = document.createElement('button');
        delBtn.className = 'channel-action-btn btn-delete';
        delBtn.title = 'Delete Channel';
        delBtn.innerHTML = `<span class="material-symbols-outlined">delete</span>`;
        delBtn.onclick = (e) => {
            e.stopPropagation();
            showConfirmModal({
                title: 'Delete Channel',
                message: `Are you sure you want to delete #${name}? This action cannot be undone.`,
                confirmText: 'Delete Channel',
                isDanger: true,
                onConfirm: () => {
                    window.pywebview.api.delete_channel(roomId, channelId);
                }
            });
        };
        actions.appendChild(delBtn);
    }
    container.appendChild(actions);
}

function openRenameChannelModal(roomId, channelId, currentName) {
    showPromptModal({
        title: 'Rename Channel',
        desc: 'Enter new channel name:',
        placeholder: 'channel-name',
        initialValue: currentName,
        confirmText: 'Save',
        onConfirm: (newName) => {
            if (newName && newName.trim()) {
                window.pywebview.api.rename_channel(roomId, channelId, newName.trim());
            }
        }
    });
}

function renderChannelVoiceUsers(container, channelId) {
    container.innerHTML = '';
    const users = state.voiceUsers[channelId] || [];
    users.forEach(u => {
        const row = document.createElement('div');
        row.className = `channel-voice-user ${u.is_speaking ? 'speaking' : ''}`;
        row.id = `v-user-${channelId}-${u.user_id}`;
        row.style.cursor = 'pointer';
        row.title = 'View Profile';
        row.onclick = () => showUserProfileModal(u.user_id);

        const avStyle = u.avatar_image ? `background-image: url(data:image/png;base64,${u.avatar_image});` : `background-color: ${u.avatar_color || '#5865F2'};`;
        const avLetter = u.avatar_image ? '' : (u.display_name || u.username).charAt(0).toUpperCase();

        let icons = '';
        if (u.is_muted) icons += `<span class="material-symbols-outlined icon-status-muted" title="Muted">mic_off</span>`;
        if (u.is_deafened) icons += `<span class="material-symbols-outlined icon-status-deafened" title="Deafened">headset_off</span>`;

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

    renderCachedMessages('channel', channelId);
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

    const memberSidebar = document.getElementById('member-sidebar');
    if (memberSidebar) memberSidebar.classList.add('hidden');

    document.getElementById('channel-header-icon').textContent = 'forum';
    document.getElementById('channel-header-title').textContent = `@${peerName}`;
    document.getElementById('channel-header-desc').textContent = `Direct message with ${peerName}`;
    document.getElementById('chat-text-input').placeholder = `Message @${peerName}`;
    
    // Only show call button if peer is accepted friend
    const friendRecord = (state.friends || []).find(f => (f.peer_id === peerId || f.user_id === peerId));
    const isFriend = Boolean(friendRecord && (friendRecord.friendship_status === 'accepted' || friendRecord.status === 'accepted'));
    const callHeaderBtn = document.getElementById('btn-header-call');
    if (callHeaderBtn) {
        if (isFriend) {
            callHeaderBtn.classList.remove('hidden');
        } else {
            callHeaderBtn.classList.add('hidden');
        }
    }

    document.getElementById('btn-toggle-members').classList.add('hidden');

    renderCachedMessages('dm', peerId);
    window.pywebview.api.get_history('dm', peerId);
}

function selectVoiceChannel(roomId, channelId, channelName) {
    const isAlreadyConnected = (state.currentVoiceChannelId === channelId);
    
    // If just viewing a text channel but connected to voice, clicking voice again should just show the voice stage
    if (isAlreadyConnected) {
        document.getElementById('view-friends').classList.add('hidden');
        document.getElementById('view-chat').classList.add('hidden');
        document.getElementById('view-voice-stage').classList.remove('hidden');
        return;
    }

    state.currentVoiceChannelId = channelId;
    state.currentVoiceRoomId = roomId;
    state.currentVoiceChannelName = channelName;

    // Highlight active voice channel in sidebar
    document.querySelectorAll('.channel-item .sidebar-item').forEach(b => b.classList.remove('active'));
    const channelVoiceCont = document.getElementById(`voice-users-${channelId}`);
    if (channelVoiceCont && channelVoiceCont.previousElementSibling) {
        const btn = channelVoiceCont.previousElementSibling.querySelector('.sidebar-item');
        if (btn) btn.classList.add('active');
    }

    state.voiceUsers[channelId] = state.voiceUsers[channelId] || [];
    if (state.user && !state.voiceUsers[channelId].some(x => x.user_id === state.user.user_id)) {
        state.voiceUsers[channelId].push({
            user_id: state.user.user_id,
            username: state.user.username,
            display_name: state.user.display_name || state.user.username,
            avatar_color: state.user.avatar_color || '#5865F2',
            avatar_image: state.user.avatar_image || '',
            is_muted: Boolean(state.isMuted),
            is_deafened: Boolean(state.isDeafened),
            is_speaking: false
        });
    }

    const bar = document.getElementById('voice-status-bar');
    bar.classList.remove('hidden');
    bar.classList.remove('connected');
    const titleEl = bar.querySelector('.voice-status-title');
    if (titleEl) titleEl.textContent = t('rtc_connecting') || 'RTC Connecting...';
    document.getElementById('voice-status-channel').textContent = `${channelName} / Connecting...`;

    document.getElementById('view-friends').classList.add('hidden');
    document.getElementById('view-chat').classList.add('hidden');
    document.getElementById('view-voice-stage').classList.remove('hidden');

    document.getElementById('channel-header-icon').textContent = 'volume_up';
    document.getElementById('channel-header-title').textContent = channelName;
    document.getElementById('channel-header-desc').textContent = `Voice Channel - RTC Connecting...`;
    document.getElementById('btn-header-call').classList.add('hidden');
    document.getElementById('btn-toggle-members').classList.add('hidden');

    const cont = document.getElementById(`voice-users-${channelId}`);
    if (cont) renderChannelVoiceUsers(cont, channelId);

    renderVoiceStage(channelName);
    window.pywebview.api.join_voice(roomId, channelId);
}

function onVoiceChannelSync(payload) {
    const { room_id, channel_id, users } = payload;
    if (!channel_id || !Array.isArray(users)) return;

    state.voiceUsers[channel_id] = users.map(u => {
        const cached = state.users[u.user_id] || {};
        return {
            user_id: u.user_id,
            username: u.username || cached.username || u.user_id,
            display_name: u.display_name || cached.display_name || u.username || u.user_id,
            avatar_color: u.avatar_color || cached.avatar_color || '#5865F2',
            avatar_image: u.avatar_image || cached.avatar_image || '',
            is_muted: Boolean(u.is_muted),
            is_deafened: Boolean(u.is_deafened),
            is_speaking: false
        };
    });

    const cont = document.getElementById(`voice-users-${channel_id}`);
    if (cont) {
        renderChannelVoiceUsers(cont, channel_id);
    }
    if (state.currentVoiceChannelId === channel_id) {
        renderVoiceStage(channel_id);
    }
}

function onVoiceStateUpdate(payload) {
    const { user_id, room_id, channel_id, action, is_muted, is_deafened } = payload;
    if (!channel_id) return;

    state.voiceUsers[channel_id] = state.voiceUsers[channel_id] || [];

    if (action === 'join') {
        // Purge user from all other voice channels to prevent multi-room ghosting
        Object.keys(state.voiceUsers).forEach(otherChId => {
            if (otherChId !== channel_id && state.voiceUsers[otherChId]) {
                const hadUser = state.voiceUsers[otherChId].some(x => x.user_id === user_id);
                if (hadUser) {
                    state.voiceUsers[otherChId] = state.voiceUsers[otherChId].filter(x => x.user_id !== user_id);
                    const otherCont = document.getElementById(`voice-users-${otherChId}`);
                    if (otherCont) {
                        renderChannelVoiceUsers(otherCont, otherChId);
                    }
                }
            }
        });

        const u = state.users[user_id] || { user_id, username: user_id, display_name: user_id };
        const existing = state.voiceUsers[channel_id].find(x => x.user_id === user_id);
        if (existing) {
            existing.is_muted = Boolean(is_muted);
            existing.is_deafened = Boolean(is_deafened);
        } else {
            state.voiceUsers[channel_id].push({
                user_id,
                username: u.username || user_id,
                display_name: u.display_name || u.username || user_id,
                avatar_color: u.avatar_color || '#5865F2',
                avatar_image: u.avatar_image || '',
                is_muted: Boolean(is_muted),
                is_deafened: Boolean(is_deafened),
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

// ---------------- Custom Confirmation Dialog (Replaces native browser confirm()) ----------------

function showConfirmModal({ title = 'Are you sure?', message = 'Do you really want to proceed?', confirmText = 'Confirm', isDanger = true, onConfirm }) {
    const modal = document.getElementById('modal-confirm');
    if (!modal) return;
    document.getElementById('confirm-title').textContent = title;
    document.getElementById('confirm-message').textContent = message;

    const okBtn = document.getElementById('btn-confirm-ok');
    const cancelBtn = document.getElementById('btn-confirm-cancel');

    okBtn.textContent = confirmText;
    okBtn.className = isDanger ? 'btn-danger' : 'btn-primary';

    const cleanup = () => {
        modal.classList.add('hidden');
        okBtn.onclick = null;
        cancelBtn.onclick = null;
    };

    okBtn.onclick = () => {
        cleanup();
        if (onConfirm) onConfirm();
    };

    cancelBtn.onclick = () => {
        cleanup();
    };

    modal.classList.remove('hidden');
}

// ---------------- User Profile Card Modal ----------------

function showUserProfileModal(userId) {
    const modal = document.getElementById('modal-user-profile');
    if (!modal) return;

    let targetUser = null;
    if (state.user && state.user.user_id === userId) {
        targetUser = state.user;
    } else if (state.users && state.users[userId]) {
        targetUser = state.users[userId];
    } else if (state.friends) {
        const f = state.friends.find(x => (x.user_id === userId || x.peer_id === userId));
        if (f) {
            targetUser = {
                user_id: userId,
                username: f.username || f.peer_name || '',
                display_name: f.display_name || f.peer_display_name || f.username,
                avatar_color: f.avatar_color || '#5865F2',
                avatar_image: f.avatar_image || '',
                banner_color: f.banner_color || '#5865F2',
                banner_image: f.banner_image || '',
                bio: f.bio || '',
                status_text: f.status_text || (f.online ? 'Online' : 'Offline'),
                online: !!(f.online || f.is_online)
            };
        }
    }

    if (!targetUser) {
        targetUser = {
            user_id: userId,
            username: userId,
            display_name: userId,
            avatar_color: '#5865F2',
            avatar_image: '',
            banner_color: '#5865F2',
            banner_image: '',
            bio: 'No profile details available.',
            status_text: 'Offline',
            online: false
        };
    }

    const dispName = targetUser.display_name || targetUser.username || 'User';
    const username = targetUser.username || 'user';
    const isOnline = Boolean(targetUser.online || targetUser.is_online);

    // Banner
    const bannerEl = document.getElementById('user-profile-banner');
    if (targetUser.banner_image) {
        bannerEl.style.backgroundImage = `url(data:image/png;base64,${targetUser.banner_image})`;
        bannerEl.style.backgroundColor = '';
    } else {
        bannerEl.style.backgroundImage = '';
        bannerEl.style.backgroundColor = targetUser.banner_color || '#5865F2';
    }

    // Avatar
    const avatarEl = document.getElementById('user-profile-avatar');
    if (targetUser.avatar_image) {
        avatarEl.style.backgroundImage = `url(data:image/png;base64,${targetUser.avatar_image})`;
        avatarEl.style.backgroundColor = '';
        avatarEl.textContent = '';
    } else {
        avatarEl.style.backgroundImage = '';
        avatarEl.style.backgroundColor = targetUser.avatar_color || '#5865F2';
        avatarEl.textContent = dispName.charAt(0).toUpperCase();
        avatarEl.style.display = 'flex';
        avatarEl.style.alignItems = 'center';
        avatarEl.style.justifyContent = 'center';
        avatarEl.style.color = '#fff';
        avatarEl.style.fontSize = '32px';
        avatarEl.style.fontWeight = 'bold';
    }

    // Status dot
    const dotEl = document.getElementById('user-profile-status-dot');
    dotEl.className = `status-dot profile-modal-status-dot ${isOnline ? 'status-online' : 'status-offline'}`;

    // Names
    document.getElementById('user-profile-display-name').textContent = dispName;
    document.getElementById('user-profile-username').textContent = `@${username}`;

    // Status badge
    const badgeEl = document.getElementById('user-profile-status-badge');
    badgeEl.textContent = targetUser.status_text || (isOnline ? 'Online' : 'Offline');

    // Bio
    const bioEl = document.getElementById('user-profile-bio');
    bioEl.textContent = targetUser.bio || 'No bio set.';

    // Actions
    const isSelf = (state.user && state.user.user_id === userId);
    const actionsEl = document.getElementById('user-profile-actions');
    if (isSelf) {
        actionsEl.style.display = 'none';
    } else {
        actionsEl.style.display = 'flex';
        const msgBtn = document.getElementById('btn-profile-send-msg');
        const callBtn = document.getElementById('btn-profile-call');
        const addFriendBtn = document.getElementById('btn-profile-add-friend');

        const friendRecord = (state.friends || []).find(f => (f.peer_id === userId || f.user_id === userId));
        const isFriend = Boolean(friendRecord && (friendRecord.friendship_status === 'accepted' || friendRecord.status === 'accepted'));

        msgBtn.onclick = () => {
            closeUserProfileModal();
            selectDmUser(userId, dispName);
        };

        if (isFriend) {
            callBtn.classList.remove('hidden');
            if (addFriendBtn) addFriendBtn.classList.add('hidden');
            callBtn.onclick = () => {
                closeUserProfileModal();
                startDirectCall(userId, dispName);
            };
        } else {
            callBtn.classList.add('hidden');
            if (addFriendBtn) {
                addFriendBtn.classList.remove('hidden');
                addFriendBtn.onclick = () => {
                    closeUserProfileModal();
                    window.pywebview.api.send_friend_request(targetUser.username);
                    showToast(`Friend request sent to @${targetUser.username}`);
                };
            }
        }
    }

    modal.classList.remove('hidden');
}

function closeUserProfileModal() {
    const modal = document.getElementById('modal-user-profile');
    if (modal) modal.classList.add('hidden');
}

function startDirectCall(userId, userName) {
    const friendRecord = (state.friends || []).find(f => (f.peer_id === userId || f.user_id === userId));
    const isFriend = Boolean(friendRecord && (friendRecord.friendship_status === 'accepted' || friendRecord.status === 'accepted'));
    if (!isFriend) {
        showToast('Calls are only available with friends / Звонки доступны только друзьям');
        return;
    }
    selectDmUser(userId, userName);
    window.pywebview.api.start_call(userId);
}

function promptCreateRoom() {
    showPromptModal({
        title: t('create_server_title', 'Create a Server'),
        desc: t('create_server_desc', 'Enter a name for your new server:'),
        placeholder: t('create_server_placeholder', 'e.g. My Gaming Server'),
        confirmText: t('create_server_btn', 'Create Server'),
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
        title: t('join_server_title', 'Join a Server'),
        desc: t('join_server_desc', 'Enter an invite link or code:'),
        placeholder: t('join_server_placeholder', 'e.g. vc-abc12345'),
        confirmText: t('join_server_btn', 'Join Server'),
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
        title: t('create_channel_title', 'Create Channel'),
        desc: t('create_channel_desc', 'Enter channel name and select type:'),
        placeholder: 'e.g. general',
        confirmText: t('create_channel_btn', 'Create Channel'),
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

function onRoomCreated(payload) {
    const room = (payload && payload.room) ? payload.room : payload;
    if (!room || !room.room_id) return;
    state.rooms[room.room_id] = room;
    renderServerRail();
    switchMode('server', room.room_id);
    showToast(`${t('server_created', 'Server created!')}: "${room.name}"`);
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
    const { room_id, members, voice_channels } = payload;
    if (state.currentRoomId === room_id) {
        renderMemberList(members);
    }
    if (voice_channels && typeof voice_channels === 'object') {
        Object.entries(voice_channels).forEach(([cid, users]) => {
            state.voiceUsers[cid] = (users || []).map(u => ({
                user_id: u.user_id,
                username: u.username || u.user_id,
                display_name: u.display_name || u.username || u.user_id,
                avatar_color: u.avatar_color || '#5865F2',
                avatar_image: u.avatar_image || '',
                is_muted: Boolean(u.is_muted),
                is_deafened: Boolean(u.is_deafened),
                is_speaking: false
            }));
            const cont = document.getElementById(`voice-users-${cid}`);
            if (cont) {
                renderChannelVoiceUsers(cont, cid);
            }
            if (state.currentVoiceChannelId === cid) {
                renderVoiceStage(cid);
            }
        });
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
        if (!state.users[m.user_id]) {
            state.users[m.user_id] = m;
        } else {
            Object.assign(state.users[m.user_id], m);
        }
        item.onclick = () => showUserProfileModal(m.user_id);
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

const messageAttachmentsCache = new Map();

// ---------------- Local Message Cache (Instant 0ms Channel Switching) ----------------
const localMessageCache = new Map();

function getCacheKey(targetType, targetId) {
    return `vc_cache_${targetType}_${targetId}`;
}

function loadCachedMessages(targetType, targetId) {
    if (!targetId) return [];
    const key = getCacheKey(targetType, targetId);
    if (localMessageCache.has(key)) {
        return localMessageCache.get(key);
    }
    try {
        const raw = localStorage.getItem(key);
        if (raw) {
            const parsed = JSON.parse(raw);
            if (Array.isArray(parsed)) {
                localMessageCache.set(key, parsed);
                return parsed;
            }
        }
    } catch (e) {
        console.warn('Failed to load cached messages:', e);
    }
    return [];
}

function saveCachedMessages(targetType, targetId, messages) {
    if (!targetId || !Array.isArray(messages)) return;
    const key = getCacheKey(targetType, targetId);
    const recent = messages.slice(-100);
    localMessageCache.set(key, recent);
    try {
        const storable = recent.map(m => {
            if (m.file_data && m.file_data.length > 50000) {
                return { ...m, file_data: '' };
            }
            return m;
        });
        localStorage.setItem(key, JSON.stringify(storable));
    } catch (e) {
        console.warn('Failed to persist cached messages to localStorage:', e);
    }
}

function renderCachedMessages(targetType, targetId) {
    const list = document.getElementById('chat-messages-list');
    list.innerHTML = '';
    const cached = loadCachedMessages(targetType, targetId);
    if (cached && cached.length > 0) {
        const frag = document.createDocumentFragment();
        cached.forEach(m => {
            if (m.file_data) {
                messageAttachmentsCache.set(m.msg_id, { name: m.file_name, data: m.file_data });
            }
            const row = createChatMessageElement(m);
            if (row) frag.appendChild(row);
        });
        list.appendChild(frag);
        scrollToBottom();
    }
}

function sendMessage() {
    const input = document.getElementById('chat-text-input');
    const text = input.value.trim();
    if (!text && !state.currentAttachment) return;

    const targetType = state.currentDmPeerId ? 'dm' : 'channel';
    const targetId = state.currentDmPeerId || state.currentChannelId;
    if (!targetId) return;

    const clientMsgId = `m-${Date.now()}-${Math.random().toString(36).substr(2, 6)}`;

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

    if (fileData) {
        messageAttachmentsCache.set(clientMsgId, { name: fileName, data: fileData });
    }

    const localMsg = {
        msg_id: clientMsgId,
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

    const cached = loadCachedMessages(targetType, targetId);
    if (!cached.some(m => m.msg_id === localMsg.msg_id)) {
        cached.push(localMsg);
        saveCachedMessages(targetType, targetId, cached);
    }

    window.pywebview.api.send_chat_message(
        targetType, targetId, text,
        imgData, '', 0.0,
        fileData, fileName, fileSize,
        clientMsgId
    );
}

// ---------------- Markdown Parser (Full Discord Standard) ----------------

function formatMarkdown(text) {
    if (!text) return '';

    // 1. Extract multiline code blocks ```...```
    const codeBlocks = [];
    let processed = text.replace(/```(?:[a-zA-Z0-9_-]*\r?\n)?([\s\S]*?)```/g, (match, code) => {
        const id = `§§VCCODEBLOCK${codeBlocks.length}§§`;
        codeBlocks.push(`<pre class="chat-code-block"><code>${escapeHtml(code.trim())}</code></pre>`);
        return id;
    });

    // 2. Extract inline code `...`
    const inlineCodes = [];
    processed = processed.replace(/`([^`\r\n]+)`/g, (match, code) => {
        const id = `§§VCINLINECODE${inlineCodes.length}§§`;
        inlineCodes.push(`<code class="chat-inline-code">${escapeHtml(code)}</code>`);
        return id;
    });

    // 3. Escape HTML on text outside code blocks
    processed = escapeHtml(processed);

    // 4. Blockquotes (> ...)
    processed = processed.replace(/^(&gt;|>)\s+(.*)$/gm, '<blockquote class="chat-blockquote">$2</blockquote>');

    // 5. Spoilers ||...||
    processed = processed.replace(/\|\|([\s\S]+?)\|\|/g, '<span class="chat-spoiler" onclick="this.classList.toggle(\'revealed\')">$1</span>');

    // 6. Bold Italic (***text*** or ___text___)
    processed = processed.replace(/\*\*\*([\s\S]+?)\*\*\*/g, '<strong><em>$1</em></strong>');
    processed = processed.replace(/___([\s\S]+?)___/g, '<u><em>$1</em></u>');

    // 7. Bold (**text**)
    processed = processed.replace(/\*\*([\s\S]+?)\*\*/g, '<strong>$1</strong>');

    // 8. Underline (__text__)
    processed = processed.replace(/__([\s\S]+?)__/g, '<u>$1</u>');

    // 9. Italic (*text* or _text_)
    processed = processed.replace(/(?<!\*)\*([^*\r\n]+)\*(?!\*)/g, '<em>$1</em>');
    processed = processed.replace(/(?<!_)_([^_\r\n]+)_(?!_)/g, '<em>$1</em>');

    // 10. Strikethrough (~~text~~)
    processed = processed.replace(/~~([\s\S]+?)~~/g, '<del>$1</del>');

    // 11. Markdown links [text](url) and auto-link URLs
    processed = processed.replace(/\[([^\]]+)\]\((https?:\/\/[^\s<]+)\)/g, '<a href="$2" class="chat-link" target="_blank" rel="noopener noreferrer">$1</a>');
    processed = processed.replace(/(?<!href=")(https?:\/\/[^\s<]+)/g, '<a href="$1" class="chat-link" target="_blank" rel="noopener noreferrer">$1</a>');

    // 12. Convert newlines to <br>
    processed = processed.replace(/\r?\n/g, '<br>');

    // 13. Restore inline code and code blocks
    inlineCodes.forEach((ic, idx) => {
        processed = processed.replace(new RegExp(`§§VCINLINECODE${idx}§§`, 'g'), ic);
    });
    codeBlocks.forEach((cb, idx) => {
        processed = processed.replace(new RegExp(`§§VCCODEBLOCK${idx}§§`, 'g'), cb);
    });

    return processed;
}

// ---------------- Chat Message Element Construction ----------------

function onDownloadFileClick(msgId, defaultName) {
    const cached = messageAttachmentsCache.get(msgId);
    if (cached && cached.data) {
        downloadFile(cached.name || defaultName, cached.data);
    } else {
        downloadFile(defaultName, '');
    }
}

function createChatMessageElement(msg) {
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
    if (msg.file_data || msg.file_name) {
        if (msg.file_data) {
            messageAttachmentsCache.set(msg.msg_id, { name: msg.file_name, data: msg.file_data });
        }
        mediaHtml += `
            <div class="msg-file-card" onclick="onDownloadFileClick('${msg.msg_id}', '${escapeHtml(msg.file_name)}')">
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
        <div class="avatar-wrap" onclick="showUserProfileModal('${msg.sender_id}')" style="cursor: pointer;" title="View Profile">
            <div class="avatar" style="${avStyle}">${avLetter}</div>
        </div>
        <div class="msg-content-wrap">
            <div class="msg-header">
                <span class="msg-sender" onclick="showUserProfileModal('${msg.sender_id}')" style="cursor: pointer;" title="View Profile">${escapeHtml(senderName)}</span>
                <span class="msg-time">${timeStr}</span>
                ${deleteHtml}
            </div>
            ${msg.content ? `<div class="msg-text">${formatMarkdown(msg.content)}</div>` : ''}
            ${mediaHtml}
        </div>
    `;

    // Right-click context menu on message
    row.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        e.stopPropagation();
        showCustomContextMenu(e, msg);
    });

    return row;
}

function onChatMessageReceived(msg) {
    const targetType = msg.target_type || (msg.target_id && msg.target_id.startsWith('ch-') ? 'channel' : 'dm');
    const targetId = (msg.target_type === 'dm' && msg.sender_id !== state.user?.user_id) ? msg.sender_id : msg.target_id;

    // Cache incoming message
    if (targetId) {
        const cached = loadCachedMessages(targetType, targetId);
        if (!cached.some(m => m.msg_id === msg.msg_id)) {
            cached.push(msg);
            saveCachedMessages(targetType, targetId, cached);
        }
    }

    const activeTargetId = state.currentDmPeerId || state.currentChannelId;
    const isRelevant = msg.target_id === activeTargetId ||
                       (msg.target_type === 'dm' && (msg.sender_id === state.currentDmPeerId || msg.target_id === state.currentDmPeerId));

    if (isRelevant) {
        // If message already rendered (via client optimistic update or duplicate event), do not duplicate!
        const existing = document.getElementById(`msg-${msg.msg_id}`);
        if (existing) {
            return;
        }
        appendChatMessage(msg);
    } 

    if (msg.sender_id !== state.user?.user_id) {
        let isMention = false;
        if (state.user && state.user.username) {
            isMention = (msg.content || "").includes(`@${state.user.username}`);
        }
        let isDm = msg.target_type === 'dm';
        
        if (!state.dndMode && (!isRelevant || !document.hasFocus())) {
            if (isDm) {
                showToast(`New DM from @${msg.sender_name || 'User'}`);
                triggerNativeNotification(`DM from @${msg.sender_name || 'User'}`, msg.content);
            } else if (isMention) {
                showToast(`@${msg.sender_name || 'User'} mentioned you`);
                triggerNativeNotification(`Mention from @${msg.sender_name || 'User'}`, msg.content);
            }
        }
    }
}

function onHistoryReceived(data) {
    const targetType = data.target_type || (data.target_id && data.target_id.startsWith('ch-') ? 'channel' : 'dm');
    const targetId = data.target_id;
    const msgs = data.messages || [];

    // Save authoritative server history to cache
    if (targetId) {
        saveCachedMessages(targetType, targetId, msgs);
    }

    const activeTargetId = state.currentDmPeerId || state.currentChannelId;
    if (targetId && targetId !== activeTargetId) {
        return;
    }

    const list = document.getElementById('chat-messages-list');
    list.innerHTML = '';
    const frag = document.createDocumentFragment();
    msgs.forEach(m => {
        if (m.file_data) {
            messageAttachmentsCache.set(m.msg_id, { name: m.file_name, data: m.file_data });
        }
        const row = createChatMessageElement(m);
        if (row) frag.appendChild(row);
    });
    list.appendChild(frag);
    scrollToBottom();
}

function onMessageDeleted(data) {
    const el = document.getElementById(`msg-${data.msg_id}`);
    if (el) el.remove();

    const activeTargetId = state.currentDmPeerId || state.currentChannelId;
    const targetType = state.currentDmPeerId ? 'dm' : 'channel';
    if (activeTargetId) {
        let cached = loadCachedMessages(targetType, activeTargetId);
        cached = cached.filter(m => m.msg_id !== data.msg_id);
        saveCachedMessages(targetType, activeTargetId, cached);
    }
}

function appendChatMessage(msg, autoScroll = true) {
    const list = document.getElementById('chat-messages-list');
    const existing = document.getElementById(`msg-${msg.msg_id}`);
    if (existing) return;

    const row = createChatMessageElement(msg);
    list.appendChild(row);
    if (autoScroll) scrollToBottom();
}

function scrollToBottom() {
    const container = document.getElementById('chat-messages-container');
    if (container) {
        container.scrollTop = container.scrollHeight;
    }
}

// ---------------- Custom Discord Context Menu ----------------

let currentContextMenuMsg = null;

function setupCustomContextMenu() {
    const menu = document.getElementById('custom-context-menu');
    if (!menu) return;

    // Suppress browser default context menu across the app except for inputs
    document.addEventListener('contextmenu', (e) => {
        const targetImg = e.target.closest('.msg-image');
        const targetRow = e.target.closest('.chat-message-row');
        const isInput = e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.isContentEditable;
        if (!targetRow && !targetImg && !isInput) {
            e.preventDefault();
            hideCustomContextMenu();
        }
    });

    // Close on outside click
    document.addEventListener('click', (e) => {
        if (!menu.contains(e.target)) {
            hideCustomContextMenu();
        }
    });

    // Close on Escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            hideCustomContextMenu();
        }
    });

    // Menu Actions
    document.getElementById('ctx-copy-text').onclick = () => {
        if (currentContextMenuMsg && currentContextMenuMsg.content) {
            navigator.clipboard.writeText(currentContextMenuMsg.content);
            showToast(t('text_copied', 'Text copied to clipboard'));
        }
        hideCustomContextMenu();
    };

    document.getElementById('ctx-open-image').onclick = () => {
        if (currentContextMenuMsg && currentContextMenuMsg.image_data) {
            openLightbox(`data:image/png;base64,${currentContextMenuMsg.image_data}`);
        }
        hideCustomContextMenu();
    };

    document.getElementById('ctx-copy-image').onclick = async () => {
        if (currentContextMenuMsg && currentContextMenuMsg.image_data) {
            try {
                const res = await fetch(`data:image/png;base64,${currentContextMenuMsg.image_data}`);
                const blob = await res.blob();
                await navigator.clipboard.write([
                    new ClipboardItem({ 'image/png': blob })
                ]);
                showToast(t('image_copied', 'Image copied to clipboard'));
            } catch (err) {
                console.error('Copy image failed:', err);
                showToast(t('copy_failed', 'Failed to copy image'));
            }
        }
        hideCustomContextMenu();
    };

    document.getElementById('ctx-save-image').onclick = () => {
        if (currentContextMenuMsg && currentContextMenuMsg.image_data) {
            downloadFile(`vimcord_${Date.now()}.png`, currentContextMenuMsg.image_data);
        }
        hideCustomContextMenu();
    };

    document.getElementById('ctx-copy-id').onclick = () => {
        if (currentContextMenuMsg && currentContextMenuMsg.msg_id) {
            navigator.clipboard.writeText(currentContextMenuMsg.msg_id);
            showToast(t('id_copied', 'Message ID copied'));
        }
        hideCustomContextMenu();
    };

    document.getElementById('ctx-delete-msg').onclick = () => {
        if (currentContextMenuMsg) {
            deleteMessage(currentContextMenuMsg.msg_id, currentContextMenuMsg.target_type, currentContextMenuMsg.target_id);
        }
        hideCustomContextMenu();
    };
}

function showCustomContextMenu(e, msg) {
    const menu = document.getElementById('custom-context-menu');
    if (!menu) return;

    currentContextMenuMsg = msg;

    const copyTextBtn = document.getElementById('ctx-copy-text');
    const openImgBtn = document.getElementById('ctx-open-image');
    const copyImgBtn = document.getElementById('ctx-copy-image');
    const saveImgBtn = document.getElementById('ctx-save-image');
    const copyIdBtn = document.getElementById('ctx-copy-id');
    const deleteBtn = document.getElementById('ctx-delete-msg');
    const divider = document.getElementById('ctx-divider-msg');

    const hasText = Boolean(msg && msg.content);
    const hasImage = Boolean(msg && msg.image_data);
    const isMine = Boolean(msg && msg.sender_id === state.user?.user_id);

    copyTextBtn.style.display = hasText ? 'flex' : 'none';
    openImgBtn.style.display = hasImage ? 'flex' : 'none';
    copyImgBtn.style.display = hasImage ? 'flex' : 'none';
    saveImgBtn.style.display = hasImage ? 'flex' : 'none';
    copyIdBtn.style.display = msg ? 'flex' : 'none';
    deleteBtn.style.display = isMine ? 'flex' : 'none';
    if (divider) divider.style.display = (msg && (hasText || hasImage)) ? 'block' : 'none';

    menu.classList.remove('hidden');

    const menuW = 210;
    const menuH = 220;
    let x = e.clientX;
    let y = e.clientY;

    if (x + menuW > window.innerWidth) {
        x = window.innerWidth - menuW - 10;
    }
    if (y + menuH > window.innerHeight) {
        y = window.innerHeight - menuH - 10;
    }

    menu.style.left = `${Math.max(10, x)}px`;
    menu.style.top = `${Math.max(10, y)}px`;
}

function hideCustomContextMenu() {
    const menu = document.getElementById('custom-context-menu');
    if (menu) menu.classList.add('hidden');
    currentContextMenuMsg = null;
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
    if (!b64) return;
    try {
        const audio = new Audio(`data:audio/wav;base64,${b64}`);
        audio.play().catch(() => {
            window.pywebview?.api?.play_voice_message(b64, dur);
        });
    } catch (e) {
        window.pywebview?.api?.play_voice_message(b64, dur);
    }
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

    if (!state.dndMode) {
        showToast(`Incoming call from @${data.from_username}`);
        triggerNativeNotification("Incoming Call", `@${data.from_username} is calling you.`);
    }
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
            is_muted: Boolean(state.isMuted),
            is_deafened: Boolean(state.isDeafened),
            is_speaking: false
        });
    }

    users.forEach(u => {
        const card = document.createElement('div');
        card.className = `voice-card ${u.is_speaking ? 'speaking' : ''}`;
        card.id = `stage-card-${u.user_id}`;
        card.style.cursor = 'pointer';
        card.title = 'View Profile';
        card.onclick = () => showUserProfileModal(u.user_id);

        const avStyle = u.avatar_image ? `background-image: url(data:image/png;base64,${u.avatar_image});` : `background-color: ${u.avatar_color || '#5865F2'};`;
        const avLetter = u.avatar_image ? '' : (u.display_name || u.username).charAt(0).toUpperCase();

        let cardBadges = '';
        if (u.is_muted) {
            cardBadges += `<span class="material-symbols-outlined card-status-badge muted" title="Muted">mic_off</span>`;
        }
        if (u.is_deafened) {
            cardBadges += `<span class="material-symbols-outlined card-status-badge deafened" title="Deafened">headset_off</span>`;
        }

        card.innerHTML = `
            <div class="voice-card-avatar" style="${avStyle}">${avLetter}</div>
            <div class="voice-card-name-row">
                <span class="voice-card-name">${escapeHtml(u.display_name || u.username)}</span>
                <span class="voice-card-badges">${cardBadges}</span>
            </div>
        `;
        grid.appendChild(card);
    });
}

function onLocalSpeaking(data) {
    if (!state.user) return;
    updateUserSpeakingState(state.user.user_id, data.is_speaking);
}

const peerSpeakingTimeouts = new Map();

function onPeerSpeaking(data) {
    updateUserSpeakingState(data.user_id, data.is_speaking);
    if (data.is_speaking) {
        if (peerSpeakingTimeouts.has(data.user_id)) {
            clearTimeout(peerSpeakingTimeouts.get(data.user_id));
        }
        peerSpeakingTimeouts.set(data.user_id, setTimeout(() => {
            updateUserSpeakingState(data.user_id, false);
            peerSpeakingTimeouts.delete(data.user_id);
        }, 350));
    }
}

function updateUserSpeakingState(userId, isSpeaking) {
    const speaking = Boolean(isSpeaking);

    // 1. User bottom panel avatar if local user (Green ring like Discord)
    if (state.user && userId === state.user.user_id) {
        const userPanelAvatar = document.getElementById('user-panel-avatar');
        if (userPanelAvatar) userPanelAvatar.classList.toggle('speaking', speaking);
    }

    // 2. Stage Card
    const card = document.getElementById(`stage-card-${userId}`);
    if (card) card.classList.toggle('speaking', speaking);

    // 3. Channel user tree
    if (state.currentVoiceChannelId) {
        const treeUser = document.getElementById(`v-user-${state.currentVoiceChannelId}-${userId}`);
        if (treeUser) treeUser.classList.toggle('speaking', speaking);
    }

    // 4. DM Call cards
    if (state.user && userId === state.user.user_id) {
        const myCallAvatar = document.getElementById('call-my-avatar');
        if (myCallAvatar) myCallAvatar.classList.toggle('speaking', speaking);
    } else {
        const peerCallAvatar = document.getElementById('call-peer-avatar');
        if (peerCallAvatar) peerCallAvatar.classList.toggle('speaking', speaking);
    }
}

// ---------------- Screen Sharing ----------------

function updateScreenShareButtons(active) {
    const btnVoice = document.getElementById('btn-voice-screenshare');
    if (btnVoice) {
        btnVoice.classList.toggle('active', active);
        btnVoice.classList.toggle('streaming', active);
    }
    const btnCall = document.getElementById('btn-call-screenshare');
    if (btnCall) {
        btnCall.classList.toggle('active', active);
        btnCall.classList.toggle('streaming', active);
    }
}

function toggleScreenShare() {
    state.isSharingScreen = !state.isSharingScreen;
    updateScreenShareButtons(state.isSharingScreen);
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

function onLocalScreenFrame(data) {
    if (!state.isSharingScreen) return;
    const stageBox = document.getElementById('voice-screen-stream-box');
    const stageImg = document.getElementById('voice-stage-screen-img');
    if (stageBox && stageImg && state.currentVoiceChannelId) {
        stageBox.classList.remove('hidden');
        stageImg.src = `data:image/jpeg;base64,${data.frame}`;
    }

    const dmBox = document.getElementById('dm-call-screen-container');
    const dmImg = document.getElementById('dm-call-screen-img');
    if (dmBox && dmImg && (state.activeCallId || state.currentDmPeerId)) {
        dmBox.classList.remove('hidden');
        dmImg.src = `data:image/jpeg;base64,${data.frame}`;
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
    if (state.isSharingScreen) {
        state.isSharingScreen = false;
        updateScreenShareButtons(false);
    }
    showToast('Screen share ended');
}

// ---------------- Audio Controls (Mute / Deafen) ----------------

function updateVoiceUserMediaState(userId, isMuted, isDeafened) {
    if (state.users[userId]) {
        state.users[userId].is_muted = isMuted;
        state.users[userId].is_deafened = isDeafened;
    }
    Object.keys(state.voiceUsers).forEach(cid => {
        const u = (state.voiceUsers[cid] || []).find(x => x.user_id === userId);
        if (u) {
            u.is_muted = isMuted;
            u.is_deafened = isDeafened;
            const cont = document.getElementById(`voice-users-${cid}`);
            if (cont) renderChannelVoiceUsers(cont, cid);
            if (state.currentVoiceChannelId === cid) renderVoiceStage(cid);
        }
    });
}

function onUserMediaState(payload) {
    const { user_id, is_muted, is_deafened } = payload;
    if (!user_id) return;
    if (state.user && state.user.user_id === user_id) {
        state.isMuted = Boolean(is_muted);
        state.isDeafened = Boolean(is_deafened);
        const micBtn = document.getElementById('btn-toggle-mic');
        if (micBtn) {
            micBtn.classList.toggle('active', state.isMuted);
            document.getElementById('mic-icon-svg').textContent = state.isMuted ? 'mic_off' : 'mic';
            micBtn.title = state.isMuted ? t('unmute_mic', 'Unmute') : t('mute_mic', 'Mute');
        }
        const deafenBtn = document.getElementById('btn-toggle-deafen');
        if (deafenBtn) {
            deafenBtn.classList.toggle('active', state.isDeafened);
            document.getElementById('deafen-icon-svg').textContent = state.isDeafened ? 'headset_off' : 'headphones';
            deafenBtn.title = state.isDeafened ? t('undeafen_audio', 'Undeafen') : t('deafen_audio', 'Deafen');
        }
    }
    updateVoiceUserMediaState(user_id, Boolean(is_muted), Boolean(is_deafened));
}

function toggleMic() {
    state.isMuted = !state.isMuted;
    const btn = document.getElementById('btn-toggle-mic');
    btn.classList.toggle('active', state.isMuted);
    document.getElementById('mic-icon-svg').textContent = state.isMuted ? 'mic_off' : 'mic';
    btn.title = state.isMuted ? t('unmute_mic', 'Unmute') : t('mute_mic', 'Mute');
    if (state.user) {
        updateVoiceUserMediaState(state.user.user_id, state.isMuted, state.isDeafened);
    }
    window.pywebview.api.set_mic_muted(state.isMuted);
}

function toggleDeafen() {
    state.isDeafened = !state.isDeafened;
    const btn = document.getElementById('btn-toggle-deafen');
    btn.classList.toggle('active', state.isDeafened);
    document.getElementById('deafen-icon-svg').textContent = state.isDeafened ? 'headset_off' : 'headphones';
    btn.title = state.isDeafened ? t('undeafen_audio', 'Undeafen') : t('deafen_audio', 'Deafen');
    if (state.user) {
        updateVoiceUserMediaState(state.user.user_id, state.isMuted, state.isDeafened);
    }
    window.pywebview.api.set_deafened(state.isDeafened);
}

// ---------------- Settings Dialog (3-Page PyQt Parity) ----------------

function openSettings() {
    document.getElementById('modal-settings').classList.remove('hidden');

    // Dynamically refresh audio input & output devices
    if (window.pywebview && window.pywebview.api && typeof window.pywebview.api.get_audio_devices === 'function') {
        window.pywebview.api.get_audio_devices().then(devs => {
            if (devs) {
                populateAudioDevices(devs, state.config?.input_device, state.config?.output_device);
            }
        }).catch(err => console.warn('[Audio] Failed to get audio devices:', err));
    }

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
    document.getElementById('settings-user-preview').textContent = `@${state.user?.username || 'user'}`;
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
    state.theme = th;
    document.body.className = `theme-${th}`;
    document.querySelectorAll('.theme-picker-card').forEach(card => {
        const isMatch = (card.dataset.theme === th);
        card.classList.toggle('active', isMatch);
        const radio = card.querySelector('input[type="radio"]');
        if (radio) radio.checked = isMatch;
    });
}

function applyLanguage(lng) {
    state.language = lng;
    document.querySelectorAll('.lang-picker-card').forEach(card => {
        const isMatch = (card.dataset.lang === lng);
        card.classList.toggle('active', isMatch);
        const radio = card.querySelector('input[type="radio"]');
        if (radio) radio.checked = isMatch;
    });
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.dataset.i18n;
        if (I18N[lng] && I18N[lng][key]) {
            el.textContent = I18N[lng][key];
        }
    });
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
        const key = el.dataset.i18nPlaceholder;
        if (I18N[lng] && I18N[lng][key]) {
            el.placeholder = I18N[lng][key];
        }
    });
    document.querySelectorAll('[data-i18n-title]').forEach(el => {
        const key = el.dataset.i18nTitle;
        if (I18N[lng] && I18N[lng][key]) {
            el.title = I18N[lng][key];
        }
    });
    if (state.activeTab === 'home') {
        const sbTitle = document.getElementById('sidebar-title');
        if (sbTitle) sbTitle.textContent = t('direct_messages', 'Direct Messages');
    }
}

function populateAudioDevices(devs, savedInput = null, savedOutput = null) {
    const inSel = document.getElementById('select-audio-input');
    const outSel = document.getElementById('select-audio-output');
    if (!inSel || !outSel) return;

    inSel.innerHTML = '<option value="">Default System Microphone</option>';
    outSel.innerHTML = '<option value="">Default System Speakers</option>';

    const inputList = devs?.inputs || (Array.isArray(devs?.input) ? devs.input.map((n, i) => ({ id: i, name: n })) : []);
    const outputList = devs?.outputs || (Array.isArray(devs?.output) ? devs.output.map((n, i) => ({ id: i, name: n })) : []);

    const seenIn = new Set();
    inputList.forEach(d => {
        if (seenIn.has(d.name)) return;
        seenIn.add(d.name);
        const opt = document.createElement('option');
        opt.value = d.id;
        opt.textContent = d.name;
        if (savedInput !== null && savedInput !== undefined && String(d.id) === String(savedInput)) {
            opt.selected = true;
        }
        inSel.appendChild(opt);
    });

    const seenOut = new Set();
    outputList.forEach(d => {
        if (seenOut.has(d.name)) return;
        seenOut.add(d.name);
        const opt = document.createElement('option');
        opt.value = d.id;
        opt.textContent = d.name;
        if (savedOutput !== null && savedOutput !== undefined && String(d.id) === String(savedOutput)) {
            opt.selected = true;
        }
        outSel.appendChild(opt);
    });

    if (inputList.length === 0 && navigator.mediaDevices && navigator.mediaDevices.enumerateDevices) {
        navigator.mediaDevices.enumerateDevices().then(devices => {
            devices.forEach((d, idx) => {
                const label = d.label || (d.kind === 'audioinput' ? `Microphone ${idx + 1}` : `Speakers ${idx + 1}`);
                if (d.kind === 'audioinput') {
                    if (seenIn.has(label)) return;
                    seenIn.add(label);
                    const opt = document.createElement('option');
                    opt.value = d.deviceId || idx;
                    opt.textContent = label;
                    inSel.appendChild(opt);
                } else if (d.kind === 'audiooutput') {
                    if (seenOut.has(label)) return;
                    seenOut.add(label);
                    const opt = document.createElement('option');
                    opt.value = d.deviceId || idx;
                    opt.textContent = label;
                    outSel.appendChild(opt);
                }
            });
        }).catch(() => {});
    }
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
            <div class="friend-info" onclick="showUserProfileModal('${friendId}')" style="cursor: pointer;" title="View Profile">
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
    state.lastPingMs = data.ping_ms;
    const bar = document.getElementById('voice-status-bar');
    if (bar && state.currentVoiceChannelId) {
        bar.classList.add('connected');
        const titleEl = bar.querySelector('.voice-status-title');
        if (titleEl) {
            titleEl.textContent = t('voice_connected') || 'Voice Connected';
        }
        const chName = state.currentVoiceChannelName || 'General';
        const el = document.getElementById('voice-status-channel');
        if (el) el.textContent = `${chName} / ${data.ping_ms} ms`;
    }
    const desc = document.getElementById('channel-header-desc');
    if (desc && !document.getElementById('view-voice-stage').classList.contains('hidden')) {
        desc.textContent = `Voice Channel - RTC Connected (${data.ping_ms} ms)`;
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

function triggerNativeNotification(title, body) {
    if (window.__TAURI__ && window.__TAURI__.notification) {
        const { isPermissionGranted, requestPermission, sendNotification } = window.__TAURI__.notification;
        isPermissionGranted().then(granted => {
            if (!granted) {
                requestPermission().then(perm => {
                    if (perm === 'granted') {
                        sendNotification({ title: title, body: body });
                    }
                });
            } else {
                sendNotification({ title: title, body: body });
            }
        }).catch(err => console.warn('Native notification error:', err));
    } else if (window.Notification) {
        // Fallback to HTML5 Notifications if running in normal browser context
        if (Notification.permission === 'granted') {
            new Notification(title, { body });
        } else if (Notification.permission !== 'denied') {
            Notification.requestPermission().then(permission => {
                if (permission === 'granted') {
                    new Notification(title, { body });
                }
            });
        }
    }
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
