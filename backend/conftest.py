import os
import socket
import sys
from pathlib import Path

BUNDLE = Path(__file__).resolve().parent.parent / "models" / "model_bundle"
os.environ.setdefault("MLPHIL_URL_BUNDLE", str(BUNDLE))

# url_v5_service loads the bundle on import, so its own tests cannot be collected without it.
collect_ignore = [] if BUNDLE.exists() else ["vendor/test_url_v5_service.py"]

if sys.platform == "win32":
    # On Windows every new asyncio loop builds its self-pipe with socket.socketpair(), a
    # loopback connect() in the stdlib, which the no-network fixtures would otherwise
    # report as egress. Only that call gets the real connect; all others stay blocked.
    _real_connect, _real_socketpair = socket.socket.connect, socket.socketpair

    def _socketpair(*args, **kwargs):
        patched = socket.socket.connect
        socket.socket.connect = _real_connect
        try:
            return _real_socketpair(*args, **kwargs)
        finally:
            socket.socket.connect = patched

    socket.socketpair = _socketpair
