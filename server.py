"""
server.py — Flask + Flask-SocketIO backend for Oasis Chat.

Run locally (LAN access):
    python server.py

Expose publicly via ngrok (anyone on the internet can join):
    python server.py --ngrok

The server always binds to 0.0.0.0 so every device on the same
Wi-Fi/LAN can reach it at http://<your-local-ip>:5000.
The --ngrok flag creates a public HTTPS tunnel via pyngrok.
"""

import os
import re
import socket
import argparse
from functools import wraps

from flask import Flask, render_template, request, session, jsonify
from flask_socketio import SocketIO, join_room, leave_room, emit
from werkzeug.security import generate_password_hash, check_password_hash

import database as db

# ── App setup ──────────────────────────────────────────────────────────────

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")

socketio = SocketIO(
    app,
    async_mode="threading",
    cors_allowed_origins="*",
    logger=False,
    engineio_logger=False,
)

# ── Emoji shortcode map ────────────────────────────────────────────────────

EMOJI_MAP: dict[str, str] = {
    "smile":      "😊", "grin":       "😁", "laugh":      "😂",
    "wink":       "😉", "heart":      "❤️", "thumbsup":   "👍",
    "+1":         "👍", "thumbsdown": "👎", "-1":         "👎",
    "clap":       "👏", "fire":       "🔥", "100":        "💯",
    "rocket":     "🚀", "wave":       "👋", "thinking":   "🤔",
    "eyes":       "👀", "tada":       "🎉", "cry":        "😢",
    "angry":      "😠", "sunglasses": "😎", "star":       "⭐",
    "check":      "✅", "x":          "❌", "warning":    "⚠️",
    "question":   "❓", "zzz":        "💤", "coffee":     "☕",
    "pizza":      "🍕", "poop":       "💩", "rainbow":    "🌈",
}

_EMOJI_RE = re.compile(r":([a-zA-Z0-9_+\-]+):")


def render_emoji(text: str) -> str:
    return _EMOJI_RE.sub(lambda m: EMOJI_MAP.get(m.group(1), m.group(0)), text)


# ── Auth helpers ───────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "Not authenticated"}), 401
        return f(*args, **kwargs)
    return decorated


def current_user() -> dict | None:
    uid = session.get("user_id")
    if uid is None:
        return None
    row = db.get_user_by_id(uid)
    return dict(row) if row else None


# ── Socket.IO room key ─────────────────────────────────────────────────────
# We use the string "room:<id>" as the Socket.IO room key so that rooms with
# the same display-name don't collide.

def _sk(room_id: int) -> str:
    return f"room:{room_id}"


# ── HTTP routes ────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


# Auth ──────────────────────────────────────────────────────────────────────

