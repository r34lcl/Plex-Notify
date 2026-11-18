from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time
from urllib.parse import quote
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response

from . import analyzer, db, render
from .plex import PlexClient
from .worker import Worker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
PLEX_URL = os.environ.get("PLEX_URL", "http://host.docker.internal:32400")
PLEX_TOKEN = os.environ["PLEX_TOKEN"]
APP_USER = os.environ.get("APP_USER", "admin")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")
SECRET_FIELDS = {("telegram", "bot_token"), ("email", "password")}
MASK = "••••••••"
STATIC = os.path.join(os.path.dirname(__file__), "static")

plex = PlexClient(PLEX_URL, PLEX_TOKEN)
worker = Worker(plex)


@asynccontextmanager
async def lifespan(_app):
    db.init()
    task = asyncio.create_task(worker.run())
    yield
    task.cancel()


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)


# ---------------- autenticación: login web con cookie de sesión firmada ----------------
SESSION_COOKIE = "pn_session"
PUBLIC_PATHS = {"/health", "/login", "/api/login", "/favicon.ico"}
_fails: dict[str, list[float]] = {}   # ip -> intentos fallidos recientes
MAX_FAILS, LOCK_SECONDS = 5, 300


def _secret() -> bytes:
    sec = db.get_state("session_secret")
    if not sec:
        sec = secrets.token_hex(32)
        db.set_state("session_secret", sec)
    # incluir la contraseña: si cambia en .env, todas las sesiones abiertas dejan de valer
    return (sec + APP_PASSWORD).encode()


def _sign(user: str, exp: int) -> str:
    sig = hmac.new(_secret(), f"{user}|{exp}".encode(), hashlib.sha256).hexdigest()
    return f"{user}|{exp}|{sig}"


def _valid_session(token: str | None) -> bool:
    try:
        user, exp, sig = (token or "").rsplit("|", 2)
        good = hmac.new(_secret(), f"{user}|{exp}".encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, good) and int(exp) > time.time() and user == APP_USER
    except ValueError:
        return False


def _basic_ok(request: Request) -> bool:
    """Se sigue aceptando Basic Auth para scripts / curl (sin mostrar la ventana del navegador)."""
    h = request.headers.get("authorization", "")
    if not h.startswith("Basic "):
        return False
    try:
        u, _, p = base64.b64decode(h[6:]).decode().partition(":")
    except Exception:  # noqa: BLE001
        return False
    return secrets.compare_digest(u, APP_USER) and secrets.compare_digest(p, APP_PASSWORD)


def _client_ip(request: Request) -> str:
    return (request.headers.get("x-forwarded-for", "").split(",")[0].strip()
            or (request.client.host if request.client else "?"))


@app.middleware("http")
async def auth(request: Request, call_next):
    path = request.url.path
    if (not APP_PASSWORD or path in PUBLIC_PATHS
            or _valid_session(request.cookies.get(SESSION_COOKIE)) or _basic_ok(request)):
        return await call_next(request)
    if path.startswith("/api/"):
        return JSONResponse({"detail": "no autenticado"}, status_code=401)
    return RedirectResponse("/login", status_code=303)


@app.get("/login")
async def login_page(request: Request):
    if not APP_PASSWORD or _valid_session(request.cookies.get(SESSION_COOKIE)):
        return RedirectResponse("/", status_code=303)
    return FileResponse(os.path.join(STATIC, "login.html"))


@app.post("/api/login")
async def login(request: Request, body: dict):
    ip, now = _client_ip(request), time.time()
    recent = [t for t in _fails.get(ip, []) if now - t < LOCK_SECONDS]
    _fails[ip] = recent
    if len(recent) >= MAX_FAILS:
        wait = int(LOCK_SECONDS - (now - recent[0]))
        raise HTTPException(429, f"Demasiados intentos. Espera {max(1, wait // 60)} min.")
    user, pw = str(body.get("username", "")), str(body.get("password", ""))
    if not (secrets.compare_digest(user, APP_USER) and secrets.compare_digest(pw, APP_PASSWORD)):
        _fails[ip].append(now)
        logging.warning("login fallido desde %s (usuario %r)", ip, user[:40])
        await asyncio.sleep(1)  # frena intentos automáticos
        left = MAX_FAILS - len(_fails[ip])
        raise HTTPException(401, "Usuario o contraseña incorrectos"
                            + (" (queda 1 intento)" if left == 1 else f" (quedan {left} intentos)" if left == 2
                               else ". Acceso bloqueado por 5 min" if left == 0 else ""))
    _fails.pop(ip, None)
    remember = bool(body.get("remember"))
    max_age = 30 * 86400 if remember else 12 * 3600
    resp = JSONResponse({"ok": True})
    https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    resp.set_cookie(SESSION_COOKIE, _sign(user, int(now + max_age)), max_age=max_age if remember else None,
                    httponly=True, samesite="lax", secure=https, path="/")
    return resp


