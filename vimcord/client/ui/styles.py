"""
Discord-inspired modern dark theme QSS for VimCord.
"""

DARK_THEME_QSS = """
/* Global styling */
QWidget {
    background-color: #313338;
    color: #dbdee1;
    font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
    font-size: 14px;
    selection-background-color: #5865F2;
    selection-color: #ffffff;
}

QMainWindow, QDialog {
    background-color: #1e1f22;
}

/* Left Server Navigation Bar */
#server_nav_bar {
    background-color: #1e1f22;
    min-width: 72px;
    max-width: 72px;
}

QPushButton.server_btn {
    background-color: #313338;
    color: #dbdee1;
    border-radius: 24px;
    font-size: 16px;
    font-weight: bold;
    min-width: 48px;
    max-width: 48px;
    min-height: 48px;
    max-height: 48px;
    border: none;
}

QPushButton.server_btn:hover {
    background-color: #5865F2;
    color: #ffffff;
    border-radius: 16px;
}

QPushButton.server_btn_active {
    background-color: #5865F2;
    color: #ffffff;
    border-radius: 16px;
}

QPushButton.add_server_btn {
    background-color: #313338;
    color: #23a55a;
    border-radius: 24px;
    font-size: 22px;
    font-weight: bold;
    min-width: 48px;
    max-width: 48px;
    min-height: 48px;
    max-height: 48px;
    border: none;
}

QPushButton.add_server_btn:hover {
    background-color: #23a55a;
    color: #ffffff;
    border-radius: 16px;
}

/* Middle Sidebar: Channels & Friends */
#sidebar_widget {
    background-color: #2b2d31;
    border-top-left-radius: 8px;
}

QLabel.section_header {
    color: #949ba4;
    font-size: 11px;
    font-weight: bold;
    letter-spacing: 0.5px;
    padding-left: 8px;
    padding-top: 10px;
    padding-bottom: 4px;
}

QListWidget {
    background-color: transparent;
    border: none;
    outline: none;
}

QListWidget::item {
    color: #949ba4;
    padding: 7px 10px;
    border-radius: 4px;
    margin: 2px 6px;
}

QListWidget::item:hover {
    background-color: #35373c;
    color: #dbdee1;
}

QListWidget::item:selected {
    background-color: #404249;
    color: #ffffff;
}

/* User Profile Panel at bottom left */
#user_panel_widget {
    background-color: #232428;
    padding: 6px;
    border-top: 1px solid #1f2023;
}

QPushButton.icon_btn {
    background-color: transparent;
    border-radius: 4px;
    padding: 6px;
    font-size: 16px;
    border: none;
}

QPushButton.icon_btn:hover {
    background-color: #35373c;
}

QPushButton.icon_btn_active {
    background-color: #f23f43;
    color: #ffffff;
    border-radius: 4px;
    padding: 6px;
    font-size: 16px;
    border: none;
}

/* Center Content & Chat */
#chat_header {
    background-color: #313338;
    border-bottom: 1px solid #1f2023;
    min-height: 48px;
    max-height: 48px;
    padding: 0 16px;
}

QTextEdit#chat_history, QListWidget#chat_messages_list {
    background-color: #313338;
    border: none;
    color: #dbdee1;
    padding: 10px;
}

QLineEdit#chat_input {
    background-color: #383a40;
    color: #dbdee1;
    border: none;
    border-radius: 8px;
    padding: 10px 14px;
    font-size: 14px;
}

QLineEdit#chat_input:focus {
    background-color: #383a40;
    color: #ffffff;
}

QPushButton#send_btn {
    background-color: #5865F2;
    color: #ffffff;
    font-weight: bold;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
}

QPushButton#send_btn:hover {
    background-color: #4752c4;
}

/* Voice Call Active Widget */
#voice_status_card {
    background-color: #232428;
    border-bottom: 1px solid #1f2023;
    padding: 8px 12px;
}

QPushButton#disconnect_voice_btn {
    background-color: #f23f43;
    color: #ffffff;
    font-weight: bold;
    border: none;
    border-radius: 4px;
    padding: 6px 12px;
}

QPushButton#disconnect_voice_btn:hover {
    background-color: #da373c;
}

/* Call Overlay / Modal */
QDialog#incoming_call_dialog {
    background-color: #2b2d31;
    border: 2px solid #5865F2;
    border-radius: 12px;
}

QPushButton#call_accept_btn {
    background-color: #23a55a;
    color: #ffffff;
    font-size: 15px;
    font-weight: bold;
    border: none;
    border-radius: 6px;
    padding: 10px 20px;
}

QPushButton#call_accept_btn:hover {
    background-color: #1f9250;
}

QPushButton#call_decline_btn {
    background-color: #f23f43;
    color: #ffffff;
    font-size: 15px;
    font-weight: bold;
    border: none;
    border-radius: 6px;
    padding: 10px 20px;
}

QPushButton#call_decline_btn:hover {
    background-color: #da373c;
}

/* Standard Buttons & Inputs */
QPushButton.primary_btn {
    background-color: #5865F2;
    color: #ffffff;
    font-weight: bold;
    border: none;
    border-radius: 4px;
    padding: 8px 16px;
}

QPushButton.primary_btn:hover {
    background-color: #4752c4;
}

QPushButton.secondary_btn {
    background-color: #4e5058;
    color: #ffffff;
    border: none;
    border-radius: 4px;
    padding: 8px 16px;
}

QPushButton.secondary_btn:hover {
    background-color: #6d6f78;
}

QLineEdit, QComboBox, QSpinBox {
    background-color: #1e1f22;
    color: #dbdee1;
    border: 1px solid #3f4147;
    border-radius: 4px;
    padding: 6px 10px;
}

QLineEdit:focus, QComboBox:focus {
    border: 1px solid #5865F2;
}

/* Scrollbars */
QScrollBar:vertical {
    background: #2b2d31;
    width: 8px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background: #1a1b1e;
    min-height: 20px;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover {
    background: #111214;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
"""

