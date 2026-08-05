#!/usr/bin/env python3
"""
One-off migration: encrypt existing plaintext facebook_password values in SQLite DBs

Usage:
  FERNET_KEY=... python migrate_encrypt_passwords.py [--db test_app.db|integrated_dashboard.db]
If no --db is provided, migrates both known SQLite files when present.
"""
import os
import sys
import sqlite3
from cryptography.fernet import Fernet


def is_encrypted(value: str, cipher: Fernet) -> bool:
    if not value:
        return True
    try:
        cipher.decrypt(value.encode())
        return True
    except Exception:
        return False


def migrate_db(db_path: str, cipher: Fernet) -> int:
    if not os.path.exists(db_path):
        print(f"- Skipping: {db_path} not found")
        return 0
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        # Ensure users table exists with facebook_password column
        cur.execute("PRAGMA table_info(users)")
        cols = [r[1] for r in cur.fetchall()]
        if 'facebook_password' not in cols:
            print(f"- Skipping: users.facebook_password not found in {db_path}")
            return 0

        cur.execute("SELECT id, facebook_password FROM users")
        rows = cur.fetchall()
        updated = 0
        for user_id, fb_pass in rows:
            if fb_pass and not is_encrypted(fb_pass, cipher):
                enc = cipher.encrypt(fb_pass.encode()).decode()
                cur.execute("UPDATE users SET facebook_password = ? WHERE id = ?", (enc, user_id))
                updated += 1
        conn.commit()
        print(f"✓ {db_path}: encrypted {updated} record(s)")
        return updated
    finally:
        conn.close()


def main():
    key = os.environ.get('FERNET_KEY')
    if not key:
        print("ERROR: FERNET_KEY is required")
        sys.exit(1)
    cipher = Fernet(key.encode() if isinstance(key, str) else key)

    targets = []
    if len(sys.argv) > 1 and sys.argv[1] == '--db' and len(sys.argv) > 2:
        targets = [sys.argv[2]]
    else:
        # Default known DBs in this repo
        for name in ('test_app.db', 'integrated_dashboard.db'):
            if os.path.exists(name):
                targets.append(name)
    if not targets:
        print("No SQLite DBs found to migrate. Provide --db path if needed.")
        return

    total = 0
    for path in targets:
        total += migrate_db(path, cipher)
    print(f"Done. Total updated: {total}")


if __name__ == '__main__':
    main()



