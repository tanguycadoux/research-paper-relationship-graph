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
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS authors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS publication_author (
            publication_id INTEGER,
            author_id INTEGER,
            author_order INTEGER,
            PRIMARY KEY (publication_id, author_id),
            FOREIGN KEY (publication_id) REFERENCES publications(id),
            FOREIGN KEY (author_id) REFERENCES authors(id)
        );
    ''')
    conn.commit()
    conn.close()

''' Fonctions pour publications '''

def insert_publication(doi, title, date):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO publications (doi, title, published, active)
        VALUES (?, ?, ?, 1)
    ''', (doi, title, date))
    publication_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return publication_id

def get_active_publications():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id, doi, title, published FROM publications WHERE active = 1')
    rows = cursor.fetchall()
    conn.close()

    publications = []
    for row in rows:
        publications.append({
            'id': row[0],
            'doi': row[1],
            'title': row[2],
            'published': row[3]
        })

    return publications

def get_publication_by_id(id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT doi, title, published FROM publications WHERE id = ?', (id,))
    row = cursor.fetchone()
    conn.close()

    publication = {
        'doi': row[0],
        'title': row[1],
        'published': row[2]
    }

    return publication

def is_doi_in_publication_table(doi):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT EXISTS (SELECT 1 FROM publications WHERE doi = ?)', (doi,))
    doi_exists = cursor.fetchone()
    conn.close()

    return doi_exists[0] == 1

''' Fonctions pour auteurs '''

def insert_author(name):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO authors (name)
        VALUES (?)
    ''', (name,))
    author_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return author_id

''' Fonctions pour lien publication auteurs '''

def link_author_to_publication(publication_id, author_id, order):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO publication_author (publication_id, author_id, author_order)
        VALUES (?, ?, ?)
    ''', (publication_id, author_id, order))
    conn.commit()
    conn.close()

def get_authors_by_publication_id(publication_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT a.name
        FROM authors a
        JOIN publication_author pa ON a.id = pa.author_id
        WHERE pa.publication_id = ?
        ORDER BY pa.author_order
    ''', (publication_id,))
    authors = cursor.fetchall()
    conn.close()

    return authors