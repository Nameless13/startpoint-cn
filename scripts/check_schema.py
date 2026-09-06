import sqlite3

db = sqlite3.connect(r'D:\Documents\startpoint_cn\.database\wdfp_data.db')
c = db.cursor()

# 检查表结构
c.execute('SELECT sql FROM sqlite_master WHERE name="players_characters"')
print(c.fetchone()[0])
db.close()
