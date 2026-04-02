import sqlite3
import os
from datetime import timedelta, datetime

db_path = os.path.join('instance', 'site.db')
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    offset = timedelta(hours=5, minutes=30)
    
    # Update Post timestamps
    cur.execute("SELECT id, timestamp FROM post")
    posts = cur.fetchall()
    for p in posts:
        try:
            dt = datetime.strptime(p[1], '%Y-%m-%d %H:%M:%S.%f')
            dt_new = dt + offset
            cur.execute("UPDATE post SET timestamp = ? WHERE id = ?", (dt_new, p[0]))
        except Exception:
            pass
            
    # Update Comment timestamps
    cur.execute("SELECT id, timestamp FROM comment")
    comments = cur.fetchall()
    for c in comments:
        try:
            dt = datetime.strptime(c[1], '%Y-%m-%d %H:%M:%S.%f')
            dt_new = dt + offset
            cur.execute("UPDATE comment SET timestamp = ? WHERE id = ?", (dt_new, c[0]))
        except Exception:
            pass
            
    conn.commit()
    print("Adjusted timestamps for existing data.")
    conn.close()
