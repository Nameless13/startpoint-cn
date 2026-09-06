import sqlite3

db = sqlite3.connect(r'D:\Documents\startpoint_cn\.database\wdfp_data.db')
c = db.cursor()

# 插入几个基础角色给 testplayer (player_id=8)
# id 是角色ID（如111001），联合主键是(id, player_id)
chars = [
    (111001, 8, 1, 0, 0, 0, '2026-09-06 00:00:00', '2026-09-06 00:00:00', 0, 0, 0, None, None, None),
    (111002, 8, 1, 0, 0, 0, '2026-09-06 00:00:00', '2026-09-06 00:00:00', 0, 0, 0, None, None, None),
    (111003, 8, 1, 0, 0, 0, '2026-09-06 00:00:00', '2026-09-06 00:00:00', 0, 0, 0, None, None, None),
    (111004, 8, 1, 0, 0, 0, '2026-09-06 00:00:00', '2026-09-06 00:00:00', 0, 0, 0, None, None, None),
    (111005, 8, 1, 0, 0, 0, '2026-09-06 00:00:00', '2026-09-06 00:00:00', 0, 0, 0, None, None, None),
]

c.executemany(
    '''INSERT INTO players_characters
       (id, player_id, entry_count, evolution_level, over_limit_step, protection, join_time, update_time, exp, stack, mana_board_index, ex_boost_status_id, ex_boost_ability_id_list, illustration_settings)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
    chars
)
db.commit()
print(f'Inserted {len(chars)} characters for player 8')

# 验证
c.execute('SELECT id, entry_count, evolution_level FROM players_characters WHERE player_id=8')
for row in c.fetchall():
    print(f'  char_id={row[0]}, entry={row[1]}, evo={row[2]}')
db.close()
