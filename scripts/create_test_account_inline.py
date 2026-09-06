import sqlite3, bcrypt

db = sqlite3.connect(r'D:\Documents\startpoint_cn\.database\wdfp_data.db')
c = db.cursor()

c.execute('SELECT id FROM accounts WHERE username = ?', ('testplayer',))
if c.fetchone():
    print('账号已存在')
    db.close()
    exit()

h = bcrypt.hashpw(b'123456', bcrypt.gensalt()).decode()
now = '2024-01-01 00:00:00'

c.execute(
    'INSERT INTO accounts (app_id,first_login_time,idp_alias,idp_code,idp_id,reg_time,last_login_time,status,username,password_hash) VALUES (?,?,?,?,?,?,?,?,?,?)',
    ('test_app', now, 'test', 'test', 'test_idp', now, now, 'active', 'testplayer', h)
)
aid = c.lastrowid
print(f'创建账号: account_id={aid}')

# 获取 players 表的列数
c.execute('PRAGMA table_info(players)')
col_count = len(c.fetchall())
print(f'players 表共 {col_count} 列')

# NULL 用于 id 列，其余填默认值
vals = [None, aid, 10, now, 0, 0, 0, 0, 'TestPlayer', now, '', 0, 0, 0, 0, 0, 0, now, 1, 1, 1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, None, 0]
placeholders = ','.join(['?'] * len(vals))
c.execute(f'INSERT INTO players VALUES ({placeholders})', vals)
pid = c.lastrowid
print(f'创建角色: player_id={pid}')

db.commit()
db.close()
print('登录: testplayer / 123456')
