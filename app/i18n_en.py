"""Traducción al inglés de los textos del servidor (avisos y errores de la API)."""

EN = {
    # ---- API / inicio de sesión
    "no autenticado": "not authenticated",
    "Demasiados intentos. Espera {n} min.": "Too many attempts. Wait {n} min.",
    "Usuario o contraseña incorrectos": "Wrong username or password",
    " (queda 1 intento)": " (1 attempt left)",
    " (quedan {n} intentos)": " ({n} attempts left)",
    ". Acceso bloqueado por 5 min": ". Access locked for 5 min",
    "idioma inválido": "invalid language",
    "no se pudo armar el evento": "could not build the event",
    "Chat ID de Telegram inválido (ej. 123456789, -1001234567890 o @canal)":
        "Invalid Telegram chat ID (e.g. 123456789, -1001234567890 or @channel)",
    "Correo de prueba inválido": "Invalid test email",
    "Elige al menos un destino de prueba": "Choose at least one test destination",
    "falta el bot token en Configuración → Telegram": "missing bot token in Settings → Telegram",
    "No se pudo conectar con plex.tv ({e}). Revisa que el contenedor tenga salida a internet / DNS.":
        "Could not connect to plex.tv ({e}). Check that the container has internet access / DNS.",
    "sin detalle": "no details",

    # ---- envíos
    "falta bot_token o chat_ids": "missing bot_token or chat_ids",
    "sin respuesta de Telegram; puede que el mensaje sí haya llegado (no se reintenta para no duplicar)":
        "no response from Telegram; the message may have been delivered (not retried to avoid duplicates)",
    "(sin conexión con api.telegram.org)": "(no connection to api.telegram.org)",
    " (tras {n} intentos)": " (after {n} attempts)",
    "sin correo en Plex": "no email in Plex",
    "sin acceso a esta biblioteca": "no access to this library",
    "biblioteca excluida para este usuario": "library excluded for this user",
    "falta el servidor SMTP": "missing SMTP server",
    "no hay destinatarios para esta biblioteca": "no recipients for this library",
    "login SMTP: {e}": "SMTP login: {e}",
    "sin URLs": "no URLs",
    "URL inválida": "invalid URL",
    "falló el envío (ver logs)": "sending failed (see logs)",

    # ---- mensajes
    "Ver en Plex": "Watch on Plex",
    "Nueva película": "New movie",
    "Nuevo episodio": "New episode",
    "{n} episodios nuevos": "{n} new episodes",
    "{e} episodios nuevos en {n} temporadas": "{e} new episodes in {n} seasons",
    "Serie completa · {n} temporadas": "Complete series · {n} seasons",
    "Nueva serie · {h}": "New series · {h}",
    "{s} completa": "{s} complete",
    "{s} completada": "{s} completed",
    "Especiales": "Specials",
    "Temporada {n}": "Season {n}",
    "Temporadas {a}–{b} completas · {n} episodios": "Seasons {a}–{b} complete · {n} episodes",
    "{s} · {n} episodios": "{s} · {n} episodes",
    " ({n} ep.)": " ({n} ep.)",
    "{n} especiales en Plex": "{n} specials in Plex",
    "{n}/{n} episodios ✅ completa": "{n}/{n} episodes ✅ complete",
    "{a} de {b} episodios en Plex": "{a} of {b} episodes in Plex",
    " · al día ({n} emitidos)": " · up to date ({n} aired)",
    " · faltan {r}": " · missing {r}",
    "{n} episodios en Plex": "{n} episodes in Plex",
    "emitido {d}": "aired {d}",
    "reemplazo/mejor calidad": "replacement/better quality",
    "… y {n} más": "… and {n} more",
    "… y {n} bloques de temporadas más": "… and {n} more season blocks",
    "⚠️ Serie sin identificar en Plex: no se conoce el total de episodios":
        "⚠️ Series not matched in Plex: total episode count unknown",
}
