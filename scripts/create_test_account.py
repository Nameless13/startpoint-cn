#!/usr/bin/env python3
"""创建游戏登录测试账号。

用法:
    python scripts/create_test_account.py

会插入:
    - accounts: testplayer / 123456 (bcrypt 哈希)
    - players: 关联到该 account，名字 TestPlayer
"""

import sqlite3
import sys
from pathlib import Path

try:
    import bcrypt
except ImportError:
    print("需要 bcrypt 库: pip install bcrypt")
    sys.exit(1)

DB_PATH = Path(".database/wdfp_data.db")


def main():
    if not DB_PATH.exists():
        print(f"数据库不存在: {DB_PATH}")
        print("请先启动服务器以初始化数据库")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    # 检查是否已存在
    cursor.execute("SELECT id FROM accounts WHERE username = ?", ("testplayer",))
    if cursor.fetchone():
        print("测试账号已存在，跳过创建")
        conn.close()
        return

    # 生成 bcrypt 哈希
    password = "123456"
    hash_bytes = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    hash_str = hash_bytes.decode()

    now = "2024-01-01 00:00:00"

    # 插入账号
    cursor.execute("""
        INSERT INTO accounts
            (app_id, first_login_time, idp_alias, idp_code, idp_id,
             reg_time, last_login_time, status, username, password_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "test_app", now, "test", "test", "test_idp",
        now, now, "active",
        "testplayer", hash_str
    ))
    account_id = cursor.lastrowid
    print(f"创建账号: id={account_id}, username=testplayer, password=123456")

    # 插入角色
    cursor.execute("""
        INSERT INTO players
            (account_id, stamina, stamina_heal_time, boost_point, boss_boost_point,
             transition_state, role, name, last_login_time, comment,
             vmoney, free_vmoney, rank_point, star_crumb, bond_token, exp_pool,
             exp_pooled_time, leader_character_id, party_slot,
             degree_id, birth, free_mana, paid_mana, enable_auto_3x,
             total_stamina_used, total_powerflips, total_dashes,
             total_mana_obtained, max_combo_achieved, total_login_days,
             tutorial_step, tutorial_skip_flag)
        VALUES (?, 10, 0, 0, 0,
                0, 0, 'TestPlayer', ?, '',
                0, 0, 0, 0, 0, 0,
                ?, 1, 1,
                1, 0, 0, 0, 1,
                0, 0, 0,
                0, 0, 0,
                0, 0)
    """, (account_id, now, now))
    player_id = cursor.lastrowid
    print(f"创建角色: id={player_id}, account_id={account_id}")

    conn.commit()
    conn.close()
    print("\n登录测试:")
    print(f"  curl -X POST http://127.0.0.1:8001/api/v2/game/login \\")
    print('    -H "Content-Type: application/json" \\')
    print('    -d \'{"username":"testplayer","password":"123456"}\'')


if __name__ == "__main__":
    main()
