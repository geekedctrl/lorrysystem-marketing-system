"""Optional localhost-only preview bridge for broken Docker Desktop/WSL port forwarding.

Forwards only to the fixed frontend HTTP listener inside a task-owned container.
No docker socket, API bearer tokens, arbitrary target URL or credentials are exposed.
"""

import argparse
import base64
import json
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REMOTE = """import base64,json,sys,urllib.request,urllib.error
v=json.load(sys.stdin)
r=urllib.request.Request('http://127.0.0.1:8080'+v['path'],data=base64.b64decode(v['body']) if v['body'] else None,headers=v['headers'],method=v['method'])
try: response=urllib.request.urlopen(r,timeout=25)
except urllib.error.HTTPError as e: response=e
print(json.dumps({'status':response.status,'headers':list(response.headers.items()),'body':base64.b64encode(response.read()).decode()}))
"""
HOP = {
    "connection",
    "transfer-encoding",
    "content-length",
    "host",
    "keep-alive",
    "upgrade",
    "proxy-authorization",
    "proxy-authenticate",
    "te",
    "trailer",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--container", default="native-acceptance-native-frontend-1")
    parser.add_argument("--port", type=int, default=8095)
    args = parser.parse_args()
    if not args.container.startswith("native-acceptance-"):
        raise SystemExit(
            "Only task-owned native-acceptance frontend containers are allowed"
        )

    class Gateway(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def forward(self):
            if not self.path.startswith("/") or self.path.startswith("//"):
                self.send_error(400)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 0 or length > 262144:
                    self.send_error(413)
                    return
                value = {
                    "method": self.command,
                    "path": self.path,
                    "headers": {
                        k: v for k, v in self.headers.items() if k.lower() not in HOP
                    },
                    "body": base64.b64encode(self.rfile.read(length)).decode(),
                }
                result = subprocess.run(
                    ["docker", "exec", "-i", args.container, "python", "-c", REMOTE],
                    input=json.dumps(value),
                    capture_output=True,
                    text=True,
                    timeout=35,
                )
                if result.returncode:
                    raise ValueError()
                response = json.loads(result.stdout)
                body = base64.b64decode(response["body"])
                self.send_response(response["status"])
                for key, value in response["headers"]:
                    if key.lower() not in HOP:
                        self.send_header(key, value)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (ValueError, subprocess.SubprocessError, OSError):
                self.send_error(503, "Native preview bridge unavailable")

        do_GET = do_POST = do_PUT = do_PATCH = forward

    print(f"Native preview: http://127.0.0.1:{args.port} (localhost only)", flush=True)
    ThreadingHTTPServer(("127.0.0.1", args.port), Gateway).serve_forever()


if __name__ == "__main__":
    main()
