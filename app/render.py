"""Convierte un evento en mensajes: HTML de Telegram (límite de caption 1024), HTML de email y texto/markdown."""
from __future__ import annotations

import html
import re

from .i18n import _, get_lang

PLACEHOLDER = re.compile(r"^(episode|episodio|capítulo|capitulo)\s*\d+$", re.I)


def esc(s) -> str:
    return html.escape(str(s or ""), quote=False)


def human_size(n: int) -> str:
    if not n:
        return ""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit in ("GB", "TB") else f"{n:.0f} {unit}"
        n /= 1024
    return ""


def human_duration(ms: int | None) -> str:
    if not ms:
        return ""
    m = round(ms / 60000)
    return f"{m // 60} h {m % 60:02d} min" if m >= 60 else f"{m} min"


def season_label(s: dict) -> str:
    if s["index"] == 0:
        return _("Especiales")
    t = s.get("title") or ""
    if not t or re.fullmatch(r"(season|temporada)\s*\d+", t, re.I):
        return _("Temporada {n}", n=s["index"])
    return t


def ep_code(season: int, ep: int | None) -> str:
    return f"S{season:02d}E{ep:02d}" if ep is not None and season >= 0 else (f"E{ep:02d}" if ep is not None else "")


def ranges(idx: list[int]) -> str:
    idx = sorted(i for i in idx if i is not None)
    if not idx:
        return ""
    out, start, prev = [], idx[0], idx[0]
    for i in idx[1:] + [None]:
        if i is not None and i == prev + 1:
            prev = i
            continue
        out.append(f"E{start:02d}" if start == prev else f"E{start:02d}–E{prev:02d}")
        if i is not None:
            start = prev = i
    return ", ".join(out)


def ep_title(e: dict) -> str:
    t = e.get("title") or ""
    return "" if PLACEHOLDER.match(t.strip()) else t


def headline(ev: dict) -> tuple[str, str]:
    """(emoji, texto) de la cabecera."""
    if ev["type"] == "movie":
        return "🎬", _("Nueva película")
    k = ev["kind"]
    s0 = ev["seasons"][0]
    if k == "series_full":
        h = ("🏆", _("Serie completa · {n} temporadas", n=len(ev["seasons"])))
    elif k == "multi_season":
        h = ("📚", _("{e} episodios nuevos en {n} temporadas", e=ev["episode_count"], n=len(ev["seasons"])))
    elif k == "season_full":
        h = ("📦", _("{s} completa", s=season_label(s0)))
    elif k == "season_completed":
        h = ("🏁", _("{s} completada", s=season_label(s0)))
    elif k == "episode":
        h = ("📺", _("Nuevo episodio"))
    else:
        h = ("📺", _("{n} episodios nuevos", n=len(s0["episodes"])))
    if ev.get("is_new_show") and k not in ("series_full",):
        h = ("🆕", _("Nueva serie · {h}", h=h[1]))
    return h


def season_status(s: dict) -> str:
    if s["index"] == 0:
        return _("{n} especiales en Plex", n=s["in_plex"])
    if s["total"]:
        if s["complete"]:
            return _("{n}/{n} episodios ✅ completa", n=s["total"])
        txt = _("{a} de {b} episodios en Plex", a=s["in_plex"], b=s["total"])
        if s.get("caught_up"):
            txt += _(" · al día ({n} emitidos)", n=s["aired_total"])
        elif s.get("missing"):
            miss = s["missing"]
            txt += _(" · faltan {r}", r=ranges(miss[:12])) + ("…" if len(miss) > 12 else "")
        return txt
    return _("{n} episodios en Plex", n=s["in_plex"])


def _meta_line(ev: dict) -> list[str]:
    parts = []
    obj = ev.get("show") or ev.get("movie")
    if ev.get("resolutions") or obj.get("resolutions"):
        parts.append("🎞 " + " / ".join(ev.get("resolutions") or obj.get("resolutions")))
    if obj.get("library"):
        parts.append("📁 " + obj["library"])
    return parts


