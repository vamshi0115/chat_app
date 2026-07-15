# 💬 Oasis Chat

A real-time, multi-room chat application built with **Python + Flask-SocketIO** and a pure HTML/CSS/JS frontend. Covers the full Advanced tier of Task 5.

---

## Features

| Feature | Status |
|---|---|
| GUI web chat window (Flask-served SPA) | ✅ |
| User registration & login (username + password, SQLite) | ✅ |
| Multiple chat rooms — create or join named rooms | ✅ |
| Message history — past 50 messages loaded on join | ✅ |
| Desktop & in-app notifications for new messages | ✅ |
| Emoji shortcode rendering (`:smile:` → 😊, etc.) | ✅ |
| Security transparency documentation (this README) | ✅ |

---

## Quick Start

### 1 — Install dependencies

```bash
cd chat_app
pip install -r requirements.txt
```

### 2 — Run the server

```bash
python server.py
```

Open your browser at **http://localhost:5000**.

---

## Project Structure

```
chat_app/
├── server.py         # Flask + Flask-SocketIO application
├── database.py       # SQLite schema & helper functions
├── requirements.txt  # Python dependencies
├── chat.db           # SQLite database (auto-created on first run)
├── templates/
│   └── index.html    # Single-page frontend (HTML + CSS + JS)
└── README.md         # This file
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Web framework | Flask 2.x |
| Real-time transport | Flask-SocketIO 5.x + eventlet |
| Database | SQLite 3 (via Python `sqlite3` stdlib) |
| Password hashing | Werkzeug `generate_password_hash` (PBKDF2-SHA256) |
| Frontend | Vanilla HTML5 / CSS3 / JavaScript (ES2020) |
| Notifications | Browser Notification API |

---

## How Networking Works

The server uses **Flask-SocketIO** backed by **eventlet** for asynchronous concurrency.

- On connect, the browser opens a **WebSocket** (with HTTP long-polling as fallback via Socket.IO).
- Each chat room maps to a Socket.IO *room* — messages are broadcast only to members of that room using `emit(..., to=room_name)`.
- When a user joins a room the server emits the last 50 messages from SQLite so history is immediately visible.
- Room membership is ephemeral (Socket.IO sessions); the database stores only persistent data.

---

## 🔐 Security Transparency

This section is required reading for anyone deploying this application.

### What IS protected

| Mechanism | How |
|---|---|
| Passwords | Never stored in plaintext. Hashed with **PBKDF2-SHA256** (Werkzeug default, 260,000 iterations). Salted per user. |
| Session identity | Flask signed-cookie sessions (HMAC-SHA1). The `SECRET_KEY` must be changed for production. |
| Input validation | Username/password/room-name length and character checks on both client and server. |
| SQL injection | All database queries use parameterised statements (`?` placeholders via `sqlite3`). |
| XSS | All user-supplied content is HTML-escaped client-side before insertion into the DOM. |

### What is NOT protected (by design — be aware)

| Risk | Details |
|---|---|
| **No end-to-end encryption** | Messages are transmitted in plaintext over the WebSocket (or TLS if you add HTTPS). The server reads every message before saving it. |
| **Messages stored as plaintext** | The `messages` table in `chat.db` contains raw UTF-8 text. Anyone with filesystem access to `chat.db` can read all messages. |
| **No TLS out of the box** | Running with `python server.py` serves plain HTTP. In production, put the app behind **nginx** or **Caddy** with HTTPS to encrypt traffic in transit. |
| **SECRET_KEY in source** | The default `dev-secret-change-in-production` key is public. Set the `SECRET_KEY` environment variable before any non-local deployment. |
| **No rate limiting** | The login endpoint has no brute-force protection. For production, add Flask-Limiter. |
| **No message deletion / edit** | Stored messages are permanent until the database file is deleted. |
| **Single-server only** | Socket.IO rooms are in-process. Horizontal scaling requires a Redis message queue adapter. |

### Production hardening checklist

```bash
# 1. Set a strong secret key
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"

# 2. Run behind a reverse proxy with TLS (example: nginx + certbot)
# 3. Restrict database file permissions
chmod 600 chat.db

# 4. Install Flask-Limiter and add rate limits to /api/auth/login
# 5. Consider full-disk encryption for the host if message confidentiality matters
```

---

## Emoji Shortcodes Reference

| Shortcode | Emoji | | Shortcode | Emoji |
|---|---|---|---|---|
| `:smile:` | 😊 | | `:thumbsup:` | 👍 |
| `:laugh:` | 😂 | | `:fire:` | 🔥 |
| `:wink:` | 😉 | | `:rocket:` | 🚀 |
| `:heart:` | ❤️ | | `:tada:` | 🎉 |
| `:clap:` | 👏 | | `:thinking:` | 🤔 |
| `:wave:` | 👋 | | `:100:` | 💯 |
| `:star:` | ⭐ | | `:cry:` | 😢 |
| `:sunglasses:` | 😎 | | `:check:` | ✅ |
| `:coffee:` | ☕ | | `:pizza:` | 🍕 |
| `:rainbow:` | 🌈 | | `:warning:` | ⚠️ |

---

## Learning Resources

- [Python `socket` module docs](https://docs.python.org/3/library/socket.html)
- [Flask-SocketIO documentation](https://flask-socketio.readthedocs.io/)
- [Flask documentation](https://flask.palletsprojects.com/)


---

*Made with Python 🐍 — Oasis Chat — Task 5 Advanced Tier*
