#!/usr/bin/env python3
"""
VimCord User & Database Administration Tool.
Usage:
    python manage_users.py list
    python manage_users.py add <username> <password>
    python manage_users.py passwd <username_or_id> <new_password>
    python manage_users.py delete <username_or_id>
    python manage_users.py stats
"""

import sys
import os
import argparse
from datetime import datetime

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from vimcord.server.db import Database


def get_db(path: str = "vimcord_data.db") -> Database:
    return Database(path)


def cmd_list(db: Database):
    users = db.get_all_users()
    print(f"\n{'='*70}")
    print(f"Всего пользователей в базе: {len(users)}")
    print(f"{'='*70}")
    print(f"{'User ID':<20} | {'Username':<18} | {'Статус':<12} | {'Дата регистрации'}")
    print(f"{'-'*70}")
    for u in users:
        created = datetime.fromtimestamp(u.get("created_at", 0)).strftime("%Y-%m-%d %H:%M") if u.get("created_at") else "—"
        print(f"{u['user_id']:<20} | {u['username']:<18} | {u.get('status_text', '—'):<12} | {created}")
    print(f"{'='*70}\n")


def cmd_add(db: Database, username: str, password: str):
    ok, msg, data = db.register_user(username, password)
    if ok:
        print(f"[УСПЕХ] Пользователь '{username}' успешно создан! User ID: {data['user_id']}")
    else:
        print(f"[ОШИБКА] Не удалось создать пользователя: {msg}")


def cmd_passwd(db: Database, identifier: str, new_pass: str):
    # Find user by id or username
    user = db.get_user_by_id(identifier)
    if not user:
        user = db.get_user_by_username(identifier)
    if not user:
        print(f"[ОШИБКА] Пользователь '{identifier}' не найден в базе данных.")
        return

    ok = db.admin_set_password(user["user_id"], new_pass)
    if ok:
        print(f"[УСПЕХ] Пароль для пользователя '{user['username']}' ({user['user_id']}) успешно изменен.")
    else:
        print(f"[ОШИБКА] Не удалось сменить пароль.")


def cmd_delete(db: Database, identifier: str):
    user = db.get_user_by_id(identifier)
    if not user:
        user = db.get_user_by_username(identifier)
    if not user:
        print(f"[ОШИБКА] Пользователь '{identifier}' не найден в базе данных.")
        return

    uid = user["user_id"]
    uname = user["username"]
    confirm = input(f"Вы действительно хотите удалить пользователя '{uname}' ({uid})? [y/N]: ").strip().lower()
    if confirm in ("y", "yes", "да"):
        db.delete_user(uid)
        print(f"[УСПЕХ] Пользователь '{uname}' успешно удален.")
    else:
        print("[ОТМЕНА] Удаление отменено.")


def cmd_stats(db: Database):
    with db._get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users")
        user_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM rooms")
        room_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM channels")
        channel_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM messages")
        msg_count = cur.fetchone()[0]

    print(f"\n{'='*40}")
    print(" Статистика сервера VimCord")
    print(f"{'='*40}")
    print(f" Зарегистрированных пользователей : {user_count}")
    print(f" Созданных серверов (комнат)     : {room_count}")
    print(f" Каналов                          : {channel_count}")
    print(f" Сообщений в истории             : {msg_count}")
    print(f"{'='*40}\n")


def main():
    parser = argparse.ArgumentParser(description="Управление пользователями и базой VimCord")
    parser.add_argument("--db", default="vimcord_data.db", help="Путь к файлу sqlite базы (по умолчанию vimcord_data.db)")
    subparsers = parser.add_subparsers(dest="command", help="Команда")

    subparsers.add_parser("list", help="Вывести список всех пользователей")

    add_p = subparsers.add_parser("add", help="Создать нового пользователя")
    add_p.add_argument("username", help="Логин")
    add_p.add_argument("password", help="Пароль")

    pass_p = subparsers.add_parser("passwd", help="Сменить пароль пользователя")
    pass_p.add_argument("user", help="Логин или user_id")
    pass_p.add_argument("new_password", help="Новый пароль")

    del_p = subparsers.add_parser("delete", help="Удалить пользователя")
    del_p.add_argument("user", help="Логин или user_id")

    subparsers.add_parser("stats", help="Показать статистику сервера")

    args = parser.parse_args()
    db = get_db(args.db)

    if args.command == "list":
        cmd_list(db)
    elif args.command == "add":
        cmd_add(db, args.username, args.password)
    elif args.command == "passwd":
        cmd_passwd(db, args.user, args.new_password)
    elif args.command == "delete":
        cmd_delete(db, args.user)
    elif args.command == "stats":
        cmd_stats(db)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