def build(ev: dict, max_list: int = 8) -> dict:
    """Estructura neutral -> {headline, emoji, title, lines:[(kind, text)], summary, link, thumb}."""
    emoji, head = headline(ev)
    lines: list[tuple[str, str]] = []  # kind: 'b' bold-ish, 'n' normal, 'i' item, 'm' meta, 's' status
    if ev["type"] == "movie":
        m = ev["movie"]
        title = m["title"] + (f" ({m['year']})" if m.get("year") else "")
        if m.get("original_title") and m["original_title"] != m["title"]:
            lines.append(("i_", m["original_title"]))
        info = []
        if m.get("genres"):
            info.append(", ".join(m["genres"]))
        if m.get("duration"):
            info.append(human_duration(m["duration"]))
        if m.get("rating"):
            info.append(f"⭐ {m['rating']:.1f}")
        if m.get("content_rating"):
            info.append(m["content_rating"].split("/")[-1].upper())
        if info:
            lines.append(("n", " · ".join(info)))
        if m.get("directors"):
            lines.append(("n", "🎥 " + ", ".join(m["directors"])))
        summary = m.get("tagline") and m.get("summary") and f"{m['summary']}" or m.get("summary")
        thumb, link = m.get("thumb"), m["link"]
        meta = _meta_line(ev)
    else:
        sh = ev["show"]
        title = sh["title"] + (f" ({sh['year']})" if sh.get("year") else "")
        seasons = ev["seasons"]
        # en subidas de varias temporadas, juntar las temporadas completas consecutivas en una línea
        blocks: list[list[dict]] = []
        for s in seasons:
            if (len(seasons) > 1 and s["kind"] == "season_full" and s["index"] > 0 and blocks
                    and blocks[-1][-1]["kind"] == "season_full" and blocks[-1][-1]["index"] == s["index"] - 1):
                blocks[-1].append(s)
            else:
                blocks.append([s])
        for blk in blocks[:6]:
            if len(blk) > 1:
                n = sum(len(x["episodes"]) for x in blk)
                lines.append(("b", _("Temporadas {a}–{b} completas · {n} episodios", a=blk[0]["index"], b=blk[-1]["index"], n=n)))
                continue
            s = blk[0]
            eps = s["episodes"]
            if s["kind"] == "episode" and len(seasons) == 1:
                e = eps[0]
                t = ep_title(e)
                lines.append(("b", ep_code(s["index"], e["index"]) + (f" · «{t}»" if t else "")))
                extra = []
                if e.get("aired"):
                    extra.append(_("emitido {d}", d=_fmt_date(e["aired"])))
                if e.get("duration"):
                    extra.append(human_duration(e["duration"]))
                if e.get("replacement"):
                    extra.append(_("reemplazo/mejor calidad"))
                if extra:
                    lines.append(("n", " · ".join(extra)))
            elif s["kind"] == "season_full":
                lines.append(("b", _("{s} · {n} episodios", s=season_label(s), n=len(eps))))
            else:
                lines.append(("b", f"{season_label(s)} · {ranges([e['index'] for e in eps])}"
                                   + (_(" ({n} ep.)", n=len(eps)) if len(eps) > 1 else "")))
                if len(seasons) == 1 and any(ep_title(e) for e in eps):
                    shown = eps[:max_list]
                    for e in shown:
                        t = ep_title(e)
                        lines.append(("i", f"E{e['index']:02d}" + (f" · {t}" if t else "")
                                      + (" ↻" if e.get("replacement") else "")))
                    if len(eps) > len(shown):
                        lines.append(("i", _("… y {n} más", n=len(eps) - len(shown))))
            if not (len(seasons) > 1 and s["kind"] == "season_full"):
                lines.append(("s", season_status(s)))
        if len(blocks) > 6:
            lines.append(("n", _("… y {n} bloques de temporadas más", n=len(blocks) - 6)))
        if not ev.get("identified"):
            lines.append(("n", _("⚠️ Serie sin identificar en Plex: no se conoce el total de episodios")))
        if ev["kind"] == "episode":
            summary = seasons[0]["episodes"][0].get("summary") or sh.get("summary")
        elif ev["kind"] == "season_full":
            summary = seasons[0].get("summary") or sh.get("summary")
        else:
            summary = sh.get("summary")
        thumb = seasons[0].get("thumb") if ev["kind"] in ("season_full",) and seasons[0].get("thumb") else sh.get("thumb")
        link = seasons[0]["link"] if len(seasons) == 1 and ev["kind"] != "episode" else sh["link"]
        if ev["kind"] == "episode":
            link = sh["link"]
        meta = _meta_line(ev)
        if sh.get("genres"):
            meta.append("🏷 " + ", ".join(sh["genres"]))
    return {"emoji": emoji, "headline": head, "title": title, "lines": lines,
            "meta": meta, "summary": (summary or "").strip(), "thumb": thumb, "link": link}