AMOLED_THEME_QSS = """
/* AMOLED / Midnight Pure Black Theme */
QWidget {
    background-color: #000000;
    color: #e3e5e8;
    font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
    font-size: 14px;
    selection-background-color: #5865F2;
    selection-color: #ffffff;
}

QMainWindow, QDialog {
    background-color: #000000;
}

#server_nav_bar {
    background-color: #000000;
    border-right: 1px solid #141416;
    min-width: 72px;
    max-width: 72px;
}

QPushButton.server_btn {
    background-color: #0c0d0e;
    color: #dbdee1;
    border-radius: 24px;
    font-size: 16px;
    font-weight: bold;
    min-width: 48px;
    max-width: 48px;
    min-height: 48px;
    max-height: 48px;
    border: 1px solid #1f2024;
}

QPushButton.server_btn:hover, QPushButton.server_btn_active {
    background-color: #5865F2;
    color: #ffffff;
    border-radius: 16px;
}

QPushButton.add_server_btn {
    background-color: #0c0d0e;
    color: #23a55a;
    border-radius: 24px;
    font-size: 22px;
    font-weight: bold;
    min-width: 48px;
    max-width: 48px;
    min-height: 48px;
    max-height: 48px;
    border: 1px solid #1f2024;
}

QPushButton.add_server_btn:hover {
    background-color: #23a55a;
    color: #ffffff;
    border-radius: 16px;
}

#sidebar_widget {
    background-color: #08080a;
    border-right: 1px solid #141416;
}

QLabel.section_header {
    color: #8a8e94;
    font-size: 11px;
    font-weight: bold;
    padding-left: 8px;
    padding-top: 10px;
    padding-bottom: 4px;
}

QListWidget {
    background-color: transparent;
    border: none;
}

QListWidget::item {
    color: #8a8e94;
    padding: 7px 10px;
    border-radius: 4px;
    margin: 2px 6px;
}

QListWidget::item:hover {
    background-color: #141418;
    color: #ffffff;
}

QListWidget::item:selected {
    background-color: #202228;
    color: #ffffff;
    font-weight: bold;
}

#chat_header {
    background-color: #000000;
    border-bottom: 1px solid #141416;
}

#chat_history, QTextBrowser {
    background-color: #000000;
    color: #e3e5e8;
    border: none;
}

#chat_input, QLineEdit {
    background-color: #0c0d0e;
    color: #ffffff;
    border: 1px solid #202226;
    border-radius: 8px;
    padding: 8px 12px;
}

#chat_input:focus, QLineEdit:focus {
    border: 1px solid #5865F2;
}

#user_profile_bar {
    background-color: #040405;
    border-top: 1px solid #141416;
}

#voice_status_card {
    background-color: #0c0d0e;
    border: 1px solid #18191c;
}

QScrollBar:vertical {
    background: #000000;
    width: 8px;
}

QScrollBar::handle:vertical {
    background: #141418;
    border-radius: 4px;
}
"""

