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
            is_a_user_source INTEGER
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
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS publication_reference (
            publication_id INTEGER,
            reference_id INTEGER,
            reference_order INTEGER,
            PRIMARY KEY (publication_id, reference_id),
            FOREIGN KEY (publication_id) REFERENCES publications(id),
            FOREIGN KEY (reference_id) REFERENCES publications(id)
        )
    ''')
    conn.commit()
    conn.close()

''' Fonctions pour publications '''

def insert_publication(doi, title, date, is_a_user_source):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT OR IGNORE INTO publications (doi, title, published, is_a_user_source)
            VALUES (?, ?, ?, ?)
        ''', (doi, title, date, is_a_user_source))
        conn.commit()
    except sqlite3.IntegrityError as e:
        print(f"IntegrityError for DOI {doi}: {e}")
    except Exception as e:
        print(f"Failed to insert {doi}: {e}")
    finally:
        conn.close()
    publication_id = cursor.lastrowid

    return publication_id

def get_user_publications():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id, doi, title, published FROM publications WHERE is_a_user_source = 1')
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

def get_user_publications_references():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''SELECT DISTINCT p2.id, p2.doi, p2.title, p2.published
                    FROM publication_reference pr
                    JOIN publications p1 ON pr.publication_id = p1.id
                    JOIN publications p2 ON pr.reference_id = p2.id
                    WHERE p1.is_a_user_source = 1
                    AND p2.is_a_user_source != 1;
                   ''')
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

''' Fonctions pour lien publication references '''

def link_reference_to_publication(publication_id, reference_id, order):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO publication_reference (publication_id, reference_id, reference_order)
        VALUES (?, ?, ?)
    ''', (publication_id, reference_id, order))
    conn.commit()
    conn.close()