@app.post("/api/logout")
async def logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(SESSION_COOKIE, path="/")
    return resp


@app.get("/health")
async def health():
    return {"ok": True}


@app.get("/")
async def index():
    return FileResponse(os.path.join(STATIC, "index.html"))


@app.get("/api/status")
async def status():
    try:
        info = await plex.server_info()
        plex_ok = {"ok": True, "name": info.get("friendlyName"), "version": info.get("version")}
    except Exception as e:  # noqa: BLE001
        plex_ok = {"ok": False, "error": str(e)}
    s = db.get_settings()
    return {"plex": plex_ok, "last_poll": worker.last_poll, "last_error": worker.last_error,
            "pending": db.pending_groups(), "now": time.time(), "quiet_seconds": s["quiet_seconds"],
            "channels": {k: s[k]["enabled"] for k in ("telegram", "email", "apprise")}}


def _masked(s: dict) -> dict:
    s = {k: v for k, v in s.items() if not k.startswith("_state.")}
    for sec, f in SECRET_FIELDS:
        if s[sec].get(f):
            s[sec][f] = MASK
    return s


@app.get("/api/settings")
async def get_settings():
    return _masked(db.get_settings())


@app.put("/api/settings")
async def put_settings(body: dict):
    cur = db.get_settings()
    allowed = {k for k in db.DEFAULT_SETTINGS}
    out = {}
    for k, v in body.items():
        if k not in allowed:
            continue
        if isinstance(v, dict):
            v = {**cur[k], **v}
            for sec, f in SECRET_FIELDS:
                if sec == k and v.get(f) == MASK:
                    v[f] = cur[k].get(f, "")
        out[k] = v
    for k in ("poll_seconds", "quiet_seconds", "max_episode_list"):
        if k in out:
            out[k] = max(10 if k != "max_episode_list" else 1, int(out[k]))
    db.save_settings(out)
    worker.wake()
    return _masked(db.get_settings())


@app.get("/api/sections")
async def sections():
    return [{"key": s["key"], "title": s["title"], "type": s["type"]}
            for s in await plex.sections() if s["type"] in ("movie", "show")]


@app.get("/api/plex-users")
async def plex_users(refresh: bool = False):
    error = None
    users = db.get_state("plex_users") or []
    if refresh or not users:
        try:
            users = await worker.refresh_users()
        except Exception as e:  # noqa: BLE001
            logging.warning("no se pudo consultar plex.tv: %s: %s", type(e).__name__, e)
            error = f"No se pudo conectar con plex.tv ({type(e).__name__}: {e or 'sin detalle'}). " \
                    "Revisa que el contenedor tenga salida a internet / DNS."
    return {"users": users, "updated": db.get_state("plex_users_at"), "error": error}


@app.get("/api/notifications")
async def notifications(limit: int = 100):
    return db.list_notifications(limit)


@app.get("/api/recent")
async def recent():
    """Últimas subidas reales agrupadas como lo haría el detector (para vista previa / prueba)."""
    groups: dict[str, dict] = {}
    for s in await plex.sections():
        if s["type"] not in ("movie", "show"):
            continue
        ptype = 1 if s["type"] == "movie" else 4
        for it in await plex.recent(s["key"], ptype, 80 if ptype == 4 else 15):
            if ptype == 1:
                gk, title = f"movie:{it['ratingKey']}", f"{it['title']} ({it.get('year', '')})"
            else:
                # agrupar por serie + "tanda" (mismo minuto de addedAt aprox) para imitar una subida
                gk = f"show:{it['grandparentRatingKey']}:{it.get('addedAt', 0) // 900}"
                title = it.get("grandparentTitle")
            g = groups.setdefault(gk, {"group": gk, "kind": "movie" if ptype == 1 else "episode", "title": title,
                                       "library": s["title"], "added_at": it.get("addedAt", 0), "items": []})
            g["items"].append({"rating_key": it["ratingKey"], "season_index": it.get("parentIndex"),
                               "episode_index": it.get("index")})
    out = sorted(groups.values(), key=lambda g: -g["added_at"])[:40]
    for g in out:
        g["count"] = len(g["items"])
    return out


async def _event_from(body: dict) -> dict:
    settings = db.get_settings()
    settings["notify_replacements"] = True
    if body["kind"] == "movie":
        ev = await analyzer.build_movie_event(plex, body["items"][0]["rating_key"])
    else:
        show_key = body["group"].split(":")[1]
        ev = await analyzer.build_show_event(plex, show_key, body["items"], settings)
    if not ev:
        raise HTTPException(404, "no se pudo armar el evento")
    return ev