@app.route("/api/auth/register", methods=["POST"])
def register():
    data = request.get_json(force=True)
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400
    if len(username) < 3 or len(username) > 20:
        return jsonify({"error": "Username must be 3–20 characters"}), 400
    if not re.match(r"^[a-zA-Z0-9_]+$", username):
        return jsonify({"error": "Username may only contain letters, numbers, and underscores"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400
    if db.get_user_by_username(username):
        return jsonify({"error": "Username already taken"}), 409

    pw_hash = generate_password_hash(password)
    user_id = db.create_user(username, pw_hash)
    session["user_id"] = user_id
    session["username"] = username
    return jsonify({"id": user_id, "username": username}), 201


@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json(force=True)
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()

    user = db.get_user_by_username(username)
    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Invalid username or password"}), 401

    session["user_id"] = user["id"]
    session["username"] = user["username"]
    return jsonify({"id": user["id"], "username": user["username"]})


@app.route("/api/auth/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/auth/me")
def me():
    user = current_user()
    if not user:
        return jsonify({"error": "Not authenticated"}), 401
    return jsonify({"id": user["id"], "username": user["username"]})


# Rooms ─────────────────────────────────────────────────────────────────────

@app.route("/api/rooms/my", methods=["GET"])
@login_required
def my_rooms():
    """Return rooms the current user has joined."""
    rooms = db.get_user_rooms(session["user_id"])
    return jsonify(rooms)


@app.route("/api/rooms/search", methods=["GET"])
@login_required
def search_rooms():
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify([])
    return jsonify(db.search_rooms(q))


@app.route("/api/rooms", methods=["POST"])
@login_required
def create_room():
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    description = (data.get("description") or "").strip()

    if not name:
        return jsonify({"error": "Room name is required"}), 400
    if len(name) < 2 or len(name) > 30:
        return jsonify({"error": "Room name must be 2–30 characters"}), 400
    if not re.match(r"^[a-zA-Z0-9 _\-]+$", name):
        return jsonify({"error": "Room name may only contain letters, numbers, spaces, hyphens, and underscores"}), 400
    if len(description) > 200:
        return jsonify({"error": "Description max 200 characters"}), 400

    room_id = db.create_room(name, description, session["user_id"])
    # Creator automatically joins their own room
    db.add_member(room_id, session["user_id"])
    room = db.get_room_by_id(room_id)
    return jsonify(room), 201


@app.route("/api/rooms/<int:room_id>", methods=["GET"])
@login_required
def get_room(room_id):
    room = db.get_room_by_id(room_id)
    if not room:
        return jsonify({"error": "Room not found"}), 404
    return jsonify(room)


@app.route("/api/rooms/<int:room_id>", methods=["PUT"])
@login_required
def update_room(room_id):
    """Only the room creator can edit name/description."""
    room = db.get_room_by_id(room_id)
    if not room:
        return jsonify({"error": "Room not found"}), 404
    if room["created_by"] != session["user_id"]:
        return jsonify({"error": "Only the room creator can edit this room"}), 403

    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    description = (data.get("description") or "").strip()

    if not name:
        return jsonify({"error": "Room name is required"}), 400
    if len(name) < 2 or len(name) > 30:
        return jsonify({"error": "Room name must be 2–30 characters"}), 400
    if not re.match(r"^[a-zA-Z0-9 _\-]+$", name):
        return jsonify({"error": "Room name may only contain letters, numbers, spaces, hyphens, and underscores"}), 400
    if len(description) > 200:
        return jsonify({"error": "Description max 200 characters"}), 400

    db.update_room(room_id, name, description)
    updated = db.get_room_by_id(room_id)

    # Broadcast the update to everyone in the room
    socketio.emit(
        "room_updated",
        updated,
        to=_sk(room_id),
    )
    return jsonify(updated)


@app.route("/api/rooms/<int:room_id>", methods=["DELETE"])
@login_required
def delete_room(room_id):
    """Only the room creator can delete the room."""
    room = db.get_room_by_id(room_id)
    if not room:
        return jsonify({"error": "Room not found"}), 404
    if room["created_by"] != session["user_id"]:
        return jsonify({"error": "Only the room creator can delete this room"}), 403

    # Notify everyone before deletion
    socketio.emit(
        "room_deleted",
        {"room_id": room_id, "name": room["name"]},
        to=_sk(room_id),
    )
    db.delete_room(room_id)
    return jsonify({"ok": True})


# ── Socket.IO events ───────────────────────────────────────────────────────

@socketio.on("connect")
def on_connect():
    if "user_id" not in session:
        return False


@socketio.on("join_room")
def on_join_room(data):
    room_id = (data or {}).get("room_id")
    if not room_id:
        return

    room = db.get_room_by_id(room_id)
    if not room:
        emit("error", {"message": "Room not found"})
        return

    # Persist membership
    db.add_member(room_id, session["user_id"])

    sk = _sk(room_id)
    join_room(sk)

    # Fresh member count after join
    member_count = db.get_member_count(room_id)

    # Send history only to joining user
    history = db.get_room_history(room_id)
    emit("room_history", {"room_id": room_id, "messages": history})

    # Broadcast updated member count to the whole room
    emit("member_count_update", {"room_id": room_id, "member_count": member_count}, to=sk)

    # System join announcement
    emit(
        "system_message",
        {"room_id": room_id, "text": f"{session['username']} joined the room"},
        to=sk,
    )


@socketio.on("leave_room")
def on_leave_room(data):
    room_id = (data or {}).get("room_id")
    if not room_id:
        return

    db.remove_member(room_id, session["user_id"])
    sk = _sk(room_id)
    leave_room(sk)

    member_count = db.get_member_count(room_id)
    emit("member_count_update", {"room_id": room_id, "member_count": member_count}, to=sk)

    emit(
        "system_message",
        {"room_id": room_id, "text": f"{session['username']} left the room"},
        to=sk,
    )


@socketio.on("send_message")
def on_send_message(data):
    room_id = (data or {}).get("room_id")
    content = (data or {}).get("content", "").strip()

    if not room_id or not content:
        return
    if len(content) > 2000:
        emit("error", {"message": "Message too long (max 2000 chars)"})
        return

    room = db.get_room_by_id(room_id)
    if not room:
        emit("error", {"message": "Room not found"})
        return

    content = render_emoji(content)
    meta = db.save_message(room_id, session["user_id"], content)

    emit(
        "new_message",
        {
            "room_id":    room_id,
            "username":   session["username"],
            "content":    content,
            "created_at": meta["created_at"],
            "id":         meta["id"],
        },
        to=_sk(room_id),
    )


# ── Entry point ────────────────────────────────────────────────────────────

def _local_ip() -> str:
    """Best-effort: return the machine's outbound LAN IP address."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def _start_cloudflared(port: int) -> str | None:
    """
    Start a Cloudflare Quick Tunnel (cloudflared tunnel --url).
    cloudflared is a single ~50 MB exe — no account or token needed.
    Returns the public https://xxxx.trycloudflare.com URL, or None on failure.
    """
    import subprocess, threading, time

    # Locate cloudflared on PATH or next to server.py
    import shutil
    exe = shutil.which("cloudflared") or os.path.join(
        os.path.dirname(__file__), "cloudflared.exe"
    )
    if not exe or not os.path.isfile(exe if os.path.isabs(exe) else shutil.which("cloudflared") or ""):
        # Try just the name — shutil.which already handled PATH
        exe = shutil.which("cloudflared")
    if not exe:
        # Last resort: check same directory as this script
        local = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cloudflared.exe")
        exe = local if os.path.isfile(local) else None
    if not exe:
        return None

    url_holder: list[str] = []

    def _run():
        try:
            proc = subprocess.Popen(
                [exe, "tunnel", "--url", f"http://localhost:{port}"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            for line in proc.stdout:
                if "trycloudflare.com" in line or "cloudflare.com/cdn-cgi" in line:
                    # Extract the URL from the log line
                    for token in line.split():
                        if "trycloudflare.com" in token or token.startswith("https://"):
                            url_holder.append(token.strip())
                            return
        except Exception:
            pass

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    # Wait up to 12 s for the URL to appear
    for _ in range(24):
        if url_holder:
            return url_holder[0]
        time.sleep(0.5)
    return None


def _start_localtunnel(port: int) -> str | None:
    """
    Start a localtunnel.me tunnel via npx (requires Node.js ≥ 14).
    No account, no binary download — uses the Node package directly.
    Returns the public URL or None on failure.
    """
    import subprocess, threading, time, shutil

    npx = shutil.which("npx")
    if not npx:
        return None

    url_holder: list[str] = []

    def _run():
        try:
            proc = subprocess.Popen(
                [npx, "--yes", "localtunnel", "--port", str(port)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            for line in proc.stdout:
                if "loca.lt" in line or "localtunnel" in line:
                    for token in line.split():
                        if token.startswith("https://"):
                            url_holder.append(token.strip())
                            return
        except Exception:
            pass

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    for _ in range(30):
        if url_holder:
            return url_holder[0]
        time.sleep(0.5)
    return None


def _start_localhost_run(port: int) -> None:
    """
    Start a localhost.run SSH tunnel in a background thread.
    Output goes directly to the terminal (not captured) so the URL
    prints naturally as SSH receives it — no buffering issues.
    """
    import subprocess, threading, shutil

    ssh = shutil.which("ssh")
    if not ssh:
        print("  [ssh] ssh not found on PATH.")
        return

    def _run():
        try:
            subprocess.run(
                [
                    ssh,
                    "-o", "StrictHostKeyChecking=no",
                    "-o", "ServerAliveInterval=30",
                    "-o", "ConnectTimeout=15",
                    "-R", f"80:localhost:{port}",
                    "nokey@localhost.run",
                ],
                # No stdout/stderr redirect — output goes straight to the terminal
            )
        except Exception as e:
            print(f"\n  [ssh] Tunnel exited: {e}")

    t = threading.Thread(target=_run, daemon=True)
    t.start()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Oasis Chat server")
    parser.add_argument(
        "--tunnel",
        choices=["ssh", "cloudflare", "localtunnel", "ngrok"],
        default=None,
        help=(
            "Create a public internet tunnel. "
            "ssh = localhost.run via built-in SSH — RECOMMENDED, zero install. "
            "cloudflare = Cloudflare Quick Tunnel (needs cloudflared.exe). "
            "localtunnel = localtunnel.me via npx (needs Node.js). "
            "ngrok = ngrok (needs free account + NGROK_AUTHTOKEN env var)."
        ),
    )
    parser.add_argument(
        "--port", type=int, default=5000, help="Port to listen on (default: 5000)"
    )
    args = parser.parse_args()

    db.init_db()

    lan_ip = _local_ip()
    port   = args.port

    print("=" * 57)
    print("  Oasis Chat")
    print("=" * 57)
    print(f"  Local : http://localhost:{port}")
    print(f"  LAN   : http://{lan_ip}:{port}  (same Wi-Fi / network)")

    if args.tunnel == "ssh":
        print("  Tunnel: connecting to localhost.run via SSH...")
        print("  The public URL will appear below once SSH handshake completes (~15s).")
        print("  It looks like:  https://xxxxxxxxxxxxxxxx.lhr.life")
        print("-" * 57)
        _start_localhost_run(port)

    elif args.tunnel == "cloudflare":
        print("  Tunnel: starting Cloudflare Quick Tunnel...")
        url = _start_cloudflared(port)
        if url:
            print(f"  Public: {url}  <- share this with anyone")
        else:
            print("  [cloudflare] cloudflared not found.")
            print("  Download: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/")
            print("  Place cloudflared.exe next to server.py and re-run.")

    elif args.tunnel == "localtunnel":
        print("  Tunnel: starting localtunnel (npx)...")
        url = _start_localtunnel(port)
        if url:
            print(f"  Public: {url}  <- share this with anyone")
        else:
            print("  [localtunnel] npx not found — install Node.js from https://nodejs.org")

    elif args.tunnel == "ngrok":
        try:
            from pyngrok import ngrok as _ngrok, conf as _conf
            token = os.environ.get("NGROK_AUTHTOKEN")
            if not token:
                print("  [ngrok] NGROK_AUTHTOKEN env var not set.")
                print("  Get your token: https://dashboard.ngrok.com/get-started/your-authtoken")
                print("  Then run:  $env:NGROK_AUTHTOKEN='your_token'  and retry.")
            else:
                _conf.get_default().auth_token = token
                _conf.get_default().request_timeout = 120
                tunnel = _ngrok.connect(port, "http")
                public_url = tunnel.public_url
                if public_url.startswith("http://"):
                    public_url = "https://" + public_url[len("http://"):]
                print(f"  Public: {public_url}  <- share this with anyone")
        except ImportError:
            print("  [ngrok] pyngrok not installed: pip install pyngrok")
        except Exception as exc:
            print(f"  [ngrok] {exc}")

    print("=" * 57)
    print("  Press Ctrl+C to stop.")
    print()

    socketio.run(app, host="0.0.0.0", port=port, debug=False)