def _fmt_date(iso: str) -> str:
    try:
        y, m, d = iso.split("-")
        return iso if get_lang() == "en" else f"{d}-{m}-{y}"
    except ValueError:
        return iso


def _trunc(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1].rsplit(" ", 1)[0] + "…"


def telegram_html(msg: dict, limit: int = 1024) -> str:
    """Genera el HTML para Telegram recortando resumen y lista hasta caber en `limit`."""
    def make(summary_len: int, max_items: int) -> str:
        out = [f"{msg['emoji']} <b>{esc(msg['headline'])}</b>", f"<b>{esc(msg['title'])}</b>"]
        items = 0
        hidden = 0
        for kind, text in msg["lines"]:
            if kind == "i":
                items += 1
                if items > max_items:
                    hidden += 1
                    continue
                out.append(f"  • {esc(text)}")
            elif kind == "b":
                out.append(f"\n<b>{esc(text)}</b>")
            elif kind == "s":
                out.append(f"📊 <i>{esc(text)}</i>")
            elif kind == "i_":
                out.append(f"<i>{esc(text)}</i>")
            else:
                out.append(esc(text))
        if hidden:
            out.append("  • " + _("… y {n} más", n=hidden))
        if msg["meta"]:
            out.append("\n" + esc("  ·  ".join(msg["meta"])))
        if msg["summary"] and summary_len > 40:
            out.append(f"\n<blockquote expandable>{esc(_trunc(msg['summary'], summary_len))}</blockquote>")
        return "\n".join(out)

    for slen, mi in ((600, 20), (400, 12), (250, 8), (150, 5), (0, 3), (0, 0)):
        t = make(slen, mi)
        if len(t) <= limit:
            return t
    return t[:limit]


def plain_text(msg: dict) -> str:
    out = [f"{msg['emoji']} {msg['headline']}", msg["title"], ""]
    for kind, text in msg["lines"]:
        out.append({"i": f"  • {text}", "s": f"📊 {text}"}.get(kind, text))
    if msg["meta"]:
        out += ["", "  ·  ".join(msg["meta"])]
    if msg["summary"]:
        out += ["", _trunc(msg["summary"], 500)]
    out += ["", msg["link"]]
    return "\n".join(out)


EMAIL_THEMES = {
    "light": {"page": "#f2f2f2", "card": "#ffffff", "head_bg": "#1f1f1f", "head_fg": "#e5a00d", "title": "#111111",
              "text": "#555555", "item": "#444444", "status": "#b26a00", "meta": "#777777", "summary": "#333333",
              "line": "#e6e6e6", "btn_bg": "#e5a00d", "btn_fg": "#1f1f1f"},
    "dark": {"page": "#0f0f0f", "card": "#1c1c1c", "head_bg": "#111111", "head_fg": "#e5a00d", "title": "#f2f2f2",
             "text": "#b8b8b8", "item": "#cfcfcf", "status": "#f0b43c", "meta": "#8c8c8c", "summary": "#d6d6d6",
             "line": "#2e2e2e", "btn_bg": "#e5a00d", "btn_fg": "#141414"},
}
# elemento -> (propiedad css, clave de la paleta); se usa para el modo "auto" (media query de modo oscuro)
_EMAIL_CLASSES = {
    "pn-page": [("background", "page")], "pn-card": [("background", "card")],
    "pn-head": [("background", "head_bg"), ("color", "head_fg")], "pn-title": [("color", "title")],
    "pn-text": [("color", "text")], "pn-item": [("color", "item")], "pn-status": [("color", "status")],
    "pn-meta": [("color", "meta"), ("border-color", "line")], "pn-summary": [("color", "summary")],
    "pn-btn": [("background", "btn_bg"), ("color", "btn_fg")],
}


