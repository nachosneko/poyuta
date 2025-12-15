import sqlite3

# path to your database
db_path = r"database/poyuta.db"

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# add the 'hints' column
cursor.execute("ALTER TABLE quizzes ADD COLUMN hints TEXT;")

conn.commit()
conn.close()

print("Migration complete!")
