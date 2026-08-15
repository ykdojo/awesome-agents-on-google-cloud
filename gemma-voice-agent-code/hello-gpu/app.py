"""Minimal Cloud Run GPU smoke test: say hello and report what the GPU looks like."""
import os
import shutil
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer


def gpu_report() -> str:
    candidates = ["nvidia-smi", "/usr/local/nvidia/bin/nvidia-smi", "/usr/bin/nvidia-smi"]
    for cand in candidates:
        path = shutil.which(cand) or (cand if os.path.isfile(cand) else None)
        if path:
            try:
                out = subprocess.run([path], capture_output=True, text=True, timeout=15)
                return out.stdout or out.stderr
            except Exception as e:  # noqa: BLE001
                return f"found {path} but running it failed: {e}"
    devices = sorted(d for d in os.listdir("/dev") if d.startswith("nvidia"))
    return "nvidia-smi not found on PATH. /dev nvidia devices: " + (", ".join(devices) or "none")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        body = f"hello from Cloud Run GPU\n\n{gpu_report()}\n".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    HTTPServer(("", port), Handler).serve_forever()