def email_html(msg: dict, poster_cid: str | None, theme: str = "light", poster_src: str | None = None) -> str:
    """theme: light | dark | auto (claro por defecto, oscuro si el cliente de correo está en modo oscuro)."""
    t = EMAIL_THEMES["dark" if theme == "dark" else "light"]
    d = EMAIL_THEMES["dark"]

    def st(cls: str, extra: str = "") -> str:
        css = ";".join(f"{prop}:{t[key]}" for prop, key in _EMAIL_CLASSES[cls])
        return f'class="{cls}" style="{css};{extra}"'

    rows = []
    for kind, text in msg["lines"]:
        if kind == "b":
            rows.append(f'<div {st("pn-title", "font-weight:600;margin-top:10px;font-size:15px")}>{esc(text)}</div>')
        elif kind == "i":
            rows.append(f'<div {st("pn-item", "padding-left:12px;font-size:14px")}>• {esc(text)}</div>')
        elif kind == "s":
            rows.append(f'<div {st("pn-status", "font-size:13px;margin-top:2px")}>📊 {esc(text)}</div>')
        else:
            rows.append(f'<div {st("pn-text", "font-size:14px")}>{esc(text)}</div>')
    src = f"cid:{poster_cid}" if poster_cid else poster_src
    poster = (f'<td width="170" valign="top" style="padding-right:18px"><img src="{esc(src)}" width="160" '
              f'style="border-radius:8px;display:block" alt=""></td>') if src else ""
    meta = (f'<div {st("pn-meta", "font-size:13px;margin-top:12px;padding-top:10px;border-top:1px solid")}>'
            f'{esc("  ·  ".join(msg["meta"]))}</div>') if msg["meta"] else ""
    summary = (f'<p {st("pn-summary", "font-size:14px;line-height:1.55;margin:16px 0 0")}>{esc(_trunc(msg["summary"], 900))}</p>'
               if msg["summary"] else "")
    scheme = {"dark": "dark", "auto": "light dark"}.get(theme, "light")
    dark_css = ""
    if theme == "auto":
        rules = "".join(f".{cls}{{" + ";".join(f"{prop}:{d[key]} !important" for prop, key in props) + "}"
                        for cls, props in _EMAIL_CLASSES.items())
        dark_css = f"@media (prefers-color-scheme: dark){{{rules}}}[data-ogsc] .pn-card{{background:{d['card']} !important}}"
    return f"""<!doctype html><html lang="{get_lang()}"><head><meta charset="utf-8">
<meta name="color-scheme" content="{scheme}"><meta name="supported-color-schemes" content="{scheme}">
<style>:root{{color-scheme:{scheme};supported-color-schemes:{scheme}}}{dark_css}</style></head>
<body {st("pn-page", "margin:0;font-family:Segoe UI,Helvetica,Arial,sans-serif")}>
<table width="100%" cellpadding="0" cellspacing="0" {st("pn-page")}><tr><td align="center" style="padding:24px">
<table width="600" cellpadding="0" cellspacing="0" {st("pn-card", "border-radius:12px;overflow:hidden;max-width:600px")}>
<tr><td {st("pn-head", "padding:14px 22px;font-size:15px;font-weight:600")}>{msg['emoji']} {esc(msg['headline'])}</td></tr>
<tr><td style="padding:20px 22px"><table cellpadding="0" cellspacing="0"><tr>{poster}<td valign="top">
<div {st("pn-title", "font-size:21px;font-weight:700")}>{esc(msg['title'])}</div>
{''.join(rows)}{meta}</td></tr></table>{summary}
<div style="margin-top:18px"><a href="{esc(msg['link'])}" {st("pn-btn", "text-decoration:none;padding:10px 18px;border-radius:6px;font-weight:600;display:inline-block")}>▶ {esc(_("Ver en Plex"))}</a></div>
</td></tr></table></td></tr></table></body></html>"""


def markdown(msg: dict) -> str:
    out = [f"**{msg['title']}**", ""]
    for kind, text in msg["lines"]:
        out.append({"b": f"**{text}**", "i": f"- {text}", "s": f"📊 _{text}_"}.get(kind, text))
    if msg["meta"]:
        out += ["", "  ·  ".join(msg["meta"])]
    if msg["summary"]:
        out += ["", _trunc(msg["summary"], 500)]
    out += ["", f"[▶ {_('Ver en Plex')}]({msg['link']})"]
    return "\n".join(out)