LIGHT_THEME_QSS = """
/* Light Theme */
QWidget {
    background-color: #ffffff;
    color: #2e3338;
    font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
    font-size: 14px;
    selection-background-color: #5865F2;
    selection-color: #ffffff;
}

QMainWindow, QDialog {
    background-color: #f2f3f5;
}

#server_nav_bar {
    background-color: #e3e5e8;
    min-width: 72px;
    max-width: 72px;
}

QPushButton.server_btn {
    background-color: #ffffff;
    color: #2e3338;
    border-radius: 24px;
    font-size: 16px;
    font-weight: bold;
    min-width: 48px;
    max-width: 48px;
    min-height: 48px;
    max-height: 48px;
    border: 1px solid #d1d3d6;
}

QPushButton.server_btn:hover, QPushButton.server_btn_active {
    background-color: #5865F2;
    color: #ffffff;
    border-radius: 16px;
}

QPushButton.add_server_btn {
    background-color: #ffffff;
    color: #23a55a;
    border-radius: 24px;
    font-size: 22px;
    font-weight: bold;
    min-width: 48px;
    max-width: 48px;
    min-height: 48px;
    max-height: 48px;
    border: 1px solid #d1d3d6;
}

QPushButton.add_server_btn:hover {
    background-color: #23a55a;
    color: #ffffff;
    border-radius: 16px;
}

#sidebar_widget {
    background-color: #f2f3f5;
    border-right: 1px solid #e3e5e8;
}

QLabel.section_header {
    color: #4e5058;
    font-size: 11px;
    font-weight: bold;
    padding-left: 8px;
    padding-top: 10px;
    padding-bottom: 4px;
}

QListWidget {
    background-color: transparent;
    border: none;
}

QListWidget::item {
    color: #4e5058;
    padding: 7px 10px;
    border-radius: 4px;
    margin: 2px 6px;
}

QListWidget::item:hover {
    background-color: #e0e2e5;
    color: #060607;
}

QListWidget::item:selected {
    background-color: #d1d4d8;
    color: #060607;
    font-weight: bold;
}

#chat_header {
    background-color: #ffffff;
    border-bottom: 1px solid #e3e5e8;
}

#chat_history, QTextBrowser {
    background-color: #ffffff;
    color: #2e3338;
    border: none;
}

#chat_input, QLineEdit {
    background-color: #ebedef;
    color: #060607;
    border: 1px solid #d1d3d6;
    border-radius: 8px;
    padding: 8px 12px;
}

#chat_input:focus, QLineEdit:focus {
    border: 1px solid #5865F2;
}

#user_profile_bar {
    background-color: #ebedef;
    border-top: 1px solid #d1d3d6;
}

#voice_status_card {
    background-color: #e3e5e8;
}

QScrollBar:vertical {
    background: #f2f3f5;
    width: 8px;
}

QScrollBar::handle:vertical {
    background: #c4c9ce;
    border-radius: 4px;
}
"""


def get_theme_qss(theme_name: str) -> str:
    """Returns the QSS stylesheet for the given theme name."""
    theme = (theme_name or "").lower()
    if "amoled" in theme or "midnight" in theme or "черн" in theme:
        return AMOLED_THEME_QSS
    elif "light" in theme or "светл" in theme:
        return LIGHT_THEME_QSS
    else:
        return DARK_THEME_QSS

