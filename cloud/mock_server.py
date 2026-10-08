"""Local stand-in for S3/CloudFront: serves media/ (HLS + sidecar tracks) and assets/ with CORS.

Usage: python cloud/mock_server.py [--port 8787] [--host 127.0.0.1] [--sidecar-latency-ms 0]

  http://localhost:8787/media/synth/hls/index.m3u8
  http://localhost:8787/media/synth/sidecar.json
  http://localhost:8787/assets/brands/brands.json

Use --host 0.0.0.0 when the Vega Virtual Device needs to reach this machine.
--sidecar-latency-ms delays sidecar responses to simulate a slow inference backend.
"""

from __future__ import annotations

import argparse
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALLOWED_PREFIXES = ("/media/", "/assets/")


class Handler(SimpleHTTPRequestHandler):
    sidecar_latency = 0.0

    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".m3u8": "application/vnd.apple.mpegurl",
        ".m4s": "video/iso.segment",
        ".mp4": "video/mp4",
        ".ts": "video/mp2t",
        ".json": "application/json",
    }

    def _allowed(self) -> bool:
        path = self.path.split("?", 1)[0]
        return path.startswith(ALLOWED_PREFIXES) and ".." not in path

    def do_GET(self) -> None:
        if not self._allowed():
            self.send_error(404)
            return
        if self.sidecar_latency and self.path.split("?", 1)[0].endswith("sidecar.json"):
            time.sleep(self.sidecar_latency)
        super().do_GET()

    def do_HEAD(self) -> None:
        if not self._allowed():
            self.send_error(404)
            return
        super().do_HEAD()

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.end_headers()

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Range")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--sidecar-latency-ms", type=float, default=0)
    args = ap.parse_args()

    Handler.sidecar_latency = args.sidecar_latency_ms / 1000
    server = ThreadingHTTPServer((args.host, args.port), partial(Handler, directory=str(ROOT)))
    print(f"serving {ROOT}/media and /assets on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
