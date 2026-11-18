from __future__ import annotations

import asyncio
import json
import logging
import time
import os
import smtplib
import ssl
import tempfile
from email.message import EmailMessage

import httpx

from . import render
from .i18n import _

log = logging.getLogger("plex-notify")
# esperas entre reintentos ante errores de red (segundos)
RETRY_DELAYS = [5, 20, 60]


async def send_telegram(cfg: dict, msg: dict, poster: bytes | None) -> list[dict]:
    token = cfg["bot_token"].strip()
    chats = [c.strip() for c in str(cfg["chat_ids"]).replace(";", ",").split(",") if c.strip()]
    if not token or not chats:
        return [{"channel": "telegram", "ok": False, "error": _("falta bot_token o chat_ids")}]
    markup = json.dumps({"inline_keyboard": [[{"text": "▶ " + _("Ver en Plex"), "url": msg["link"]}]]})
    base = f"https://api.telegram.org/bot{token}"
    out = []
    # lectura generosa: Telegram a veces tarda en responder aunque ya entregó el mensaje
    async with httpx.AsyncClient(timeout=httpx.Timeout(30, read=90)) as c:
        for chat in chats:
            data = {"chat_id": chat, "parse_mode": "HTML", "reply_markup": markup,
                    "disable_notification": str(bool(cfg.get("silent"))).lower()}
            last_err = None
            for attempt, wait in enumerate(RETRY_DELAYS + [None]):
                try:
                    if poster:
                        r = await c.post(f"{base}/sendPhoto", data={**data, "caption": render.telegram_html(msg, 1024)},
                                         files={"photo": ("poster.jpg", poster, "image/jpeg")})
                    else:
                        r = await c.post(f"{base}/sendMessage", data={**data, "text": render.telegram_html(msg, 4096),
                                                                      "link_preview_options": json.dumps({"is_disabled": True})})
                    j = r.json()
                    if j.get("ok"):
                        last_err = None
                        break
                    last_err = j.get("description") or f"HTTP {r.status_code}"
                    # solo reintentar límites de envío (429) o fallas del lado de Telegram (5xx)
                    if r.status_code == 429:
                        wait = int((j.get("parameters") or {}).get("retry_after") or wait or 5)
                    elif r.status_code < 500:
                        break
                except (httpx.ReadTimeout, httpx.WriteTimeout, httpx.RemoteProtocolError, httpx.ReadError) as e:
                    # la petición ya salió: Telegram pudo haberla entregado. No reintentar para no duplicar.
                    last_err = f"{type(e).__name__}: " + _("sin respuesta de Telegram; puede que el mensaje sí haya "
                                                            "llegado (no se reintenta para no duplicar)")
                    break
                except httpx.TransportError as e:
                    last_err = (f"{type(e).__name__}: {e}" if str(e) else
                                f"{type(e).__name__} " + _("(sin conexión con api.telegram.org)"))
                except Exception as e:  # noqa: BLE001
                    last_err = f"{type(e).__name__}: {e}"
                    break
                if wait is None:
                    break
                log.warning("telegram %s: %s — reintento %d en %ds", chat, last_err, attempt + 1, wait)
                await asyncio.sleep(wait)
            res = {"channel": "telegram", "target": chat, "ok": last_err is None, "error": last_err}
            if last_err and attempt:
                res["error"] = last_err + _(" (tras {n} intentos)", n=attempt + 1)
            out.append(res)
    return out


def email_recipients(cfg: dict, section: str | None) -> tuple[list[dict], list[dict]]:
    """-> (destinatarios [{email, label}], omitidos [{label, reason}]).
    Direcciones manuales: siempre. Usuarios de Plex marcados: solo si tienen acceso a la biblioteca (si se pide)."""
    from . import db
    out, skipped, seen = [], [], set()
    for t in str(cfg.get("to", "")).replace(";", ",").split(","):
        t = t.strip()
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append({"email": t, "label": t})
    users = {u["id"]: u for u in db.get_state("plex_users", [])}
    for uid in cfg.get("plex_users", []):
        u = users.get(uid)
        if not u:
            continue
        label = u["username"]
        if not u.get("email"):
            skipped.append({"label": label, "reason": _("sin correo en Plex")})
            continue
        if (cfg.get("respect_access", True) and section and not u.get("all_libraries")
                and section not in u.get("sections", [])):
            skipped.append({"label": label, "reason": _("sin acceso a esta biblioteca")})
            continue
        if section and section in (cfg.get("user_excludes") or {}).get(uid, []):
            skipped.append({"label": label, "reason": _("biblioteca excluida para este usuario")})
            continue
        if u["email"].lower() not in seen:
            seen.add(u["email"].lower())
            out.append({"email": u["email"], "label": label})
    return out, skipped


