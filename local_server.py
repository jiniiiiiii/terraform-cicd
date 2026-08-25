import os
import sys
import json
from http.server import HTTPServer, BaseHTTPRequestHandler

# Add the backend directory to Python path so we can import the lambda function
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(BASE_DIR, 'backend'))

try:
    from lambda_function import lambda_handler
except ImportError as e:
    print(f"Error importing lambda_handler: {e}")
    sys.exit(1)

class LocalLambdaServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self._route()

    def do_POST(self):
        self._route()

    def do_OPTIONS(self):
        self._route()

    def _route(self):
        # 1. Serve frontend static file
        if self.path == '/' or self.path == '/index.html':
            frontend_path = os.path.join(BASE_DIR, 'frontend', 'index.html')
            if os.path.exists(frontend_path):
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                with open(frontend_path, 'rb') as f:
                    self.wfile.write(f.read())
            else:
                self.send_error(404, "Frontend file not found")
            return

        # 2. Serve API requests via Lambda Simulation
        if self.path.startswith('/api/'):
            # Read request body if content-length is set
            content_length = int(self.headers.get('Content-Length', 0))
            body_content = ""
            if content_length > 0:
                body_content = self.rfile.read(content_length).decode('utf-8')

            # Build simulated Lambda event
            event = {
                "path": self.path,
                "httpMethod": self.command,
                "headers": {k.lower(): v for k, v in self.headers.items()},
                "body": body_content,
                "isBase64Encoded": False
            }

            # Run the lambda handler
            try:
                response = lambda_handler(event, None)
                
                # Send HTTP response
                status_code = response.get('statusCode', 500)
                self.send_response(status_code)
                
                # Write response headers
                headers = response.get('headers', {})
                for k, v in headers.items():
                    # Content-Length is managed by http.server; filter it to prevent duplicates
                    if k.lower() != 'content-length':
                        self.send_header(k, v)
                self.end_headers()
                
                # Write response body
                body = response.get('body', '{}')
                self.wfile.write(body.encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": f"Local simulation error: {str(e)}"}).encode('utf-8'))
            return

        # 3. Path not matched
        self.send_error(404, "Not Found")

def run(port=8000):
    server_address = ('', port)
    httpd = HTTPServer(server_address, LocalLambdaServer)
    print(f"============================================================")
    print(f"Local Lambda Simulation Server started on http://localhost:{port}")
    print(f"Serving Frontend from: {os.path.join(BASE_DIR, 'frontend')}")
    print(f"SQLite Database file: {os.path.join(BASE_DIR, 'lambda_app.db')}")
    print(f"============================================================")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
        httpd.server_close()

if __name__ == '__main__':
    port = 8000
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass
    run(port)
