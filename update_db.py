import sqlite3
import os

db_path = os.path.join('instance', 'site.db')
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("ALTER TABLE like ADD COLUMN reaction_type VARCHAR(20) NOT NULL DEFAULT 'like'")
        conn.commit()
        print("Column added.")
    except Exception as e:
        print("Error:", e)
    conn.close()
