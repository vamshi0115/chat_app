import sqlite3

conn = sqlite3.connect("chat.db")

cols = [r[1] for r in conn.execute("PRAGMA table_info(rooms)").fetchall()]
print("rooms columns before:", cols)

if "description" not in cols:
    conn.execute("ALTER TABLE rooms ADD COLUMN description TEXT NOT NULL DEFAULT ''")
    conn.commit()
    print("Migration done: added 'description' column to rooms")
else:
    print("Already up to date")

cols2 = [r[1] for r in conn.execute("PRAGMA table_info(rooms)").fetchall()]
print("rooms columns after:", cols2)
conn.close()
