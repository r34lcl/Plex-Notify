# Plex Notify

Avisa por **Telegram**, **correo** u otros servicios (vía [Apprise](https://github.com/caronc/apprise)) cuando entra algo nuevo a Plex.

Nació como reemplazo de las notificaciones de Tautulli: entiende qué se subió realmente. Un capítulo suelto se anuncia como un capítulo, no como "serie completa".

## Qué detecta

Espera unos minutos sin novedades de una misma serie (por defecto 5) y recién ahí manda **un solo mensaje** con todo lo que llegó:

| Caso | Ejemplo de cabecera |
|---|---|
| 1 capítulo | 📺 Nuevo episodio · S02E05 «Título» |
| Varios capítulos | 📺 10 episodios nuevos · Temporada 3 · E41–E50 |
| Temporada entera de una vez | 📦 Temporada 4 completa |
| Capítulo que completa la temporada | 🏁 Temporada 1 completada |
| Varias temporadas | 📚 50 episodios nuevos en 5 temporadas |
| Serie nueva en la biblioteca | 🆕 Nueva serie · … |
| Serie completa con varias temporadas | 🏆 Serie completa · N temporadas |
| Película | 🎬 Nueva película |

El total real de episodios de cada temporada y sus fechas de emisión se consultan en el servicio de metadatos de Plex. Con eso el mensaje indica "5 de 26 · al día", "faltan E03, E07" o "12/12 ✅ completa".

> Las temporadas que Plex no tiene identificadas (`local://`) no traen total: el mensaje solo dice cuántos capítulos hay en Plex.

## Canales

- **Telegram:** póster, texto, resumen desplegable y botón "▶ Ver en Plex".
- **Correo (SMTP):** HTML con póster, con tema **Oscuro**, **Claro** o **Automático**.
  - **Usuarios de Plex:** se eligen de la lista de usuarios con quienes compartes el servidor (se obtiene de plex.tv y se refresca cada 6 h).
  - **Filtro por biblioteca:** con la opción activada, cada usuario solo recibe avisos de las bibliotecas que tiene compartidas.
  - **Exclusión por usuario:** toca una biblioteca de una persona para excluirla de sus correos (🔕), aunque tenga acceso.
  - **Privacidad:** se envía un correo individual por persona, así nadie ve las direcciones de los demás.
  - **Direcciones adicionales:** reciben todo, sin filtro.
- **Apprise:** Discord, ntfy, Pushover, Gotify, Slack, etc. Una URL por línea.

Los envíos fallidos por errores de red se reintentan solos. Desde el Historial se pueden reintentar o reenviar.

## Instalación

Requiere Docker con Docker Compose.

```bash
git clone https://github.com/r34lcl/Plex-Notify.git
cd Plex-Notify
cp .env.example .env
nano .env                     # completa PLEX_TOKEN y APP_PASSWORD
docker compose up -d --build
docker logs -f plex-notify
```

Abre `http://<servidor>:8092`, inicia sesión con `APP_USER` / `APP_PASSWORD` y configura los canales en **Configuración**.
Arriba a la derecha debe aparecer el nombre de tu servidor Plex en verde.

Al arrancar por primera vez, la app parte desde "ahora": no notifica lo que ya estaba en Plex.

### Dirección de Plex

En `docker-compose.yml`, `PLEX_URL` apunta por defecto a `host.docker.internal`, es decir, a Plex corriendo en la misma máquina.
Si Plex está en otro equipo, pon su IP (por ejemplo `http://192.168.1.10:32400`) y borra el bloque `extra_hosts`.

Para comprobar que se llega a Plex: `curl -s http://192.168.1.10:32400/identity`.

### Cómo obtener el PLEX_TOKEN

- **Desde Plex Web:** abre cualquier película → `⋯` → **Obtener información** → **Ver XML**. El token es el valor de `X-Plex-Token=` en la URL.
- **Desde el servidor:** está en `Preferences.xml` de Plex, atributo `PlexOnlineToken`.

Usa el token de la cuenta **dueña** del servidor; con él la app puede leer la lista de usuarios compartidos.

### Si el contenedor no tiene salida a internet

Si los envíos a Telegram o plex.tv fallan con `ConnectTimeout`, `timed out` o `Errno 97`, pero `curl` desde el servidor funciona, usa la red del servidor directamente:

```yaml
services:
  plex-notify:
    build: .
    container_name: plex-notify
    restart: unless-stopped
    env_file: .env
    network_mode: host
    environment:
      - PLEX_URL=http://127.0.0.1:32400
    volumes:
      - ./data:/data
```

Con `network_mode: host`, la interfaz queda en el puerto `APP_PORT` del servidor (8000 por defecto). Si está ocupado, define otro en `.env` (por ejemplo `APP_PORT=8092`).

> Con la red normal (`ports: "8092:8000"`) **no** definas `APP_PORT`: la app escucharía en otro puerto interno y la interfaz no respondería.

## Uso de la interfaz

- **Historial:** avisos enviados, a quién llegaron, a quién se omitió y por qué, y lo que está esperando a agruparse. "Revisar Plex ahora" fuerza una revisión.
- **Probar:** elige una subida reciente real y ve cómo quedaría en Telegram o en el correo.
  - **🧪 Destinos de prueba:** un chat ID de Telegram y un correo que reciben solo las pruebas, nunca los avisos reales.
  - **Chat ID:** escríbele a @userinfobot en Telegram. Antes, mándale un mensaje a tu bot, si no Telegram no le permite escribirte.
  - **Envío real:** "Enviar de verdad a los destinos configurados…" está plegado y pide confirmación.
- **Configuración:** frecuencia de revisión, tiempo de espera para agrupar, bibliotecas, máximo de episodios listados y datos de Telegram, SMTP y Apprise.

**Máx. episodios listados:** cuántos capítulos se muestran uno por uno con su título; el resto queda como "… y N más". Telegram limita el texto de una foto a 1024 caracteres, así que si no cabe, la app acorta primero el resumen y después la lista.

### Inicio de sesión

- **Recordarme** mantiene la sesión 30 días; sin marcarla, dura 12 h.
- 5 intentos fallidos seguidos bloquean esa IP por 5 minutos.
- Cambiar `APP_PASSWORD` y aplicar con `docker compose up -d` cierra todas las sesiones.
- La API también acepta Basic Auth (`curl -u usuario:clave`).

Si vas a exponer la interfaz a internet, ponla detrás de un proxy con HTTPS.

## Archivos

| Ruta | Contenido |
|---|---|
| `app/` | Código (FastAPI + SQLite) |
| `.env` | `PLEX_TOKEN`, `APP_USER`, `APP_PASSWORD` (**secreto**, no se versiona) |
| `data/plex-notify.db` | Configuración, historial y registro de lo ya notificado. **Contiene tokens y contraseñas**, no se versiona |

## Comandos útiles

```bash
docker compose up -d --build     # levantar / aplicar cambios de código
docker compose down              # detener
docker logs -f plex-notify       # ver detecciones y resultados de envíos
```

Si cambias algo en `.env`, usa `docker compose up -d`: `restart` no vuelve a leer `.env`.

## Mover a otro servidor

Toda la configuración vive en `.env` y `data/`. Detén la app, copia la carpeta completa al servidor nuevo (por un medio privado, como `scp`) y levántala ahí. Sigue exactamente donde quedó, y lo que entró a Plex mientras estaba apagada se notifica al arrancar.

No dejes las dos copias corriendo a la vez: cada aviso llegaría duplicado.

## Licencia

Plex Notify es software libre bajo la [Licencia Apache 2.0](LICENSE). Puedes usarlo, modificarlo, hacer forks y redistribuirlo, también con fines comerciales, siempre que:

- conserves los archivos `LICENSE` y `NOTICE` en tu copia o versión derivada, con el crédito al proyecto original: **Plex Notify de [KqK.cl](https://kqk.cl)** — <https://github.com/r34lcl/Plex-Notify>;
- indiques en los archivos que modifiques que fueron cambiados.

Se entrega «tal cual», sin garantías. Ver el texto completo en `LICENSE`.

Plex Notify no está afiliado a Plex Inc. "Plex" es una marca de sus respectivos dueños.
