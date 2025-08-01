import sqlite3

DB_PATH = "server/publications.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS publications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doi TEXT UNIQUE,
            title TEXT,
            published DATE,
            active INTEGER
        )
    ''')
    conn.commit()
    conn.close()

def insert_publication(doi, title, date):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO publications (doi, title, published, active)
        VALUES (?, ?, ?, 1)
    ''', (doi, title, date))
    conn.commit()
    conn.close()

def get_active_publications():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT doi, title, published FROM publications WHERE active = 1')
    rows = cursor.fetchall()
    conn.close()

    publications = []
    for row in rows:
        publications.append({
            'doi': row[0],
            'title': row[1],
            'published': row[2]
        })

    return publications
