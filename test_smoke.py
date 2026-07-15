"""Smoke tests for the rewritten database + server."""
import sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(__file__))

import database as db
db.DB_PATH = os.path.join(os.path.dirname(__file__), "test_chat.db")
db.init_db()
print("DB init OK")

from werkzeug.security import generate_password_hash, check_password_hash

# -- Users
pw = generate_password_hash("pass123")
uid1 = db.create_user("alice", pw)
uid2 = db.create_user("bob",   pw)
print(f"Users created: alice={uid1}, bob={uid2}")

# -- Room creation (duplicate names allowed)
r1 = db.create_room("science", "All things science", uid1)
r2 = db.create_room("science", "Another science room", uid2)  # same name, different creator
assert r1 != r2, "Duplicate room IDs — should be different rows"
print(f"Duplicate room names allowed: r1={r1}, r2={r2}")

# -- Members
db.add_member(r1, uid1)
db.add_member(r1, uid2)
db.add_member(r2, uid2)
assert db.get_member_count(r1) == 2
assert db.get_member_count(r2) == 1
print(f"Member counts: r1={db.get_member_count(r1)}, r2={db.get_member_count(r2)}")

# -- get_room_by_id
room = db.get_room_by_id(r1)
assert room["name"] == "science"
assert room["member_count"] == 2
assert room["creator_name"] == "alice"
print(f"Room by id: {room['name']}, members={room['member_count']}, creator={room['creator_name']}")

# -- search
results = db.search_rooms("sci")
assert len(results) == 2
print(f"Search 'sci': {len(results)} results")

results2 = db.search_rooms("SCIENCE")
assert len(results2) == 2
print(f"Case-insensitive search 'SCIENCE': {len(results2)} results")

# -- user rooms
alice_rooms = db.get_user_rooms(uid1)
bob_rooms   = db.get_user_rooms(uid2)
assert len(alice_rooms) == 1
assert len(bob_rooms)   == 2
print(f"Alice rooms={len(alice_rooms)}, Bob rooms={len(bob_rooms)}")

# -- update room
db.update_room(r1, "physics", "Renamed room")
room_u = db.get_room_by_id(r1)
assert room_u["name"] == "physics"
print(f"Room updated: {room_u['name']}")

# -- remove member
db.remove_member(r1, uid2)
assert db.get_member_count(r1) == 1
print(f"After remove: r1 member count={db.get_member_count(r1)}")

# -- message save + history
msg = db.save_message(r1, uid1, "hello :smile:")
assert msg["id"] > 0
history = db.get_room_history(r1)
assert len(history) == 1 and history[0]["content"] == "hello :smile:"
print(f"Message saved and retrieved: {history[0]['content']}")

# -- emoji rendering
import server as srv
assert "😊" in srv.render_emoji(":smile:")
assert "🚀" in srv.render_emoji(":rocket:")
assert ":unknown:" in srv.render_emoji(":unknown:")
print("Emoji rendering OK")

# -- delete room (cascade deletes messages + members)
db.delete_room(r1)
assert db.get_room_by_id(r1) is None
print("Room delete OK (cascade)")

print("\n All smoke tests PASSED")

import sqlite3
try:
    c = sqlite3.connect(db.DB_PATH); c.close()
except Exception: pass
try:
    os.remove(db.DB_PATH)
    print("Cleaned up test_chat.db")
except PermissionError:
    print("(Cleanup skipped — file locked)")
