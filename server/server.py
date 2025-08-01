from http.server import HTTPServer, BaseHTTPRequestHandler
import os
import json
from urllib.parse import unquote
import mimetypes
import requests
import database as db
from datetime import date
from urllib.parse import urlparse, parse_qs

HOST = 'localhost'
PORT = 8000

REPO_ROOT =       os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
INPUT_LIST_JSON = os.path.join(REPO_ROOT, 'source', 'input_papers.json')
CROSSREF_JSON =   os.path.join(REPO_ROOT, 'source',     'crossref.json')

class CustomHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        query_params = parse_qs(parsed_url.query)

        # API routing
        self.routes = {
            '/get_publications': self.handle_get_active_publications,
        }

        if path in self.routes:
            handler = self.routes[path]
            handler(query_params)
            return
        
        # Static serving
        requested_path = unquote(path)
        if requested_path == '/':
            requested_path = '/index.html'

        file_path = os.path.abspath(os.path.join(REPO_ROOT, requested_path.strip('/')))

        if not file_path.startswith(REPO_ROOT):
            self.send_error(403, 'Forbidden')
            return

        if os.path.exists(file_path) and os.path.isfile(file_path):
            self.send_response(200)
            mime_type, _ = mimetypes.guess_type(file_path)
            self.send_header('Content-Type', mime_type or 'application/octet-stream')
            self.end_headers()
            with open(file_path, 'rb') as f:
                self.wfile.write(f.read())
        else:
            self.send_error(404, f'File not found: {requested_path}')
    
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8')

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self.send_error(400, 'Invalid JSON')
            return
        
        self.routes = {
            '/add_publication': self.handle_add_publication,
        }

        handler = self.routes.get(self.path)
        if handler:
            handler(data)
        else:
            self.send_error(404, 'Path not found.')

    def fetch_crossref_data(self, doi):
        url = f"https://api.crossref.org/works/{doi}"
        response = requests.get(url)

        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"Failed to fetch Crossref data for DOI: {doi}. Status code: {response.status_code}")

    def handle_add_publication(self, data):
        db.init_db()
        doi = data['doi']

        try:
            crossref_data = self.fetch_crossref_data(doi)

            message = crossref_data['message']
            title = message['title'][0]
            date = parse_crossref_date(message)

            try:
                db.insert_publication(doi, title, date)
            except:
                self.send_error(500, 'Error while updating database')
                return

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            response = {'status': 'success', 'message': 'Publication stored', 'DOI': doi, 'Crossref message': message}
            self.wfile.write(json.dumps(response).encode())
        except:
            self.send_error(502, 'Failed to fetch Crossref data')
            return

    def handle_get_active_publications(self, params):
        try:
            publications = db.get_active_publications()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(publications).encode())
        except Exception as e:
            self.send_error(500, f'Error while retrieving publications: {str(e)}')


def parse_crossref_date(item):
    parts = item['published']['date-parts'][0]

    year = parts[0]
    month = parts[1] if len(parts) > 1 else 1
    day = parts[2] if len(parts) > 2 else 1

    return date(year, month, day).isoformat()

                
if __name__ == '__main__':
    server = HTTPServer((HOST, PORT), CustomHandler)
    print(f"Serving your repo at http://{HOST}:{PORT}")
    server.serve_forever()
