// Traducción de la interfaz. El texto en español es la clave; si falta una traducción se muestra en español.
let LANG = "es", LOC = "es-CL";
try { if (localStorage.getItem("pn_lang") === "en") { LANG = "en"; LOC = "en-US"; } } catch (e) {}
function setLang(l) {
  LANG = l === "en" ? "en" : "es"; LOC = LANG === "en" ? "en-US" : "es-CL";
  document.documentElement.lang = LANG;
  try { localStorage.setItem("pn_lang", LANG); } catch (e) {}
}
function _t(s, v) {
  let o = (LANG === "en" && I18N_EN[s]) || s;
  if (v) o = o.replace(/\{(\w+)\}/g, (m, k) => (k in v ? v[k] : m));
  return o;
}
// data-t: texto plano · data-th: HTML interno · title / placeholder / aria-label: siempre
function tStatic(root) {
  const r = root || document;
  r.querySelectorAll("[data-t]").forEach(e => { e.dataset.t = e.dataset.t || e.textContent.trim(); e.textContent = _t(e.dataset.t); });
  r.querySelectorAll("[data-th]").forEach(e => { e.dataset.th = e.dataset.th || e.innerHTML.trim(); e.innerHTML = _t(e.dataset.th); });
  r.querySelectorAll("[title]").forEach(e => { e.dataset.tt = e.dataset.tt || e.title; e.title = _t(e.dataset.tt); });
  r.querySelectorAll("[placeholder]").forEach(e => { e.dataset.tp = e.dataset.tp || e.placeholder; e.placeholder = _t(e.dataset.tp); });
  r.querySelectorAll("[aria-label]").forEach(e => { e.dataset.ta = e.dataset.ta || e.getAttribute("aria-label"); e.setAttribute("aria-label", _t(e.dataset.ta)); });
  if (document.title) { document.documentElement.dataset.title = document.documentElement.dataset.title || document.title; document.title = _t(document.documentElement.dataset.title); }
}
const I18N_EN = {
  // general
  "Historial": "History", "Probar": "Test", "Configuración": "Settings", "Salir": "Log out", "Cerrar sesión": "Log out",
  "Cargando…": "Loading…", "Guardar": "Save", "Guardado ✓": "Saved ✓", "Cambios sin guardar": "Unsaved changes",
  "Activado": "Enabled", "Error: {e}": "Error: {e}", "error: {e}": "error: {e}", "sesión expirada": "session expired",
  "hace {v}": "{v} ago", "Idioma / Language": "Idioma / Language",
  // login
  "Plex Notify · Iniciar sesión": "Plex Notify · Sign in", "Inicia sesión para continuar": "Sign in to continue",
  "Usuario": "Username", "Contraseña": "Password", "Mostrar": "Show", "Ocultar": "Hide", "Mostrar contraseña": "Show password",
  "Recordarme en este equipo (30 días)": "Remember me on this device (30 days)", "Entrar": "Sign in", "Entrando…": "Signing in…",
  "No se pudo conectar con el servidor": "Could not connect to the server", "Error {n}": "Error {n}",
  // estado
  "ningún canal activo": "no active channel", "revisado {v}": "checked {v}", "correo": "email",
  "{n} ítem(s) · se envía en ~{s} s": "{n} item(s) · sending in ~{s} s",
  // historial
  "⏳ En espera (agrupando la subida)": "⏳ Waiting (grouping the upload)", "Notificaciones enviadas": "Sent notifications",
  "Revisar Plex ahora": "Check Plex now", "🧪 prueba": "🧪 test", "{a}/{b} enviados": "{a}/{b} sent", "sin canales": "no channels",
  "Reintentar fallidos": "Retry failed", "Reintentando…": "Retrying…", "Reenviar": "Resend", "omitidos": "skipped",
  "Aún no hay notificaciones. Las subidas nuevas a Plex aparecerán aquí.": "No notifications yet. New uploads to Plex will show up here.",
  "Se reenviará por TODOS los canales activos y a TODOS los destinatarios (incluso quienes ya lo recibieron). ¿Continuar?":
    "It will be resent through ALL active channels and to ALL recipients (including those who already got it). Continue?",
  "Reenviado": "Resent", "Siguen fallando:": "Still failing:",
  "Listo: se envió a los destinos que habían fallado.": "Done: sent to the destinations that had failed.",
  // probar
  "Subidas recientes reales": "Recent real uploads",
  "Elige una para ver exactamente cómo quedaría la notificación.": "Pick one to see exactly how the notification would look.",
  "Vista previa": "Preview", "🧪 Destinos de prueba": "🧪 Test destinations",
  "solo reciben las pruebas, nunca los avisos reales": "they only get tests, never the real notifications",
  "Chat ID de Telegram": "Telegram chat ID", "Correo": "Email", "123456789 o -100…": "123456789 or -100…", "tu@correo.cl": "you@example.com",
  "Enviar prueba a ambos": "Send test to both", "Solo Telegram de prueba": "Test Telegram only", "Solo correo de prueba": "Test email only",
  "¿Tu chat ID? Escríbele a <b>@userinfobot</b> en Telegram. Antes, envíale un mensaje a tu bot (si no, Telegram no le deja escribirte).":
    "Your chat ID? Message <b>@userinfobot</b> on Telegram. First send a message to your bot (otherwise Telegram won't let it write to you).",
  "Selecciona una subida.": "Select an upload.", "Generando…": "Generating…",
  "Oscuro": "Dark", "Claro": "Light", "Automático": "Automatic",
  "Enviar de verdad a los destinos configurados…": "Really send to the configured destinations…",
  "Telegram configurado": "Configured Telegram", "Apprise configurado": "Configured Apprise",
  "Correo a todos los destinatarios": "Email to all recipients", "Todos los canales activos": "All active channels",
  "película": "movie", "{n} episodio(s)": "{n} episode(s)", "omitido ({n})": "skipped ({n})",
  "No hay canales activos (actívalos en Configuración).": "No active channels (enable them in Settings).",
  "Primero elige una subida de la lista": "First pick an upload from the list",
  "Escribe un chat ID de Telegram válido": "Enter a valid Telegram chat ID", "Escribe un correo válido": "Enter a valid email",
  "Enviando prueba…": "Sending test…", "Enviando…": "Sending…",
  "al/los chat(s) de Telegram configurados": "to the configured Telegram chat(s)",
  "a todas las URLs de Apprise configuradas": "to all configured Apprise URLs",
  "a TODOS los destinatarios de correo configurados (usuarios de Plex marcados y direcciones adicionales)":
    "to ALL configured email recipients (checked Plex users and additional addresses)",
  "por TODOS los canales activos, a todos los destinatarios": "through ALL active channels, to all recipients",
  "Esto NO es una prueba: se enviará {w}. ¿Continuar?": "This is NOT a test: it will be sent {w}. Continue?",
  // configuración
  "Detección": "Detection", "Revisar Plex cada (segundos)": "Check Plex every (seconds)",
  "Esperar sin cambios antes de notificar (segundos)": "Wait without changes before notifying (seconds)",
  "Máx. episodios listados": "Max. episodes listed",
  "Cuando subes varios episodios, la app espera a que pase este tiempo sin novedades de esa serie y manda <b>un solo</b> mensaje (1 episodio, varios, o temporada completa).":
    "When you upload several episodes, the app waits this long without news from that series and sends <b>a single</b> message (1 episode, several, or a full season).",
  "Bibliotecas (ninguna marcada = todas)": "Libraries (none checked = all)", "películas": "movies", "series": "TV shows",
  "Notificar también re-subidas de episodios ya avisados (mejor calidad)": "Also notify re-uploads of already notified episodes (better quality)",
  "Bot token (@BotFather)": "Bot token (@BotFather)",
  "Chat IDs (separados por coma; grupos/canales con -100…)": "Chat IDs (comma separated; groups/channels start with -100…)",
  "Enviar sin sonido": "Send silently", "Correo (SMTP)": "Email (SMTP)", "Servidor": "Server", "Puerto": "Port", "Seguridad": "Security",
  "Ninguna": "None", "Contraseña / app password": "Password / app password", "Remitente": "From",
  "Direcciones adicionales (coma) — reciben todo": "Additional addresses (comma) — get everything",
  "Tema del correo": "Email theme", "Automático (según el cliente de correo)": "Automatic (follows the email client)",
  "Usuarios con quienes compartes Plex": "Users you share Plex with", "Actualizar lista": "Refresh list",
  "Marcar todos": "Check all", "Ninguno": "None", "Consultando plex.tv…": "Querying plex.tv…", "· actualizada {v}": "· updated {v}",
  "Toca una biblioteca de un usuario para <b>excluirla</b> de sus correos (🔕). Las tachadas sin borde son bibliotecas a las que no tiene acceso. Recuerda <b>Guardar</b>.":
    "Tap a user's library to <b>exclude</b> it from their emails (🔕). Struck-through ones without a border are libraries they can't access. Remember to <b>Save</b>.",
  "Enviar a cada usuario solo avisos de las bibliotecas que tiene compartidas": "Only send each user notifications for the libraries shared with them",
  "Excluida: no recibe correos de esta biblioteca. Clic para incluir": "Excluded: gets no emails for this library. Click to include",
  "Recibe correos de esta biblioteca. Clic para excluir": "Gets emails for this library. Click to exclude",
  "No tiene acceso a esta biblioteca": "No access to this library", "invitación pendiente": "pending invite",
  "sin correo en Plex": "no email in Plex", "No compartes el servidor con nadie.": "You don't share the server with anyone.",
  "Otros (Apprise: Discord, ntfy, Pushover, Gotify, Slack, WhatsApp…)": "Others (Apprise: Discord, ntfy, Pushover, Gotify, Slack, WhatsApp…)",
  "Una URL por línea —": "One URL per line —", "formatos": "formats",
  "Ver en Plex": "Watch on Plex",
  "discord://webhook_id/webhook_token\nntfys://ntfy.sh/mi-tema": "discord://webhook_id/webhook_token\nntfys://ntfy.sh/my-topic",
};
