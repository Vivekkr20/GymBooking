"""Vercel entry point for every /api/* request.

Vercel invokes this handler for each request; it does not run server.py's local
HTTP server. The rewrite adds _pulse_path so the existing API keeps its clean
/api/... URLs.
"""
from pathlib import Path
import sys
from urllib.parse import parse_qs, urlencode, urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from server import App, init_db  # noqa: E402


# Safe to call on each cold start: schema creation is idempotent, and the seed
# marker prevents duplicate demo data when concurrent functions initialize.
init_db()


class handler(App):
    def restore_api_path(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query, keep_blank_values=True)
        route = query.pop("_pulse_path", [None])[-1]
        if route is None:
            return
        rebuilt = "/api/" + route.lstrip("/")
        remaining_query = urlencode(query, doseq=True)
        self.path = rebuilt + ("?" + remaining_query if remaining_query else "")

    def do_GET(self):
        self.restore_api_path()
        super().do_GET()

    def do_POST(self):
        self.restore_api_path()
        super().do_POST()

    def do_DELETE(self):
        self.restore_api_path()
        super().do_DELETE()
