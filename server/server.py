from http.server import HTTPServer, BaseHTTPRequestHandler
import os
import json
from urllib.parse import unquote
import mimetypes
import requests

HOST = 'localhost'
PORT = 8000

REPO_ROOT =       os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
INPUT_LIST_JSON = os.path.join(REPO_ROOT, 'source', 'input_papers.json')
CROSSREF_JSON =   os.path.join(REPO_ROOT, 'source',     'crossref.json')

class CustomHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Decode URL and get the full file path
        requested_path = unquote(self.path)
        if requested_path == '/':
            requested_path = '/index.html'

        file_path = os.path.abspath(os.path.join(REPO_ROOT, requested_path.strip('/')))

        # Security check: prevent access outside repo root
        if not file_path.startswith(REPO_ROOT):
            self.send_error(403, 'Forbidden')
            return

        # Serve static files
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
        if self.path == '/data':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')

            try:
                doi_list_from_frontend = json.loads(body)

                if not isinstance(doi_list_from_frontend, list):
                    self.send_error(400, "Expected a JSON array of DOIs.")
                    return

                # ---

                # Load existing Crossref entries
                crossref_entries = []
                if os.path.exists(CROSSREF_JSON):
                    with open(CROSSREF_JSON, 'r') as f:
                        crossref_entries = json.load(f)

                # Track DOIs already saved in metadata
                existing_crossref_dois = {entry.get("message", {}).get("DOI") for entry in crossref_entries if "message" in entry}

                # Fetch metadata for new DOIs not already present
                new_entries = []
                entries_errors = []
                for doi in doi_list_from_frontend:
                    if doi not in existing_crossref_dois:
                        try:
                            metadata = self.fetch_crossref_data(doi)
                            new_entries.append(metadata)
                        except Exception as e:
                            entries_errors.append({"error": str(e), "DOI": doi})
                
                # Append new entries to list
                crossref_entries.extend(new_entries)
                
                # Get DOIs of references
                references = []
                for doi in doi_list_from_frontend:
                    for entry in crossref_entries:
                        if "message" in entry:
                            if entry["message"]["DOI"].lower() == doi.lower():
                                for input_ref in entry["message"]["reference"]:
                                    if "DOI" in input_ref.keys():
                                        if input_ref["DOI"] not in references:
                                            references.append(input_ref["DOI"].lower())

                # Track DOIs already saved in metadata
                existing_crossref_dois = {entry.get("message", {}).get("DOI") for entry in crossref_entries if "message" in entry}

                # Fetch metadata for new DOIs not already present
                new_entries = []
                for doi in references:
                    if doi not in existing_crossref_dois:
                        try:
                            metadata = self.fetch_crossref_data(doi)
                            new_entries.append(metadata)
                        except Exception as e:
                            entries_errors.append({"error": str(e), "DOI": doi})
                
                # Append new entries to list
                crossref_entries.extend(new_entries)
                
                # Save
                with open(CROSSREF_JSON, 'w') as f:
                    json.dump(crossref_entries, f, indent=2)
                
                # Respond
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({
                    "status": "success",
                    "references_list": references,
                    "crossref_data": crossref_entries,
                    "crossref_errors": entries_errors,
                    "fetched_entries": len(new_entries)
                }).encode('utf-8'))

            except Exception as e:
                self.send_error(400, f"Invalid request: {e}")
        else:
            self.send_error(404, 'Path not found.')


    def fetch_crossref_data(self, doi):
        """Fetch data from Crossref API using the DOI"""
        url = f"https://api.crossref.org/works/{doi}"
        response = requests.get(url)

        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"Failed to fetch Crossref data for DOI: {doi}. Status code: {response.status_code}")

                
if __name__ == '__main__':
    server = HTTPServer((HOST, PORT), CustomHandler)
    print(f"Serving your repo at http://{HOST}:{PORT}")
    server.serve_forever()