@app.post("/api/preview")
async def preview(body: dict):
    ev = await _event_from(body)
    msg = render.build(ev, db.get_settings()["max_episode_list"])
    poster = "/api/thumb?path=" + quote(msg["thumb"]) if msg["thumb"] else None
    return {"event": ev, "telegram": render.telegram_html(msg, 1024), "text": render.plain_text(msg),
            "thumb": msg["thumb"], "email_theme": db.get_settings()["email"].get("theme", "dark"),
            "email": {th: render.email_html(msg, None, th, poster) for th in ("light", "dark", "auto")}}


TG_CHAT = re.compile(r"^(-?\d{3,20}|@[A-Za-z][A-Za-z0-9_]{4,31})$")
EMAIL = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")


@app.post("/api/send")
async def send(body: dict):
    """Envío real a la configuración (channel opcional) o, con `test`, SOLO a los destinos de prueba."""
    ev = await _event_from(body)
    settings = db.get_settings()
    test = body.get("test")
    if not test:
        nid = await worker.send_event(ev, settings, only=body.get("channel"))
        return db.get_notification(nid)

    chat = str(test.get("chat_id") or "").strip()
    mail = str(test.get("email") or "").strip()
    channels = [c for c in test.get("channels", []) if c in ("telegram", "email")]
    if "telegram" in channels and not TG_CHAT.match(chat):
        raise HTTPException(400, "Chat ID de Telegram inválido (ej. 123456789, -1001234567890 o @canal)")
    if "email" in channels and not EMAIL.match(mail):
        raise HTTPException(400, "Correo de prueba inválido")
    if not channels:
        raise HTTPException(400, "Elige al menos un destino de prueba")
    # recordar los destinos de prueba
    db.save_settings({"test": {"chat_id": chat, "email": mail}})

    results, msg = [], None
    for ch in channels:
        st = json.loads(json.dumps(settings))
        if ch == "telegram":
            if not st["telegram"].get("bot_token"):
                results.append({"channel": "telegram", "target": chat, "ok": False,
                                "error": "falta el bot token en Configuración → Telegram"})
                continue
            st["telegram"]["chat_ids"] = chat
        else:
            # solo esa dirección: sin usuarios de Plex ni direcciones adicionales
            st["email"] = {**st["email"], "to": mail, "plex_users": [], "user_excludes": {}}
        msg, res = await worker.deliver(ev, st, only=ch)
        results += res
    for r in results:
        r["test"] = True
    msg = msg or render.build(ev, settings["max_episode_list"])
    nid = db.add_notification(ev["kind"], msg["headline"], msg["title"], render.plain_text(msg), ev, results)
    return db.get_notification(nid)


@app.post("/api/retry/{nid}")
async def retry_failed(nid: int):
    """Reenvía SOLO a los destinos que fallaron (sin duplicar a quienes ya lo recibieron)."""
    n = db.get_notification(nid)
    if not n:
        raise HTTPException(404)
    failed = [r for r in n["results"] if not r["ok"] and not r.get("skipped")]
    if not failed:
        return n
    settings = db.get_settings()
    users = {u["username"]: u.get("email") for u in db.get_state("plex_users", [])}
    new_results = []
    for ch in dict.fromkeys(r["channel"] for r in failed):
        st = json.loads(json.dumps(settings))
        rs = [r for r in failed if r["channel"] == ch]
        if ch == "telegram":
            chats = [r["target"] for r in rs if r.get("target")]
            if chats:
                st["telegram"]["chat_ids"] = ",".join(chats)
        elif ch == "email":
            addrs = []
            for r in rs:
                addrs += r.get("targets") or [r.get("address") or users.get(r.get("target")) or r.get("target")]
            addrs = [a for a in addrs if a and "@" in a]
            if not addrs:
                continue
            st["email"] = {**st["email"], "to": ",".join(dict.fromkeys(addrs)), "plex_users": []}
        _, res = await worker.deliver(n["event"], st, only=ch)
        new_results += res
    kept = [r for r in n["results"] if r["ok"] or r.get("skipped")]
    db.update_results(nid, kept + new_results)
    return db.get_notification(nid)


@app.post("/api/resend/{nid}")
async def resend(nid: int):
    n = db.get_notification(nid)
    if not n:
        raise HTTPException(404)
    settings = db.get_settings()
    await worker.send_event(n["event"], settings, store=False)
    return {"ok": True}


@app.post("/api/poll")
async def poll_now(flush: bool = False):
    await worker.poll()
    sent = await worker.flush(force=flush)
    return {"sent": sent, "pending": db.pending_groups()}


@app.get("/api/thumb")
async def thumb(path: str):
    data = await plex.image(path, 300, 450)
    if not data:
        raise HTTPException(404)
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "max-age=86400"})


@app.exception_handler(Exception)
async def errors(_req, exc):
    logging.exception("error")
    return JSONResponse({"detail": str(exc)}, status_code=500)
