from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from typing import Any

DB_PATH = os.environ.get("DB_PATH", "/data/plex-notify.db")
_lock = threading.Lock()

DEFAULT_SETTINGS: dict[str, Any] = {
    # idioma de la interfaz y de los avisos: es | en (valor inicial desde APP_LANG)
    "language": "en" if os.environ.get("APP_LANG", "").lower().startswith("en") else "es",
    "poll_seconds": 60,
    # espera sin nuevos ítems de la misma serie antes de notificar (agrupa los episodios de una subida)
    "quiet_seconds": 300,
    "sections": [],            # vacío = todas las bibliotecas de películas y series
    "notify_replacements": False,  # re-subida de un episodio ya notificado (mejor calidad, etc.)
    "max_episode_list": 8,
    "telegram": {"enabled": False, "bot_token": "", "chat_ids": "", "silent": False},
    "email": {"enabled": False, "host": "", "port": 587, "security": "starttls",
              "username": "", "password": "", "from": "", "to": "", "theme": "dark",
              "plex_users": [], "respect_access": True,
              "user_excludes": {}},
    "apprise": {"enabled": False, "urls": ""},
    # destinos solo para pruebas (pestaña Probar); nunca se usan en avisos reales
    "test": {"chat_id": "", "email": ""},
}


def conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    return c


def init() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with _lock, conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS seen (
            rating_key TEXT PRIMARY KEY,
            section TEXT, kind TEXT, group_key TEXT,
            show_guid TEXT, season_index INTEGER, episode_index INTEGER,
            added_at INTEGER, first_seen REAL, notification_id INTEGER
        );
        CREATE INDEX IF NOT EXISTS seen_pending ON seen(notification_id, group_key);
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created REAL, kind TEXT, headline TEXT, title TEXT,
            text TEXT, event TEXT, results TEXT
        );
        """)


def get_settings() -> dict:
    with conn() as c:
        rows = {r["key"]: json.loads(r["value"]) for r in c.execute("SELECT key, value FROM settings")}
    out = json.loads(json.dumps(DEFAULT_SETTINGS))
    for k, v in rows.items():
        if isinstance(out.get(k), dict) and isinstance(v, dict):
            out[k].update(v)
        else:
            out[k] = v
    return out


def save_settings(values: dict) -> None:
    with _lock, conn() as c:
        for k, v in values.items():
            c.execute("INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                      (k, json.dumps(v)))


def get_state(key: str, default: Any = None) -> Any:
    with conn() as c:
        r = c.execute("SELECT value FROM settings WHERE key=?", (f"_state.{key}",)).fetchone()
    return json.loads(r["value"]) if r else default


def set_state(key: str, value: Any) -> None:
    save_settings({f"_state.{key}": value})


def mark_seen(rows: list[dict]) -> int:
    """Inserta ítems nuevos; devuelve cuántos eran realmente nuevos."""
    n = 0
    with _lock, conn() as c:
        for r in rows:
            cur = c.execute("""INSERT OR IGNORE INTO seen(rating_key, section, kind, group_key, show_guid,
                               season_index, episode_index, added_at, first_seen, notification_id)
                               VALUES(:rating_key, :section, :kind, :group_key, :show_guid, :season_index,
                                      :episode_index, :added_at, :first_seen, :notification_id)""",
                            {"notification_id": None, "first_seen": time.time(), **r})
            n += cur.rowcount
    return n


def pending_groups() -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute("""
            SELECT group_key, kind, section, COUNT(*) n, MAX(first_seen) last_seen
            FROM seen WHERE notification_id IS NULL GROUP BY group_key""")]


def pending_items(group_key: str) -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM seen WHERE notification_id IS NULL AND group_key=?", (group_key,))]


def previously_notified(show_guid: str, season: int, episode: int, exclude_keys: list[str]) -> bool:
    if not show_guid or episode is None:
        return False
    q = ",".join("?" * len(exclude_keys)) or "''"
    with conn() as c:
        return c.execute(f"""SELECT 1 FROM seen WHERE show_guid=? AND season_index=? AND episode_index=?
                             AND notification_id IS NOT NULL AND rating_key NOT IN ({q}) LIMIT 1""",
                         (show_guid, season, episode, *exclude_keys)).fetchone() is not None


def add_notification(kind: str, headline: str, title: str, text: str, event: dict, results: list) -> int:
    with _lock, conn() as c:
        cur = c.execute("INSERT INTO notifications(created, kind, headline, title, text, event, results) VALUES(?,?,?,?,?,?,?)",
                        (time.time(), kind, headline, title, text, json.dumps(event, ensure_ascii=False),
                         json.dumps(results, ensure_ascii=False)))
        return cur.lastrowid


def assign(rating_keys: list[str], notification_id: int) -> None:
    with _lock, conn() as c:
        c.executemany("UPDATE seen SET notification_id=? WHERE rating_key=?",
                      [(notification_id, k) for k in rating_keys])


def drop_seen(rating_keys: list[str]) -> None:
    with _lock, conn() as c:
        c.executemany("DELETE FROM seen WHERE rating_key=?", [(k,) for k in rating_keys])


def list_notifications(limit: int = 100) -> list[dict]:
    with conn() as c:
        rows = c.execute("SELECT * FROM notifications ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["event"] = json.loads(d["event"])
        d["results"] = json.loads(d["results"] or "[]")
        out.append(d)
    return out


def get_notification(nid: int) -> dict | None:
    with conn() as c:
        r = c.execute("SELECT * FROM notifications WHERE id=?", (nid,)).fetchone()
    if not r:
        return None
    d = dict(r)
    d["event"] = json.loads(d["event"])
    d["results"] = json.loads(d["results"] or "[]")
    return d


def update_results(nid: int, results: list) -> None:
    with _lock, conn() as c:
        c.execute("UPDATE notifications SET results=? WHERE id=?", (json.dumps(results, ensure_ascii=False), nid))
