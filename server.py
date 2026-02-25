#!/usr/bin/env python3
import http.server
import socketserver
import json
import os
from urllib.parse import urlparse

PORT = 8080

class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.path = '/index.html'
        return super().do_GET()
    
    def do_POST(self):
        parsed = urlparse(self.path)
        
        if parsed.path == '/api/fetch-tweets':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            
            try:
                data = json.loads(body)
                print(f"Received: username={data.get('username')}, listId={data.get('listId')}")
                
                # Mock response for now
                response = {
                    "success": True,
                    "tweets": [
                        {
                            "name": "Tech Insider",
                            "username": "techinsider",
                            "text": "Breaking: New AI model achieves state-of-the-art results on multiple benchmarks. The model uses a novel architecture that reduces training time by 40%.",
                            "created_at": "2026-02-25T10:00:00Z",
                            "likes": 1234,
                            "retweets": 567,
                            "replies": 89
                        },
                        {
                            "name": "AI Research",
                            "username": "airesearch",
                            "text": "Just published our latest paper on efficient transformer architectures. Check it out! 📄🧠 #MachineLearning #AI",
                            "created_at": "2026-02-25T09:00:00Z",
                            "likes": 892,
                            "retweets": 234,
                            "replies": 45
                        }
                    ]
                }
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps(response).encode())
                
            except Exception as e:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def log_message(self, format, *args):
        print(f"[{self.log_date_time_string()}] {args[0]}")

os.chdir('/root/.openclaw/workspace/x_reader')

with socketserver.TCPServer(("0.0.0.0", PORT), Handler) as httpd:
    print(f"Server running at http://0.0.0.0:{PORT}/")
    httpd.serve_forever()
