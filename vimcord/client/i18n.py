"""
Internationalization (i18n) dictionary and helper for VimCord.
Supports English ("en") and Russian ("ru").
"""

from typing import Dict

TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "en": {
        "app_title": "VimCord",
        "online": "Online",
        "offline": "Offline",
        "friends": "Friends",
        "all": "All",
        "pending": "Pending",
        "add_friend": "Add Friend",
        "members": "MEMBERS",
        "voice_connected": "Voice Connected",
        "voice_channel": "Voice Channel",
        "screen_share": "Screen Share",
        "stop_screen": "Stop Screen",
        "disconnect": "Disconnect",
        "settings": "Settings",
        "user_settings": "User Settings",
        "mute_mic": "Mute Microphone",
        "deafen_audio": "Deafen Audio",
        "direct_messages": "DIRECT MESSAGES",
        "text_channels": "TEXT CHANNELS",
        "voice_channels": "VOICE CHANNELS",
        "send_message": "Send message...",
        "save_file": "Save",
        "delete_message": "Delete Message",
        "connection_lost": "Connection Lost",
        "reconnecting_in": "Reconnecting in {seconds}s...",
        "reconnect_now": "Reconnect Now",
        "dnd_mode": "Do Not Disturb (Disable Toasts)",
        "watch_stream": "Watch Stream",
        "hide_stream": "Hide Stream",
        "popout_window": "Pop out window",
        "stream_volume": "Stream Volume",
        "user_volume": "USER VOLUME",
        "display_name": "Display Name",
        "username": "Username",
        "profile_banner": "Profile Banner",
        "change_banner": "Change Banner Cover",
        "banner_color": "Banner Color",
        "about_me": "ABOUT ME",
        "call": "Call",
        "message": "Message",
        "only_friends_call": "You can only call users who are on your friends list.",
        "record_keybind": "Record Keybind",
        "press_any_key": "Press any key...",
        "downloaded_to": "Downloaded to Downloads folder: {filename}",
        "user_busy": "User is busy or unavailable",
        "call_failed": "Call Failed",
        "call_declined": "Call Declined",
        "call_was_declined": "Call was declined.",
        "rename_channel": "Rename Channel",
        "delete_channel": "Delete Channel",
        "enter_channel_name": "Enter new channel name:",
        "confirm_delete_channel": "Are you sure you want to delete channel #{name}?",
        "chat": "Chat",
        "no_friends_yet": "No friends yet\nGo to the 'Friends' tab to add friends 👥",
    },
    "ru": {
        "app_title": "VimCord",
        "online": "В сети",
        "offline": "Не в сети",
        "friends": "Друзья",
        "all": "Все",
        "pending": "Ожидание",
        "add_friend": "Добавить в друзья",
        "members": "УЧАСТНИКИ",
        "voice_connected": "Голос подключен",
        "voice_channel": "Голосовой канал",
        "screen_share": "Демонстрация экрана",
        "stop_screen": "Остановить экран",
        "disconnect": "Отключиться",
        "settings": "Настройки",
        "user_settings": "Настройки пользователя",
        "mute_mic": "Заглушить микрофон",
        "deafen_audio": "Заглушить звук",
        "direct_messages": "ЛИЧНЫЕ СООБЩЕНИЯ",
        "text_channels": "ТЕКСТОВЫЕ КАНАЛЫ",
        "voice_channels": "ГОЛОСОВЫЕ КАНАЛЫ",
        "send_message": "Написать сообщение...",
        "save_file": "Сохранить",
        "delete_message": "Удалить сообщение",
        "connection_lost": "Соединение потеряно",
        "reconnecting_in": "Переподключение через {seconds}с...",
        "reconnect_now": "Подключиться сейчас",
        "dnd_mode": "Не беспокоить (Отключить всплывающие уведомления)",
        "watch_stream": "Смотреть стрим",
        "hide_stream": "Скрыть стрим",
        "popout_window": "В отдельном окне",
        "stream_volume": "Громкость стрима",
        "user_volume": "ГРОМКОСТЬ ПОЛЬЗОВАТЕЛЯ",
        "display_name": "Отображаемое имя",
        "username": "Имя пользователя (логин)",
        "profile_banner": "Баннер профиля",
        "change_banner": "Изменить обложку",
        "banner_color": "Цвет баннера",
        "about_me": "О СЕБЕ",
        "call": "Позвонить",
        "message": "Написать",
        "only_friends_call": "Звонить можно только тем, кто у вас в друзьях.",
        "record_keybind": "Задать кнопку",
        "press_any_key": "Нажмите любую клавишу...",
        "downloaded_to": "Файл сохранен в Загрузки: {filename}",
        "user_busy": "Пользователь занят или недоступен",
        "call_failed": "Не удалось позвонить",
        "call_declined": "Звонок отклонен",
        "call_was_declined": "Звонок был отклонен.",
        "rename_channel": "Переименовать канал",
        "delete_channel": "Удалить канал",
        "enter_channel_name": "Введите новое имя канала:",
        "confirm_delete_channel": "Вы уверены, что хотите удалить канал #{name}?",
        "chat": "Чат",
        "no_friends_yet": "Пока нет друзей\nПерейдите во вкладку 'Друзья' чтобы добавить друзей 👥",
    }
}

_CURRENT_LANG = "en"


def set_language(lang: str):
    global _CURRENT_LANG
    if lang in TRANSLATIONS:
        _CURRENT_LANG = lang


def get_language() -> str:
    return _CURRENT_LANG


def t(key: str, default: str = "") -> str:
    lang_dict = TRANSLATIONS.get(_CURRENT_LANG, TRANSLATIONS["en"])
    return lang_dict.get(key, default or key)