def _send_email_sync(cfg: dict, msg: dict, poster: bytes | None, section: str | None) -> list[dict]:
    recipients, skipped = email_recipients(cfg, section)
    results = [{"channel": "email", "target": x["label"], "ok": True, "skipped": True, "error": None,
                "note": x["reason"]} for x in skipped]
    if not cfg.get("host"):
        return results + [{"channel": "email", "ok": False, "error": _("falta el servidor SMTP")}]
    if not recipients:
        return results + [{"channel": "email", "ok": False, "error": _("no hay destinatarios para esta biblioteca")}]
    cid = "poster@plexnotify" if poster else None
    html_body = render.email_html(msg, cid, cfg.get("theme", "dark"))
    text_body = render.plain_text(msg)
    port = int(cfg.get("port") or 587)
    sec = cfg.get("security", "starttls")
    s = None
    for attempt, wait in enumerate(RETRY_DELAYS + [None]):
        try:
            if sec == "ssl":
                s = smtplib.SMTP_SSL(cfg["host"], port, context=ssl.create_default_context(), timeout=30)
            else:
                s = smtplib.SMTP(cfg["host"], port, timeout=30)
                if sec == "starttls":
                    s.starttls(context=ssl.create_default_context())
            if cfg.get("username"):
                s.login(cfg["username"], cfg.get("password", ""))
            break
        except smtplib.SMTPAuthenticationError as e:
            return results + [{"channel": "email", "ok": False, "error": _("login SMTP: {e}", e=e),
                               "targets": [r["email"] for r in recipients]}]
        except (OSError, smtplib.SMTPException) as e:
            if s:
                try:
                    s.close()
                except Exception:  # noqa: BLE001
                    pass
            s = None
            if wait is None:
                return results + [{"channel": "email", "ok": False, "error": f"SMTP: {e}" + _(" (tras {n} intentos)", n=attempt + 1),
                                   "targets": [r["email"] for r in recipients]}]
            log.warning("SMTP: %s — reintento %d en %ds", e, attempt + 1, wait)
            time.sleep(wait)
    with s:
        # un correo por persona: nadie ve las direcciones de los demás
        for r in recipients:
            em = EmailMessage()
            em["Subject"] = f"{msg['emoji']} {msg['headline']}: {msg['title']}"
            em["From"] = cfg.get("from") or cfg.get("username")
            em["To"] = r["email"]
            em.set_content(text_body)
            em.add_alternative(html_body, subtype="html")
            if poster:
                em.get_payload()[1].add_related(poster, maintype="image", subtype="jpeg", cid=f"<{cid}>")
            try:
                s.send_message(em)
                results.append({"channel": "email", "target": r["label"], "address": r["email"], "ok": True, "error": None})
            except Exception as e:  # noqa: BLE001
                results.append({"channel": "email", "target": r["label"], "address": r["email"], "ok": False, "error": str(e)})
    return results


async def send_email(cfg: dict, msg: dict, poster: bytes | None, section: str | None = None) -> list[dict]:
    return await asyncio.to_thread(_send_email_sync, cfg, msg, poster, section)


def _send_apprise_sync(cfg: dict, msg: dict, poster: bytes | None) -> list[dict]:
    import apprise
    urls = [u.strip() for u in cfg["urls"].splitlines() if u.strip() and not u.strip().startswith("#")]
    if not urls:
        return [{"channel": "apprise", "ok": False, "error": _("sin URLs")}]
    out = []
    path = None
    if poster:
        fd, path = tempfile.mkstemp(suffix=".jpg")
        with os.fdopen(fd, "wb") as f:
            f.write(poster)
    try:
        for u in urls:
            a = apprise.Apprise()
            if not a.add(u):
                out.append({"channel": "apprise", "target": u.split("://")[0], "ok": False, "error": _("URL inválida")})
                continue
            ok = a.notify(title=f"{msg['emoji']} {msg['headline']}", body=render.markdown(msg),
                          body_format=apprise.NotifyFormat.MARKDOWN, attach=path)
            out.append({"channel": "apprise", "target": u.split("://")[0], "ok": bool(ok),
                        "error": None if ok else _("falló el envío (ver logs)")})
    finally:
        if path:
            os.unlink(path)
    return out


async def send_apprise(cfg: dict, msg: dict, poster: bytes | None) -> list[dict]:
    return await asyncio.to_thread(_send_apprise_sync, cfg, msg, poster)


async def dispatch(settings: dict, msg: dict, poster: bytes | None, only: str | None = None,
                   section: str | None = None) -> list[dict]:
    jobs = []
    for name, fn in (("telegram", send_telegram), ("email", send_email), ("apprise", send_apprise)):
        cfg = settings[name]
        if (only and only == name) or (not only and cfg.get("enabled")):
            jobs.append(send_email(cfg, msg, poster, section) if name == "email" else fn(cfg, msg, poster))
    results = []
    for r in await asyncio.gather(*jobs):
        results.extend(r)
    return results
