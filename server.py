"""
server.py — Serveur central PC Monitor.

Lancement :
    python server.py

Expose :
- un dashboard HTML ;
- une API REST protégée ;
- des événements temps réel via Flask-SocketIO.
"""

import logging
import socket
import threading
import time

from flask import Response

from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_socketio import SocketIO

import auth
import config
import database
import wol


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [server] %(levelname)s %(message)s",
)

logger = logging.getLogger("pcmonitor.server")


app = Flask(__name__)
app.secret_key = config.get_flask_secret_key()
app.permanent_session_lifetime = 60 * 60 * 12

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="threading",
)

database.init_db()

# ---------------------------------------------------------------------------
# PARTAGE D'ÉCRAN
# ---------------------------------------------------------------------------

screen_frames = {}
screen_lock = threading.Lock()


def set_screen_frame(device_id, frame):
    with screen_lock:
        screen_frames[device_id] = frame


def get_screen_frame(device_id):
    with screen_lock:
        return screen_frames.get(device_id)


def clear_screen_frame(device_id):
    with screen_lock:
        screen_frames.pop(device_id, None)


# ---------------------------------------------------------------------------
# DEMANDER LE DÉMARRAGE
# ---------------------------------------------------------------------------

@app.route(
    "/api/devices/<device_id>/screen/start",
    methods=["POST"]
)
@auth.api_login_required
def api_screen_start(device_id):

    device = database.get_device(device_id)

    if not device:
        return jsonify({
            "error": "Appareil introuvable."
        }), 404

    if device["revoked"]:
        return jsonify({
            "error": "Appareil révoqué."
        }), 403

    command_id = database.insert_command(
        device_id,
        device["name"],
        "screen_start",
        "pending",
        auth.current_username(),
        "Démarrage du partage d'écran"
    )

    database.queue_agent_command(
        device_id,
        command_id,
        "screen_start"
    )

    logger.info(
        "Demande de partage d'écran : %s",
        device_id
    )

    socketio.emit(
        "screen_status",
        {
            "device_id": device_id,
            "active": True,
            "state": "requested"
        }
    )

    return jsonify({
        "success": True,
        "command_id": command_id,
        "message": "Partage d'écran demandé à l'agent."
    })


# ---------------------------------------------------------------------------
# DEMANDER L'ARRÊT
# ---------------------------------------------------------------------------

@app.route(
    "/api/devices/<device_id>/screen/stop",
    methods=["POST"]
)
@auth.api_login_required
def api_screen_stop(device_id):

    device = database.get_device(device_id)

    if not device:
        return jsonify({
            "error": "Appareil introuvable."
        }), 404

    command_id = database.insert_command(
        device_id,
        device["name"],
        "screen_stop",
        "pending",
        auth.current_username(),
        "Arrêt du partage d'écran"
    )

    database.queue_agent_command(
        device_id,
        command_id,
        "screen_stop"
    )

    clear_screen_frame(device_id)

    socketio.emit(
        "screen_status",
        {
            "device_id": device_id,
            "active": False,
            "state": "stopped"
        }
    )

    logger.info(
        "Arrêt du partage d'écran : %s",
        device_id
    )

    return jsonify({
        "success": True,
        "command_id": command_id,
        "message": "Arrêt du partage d'écran demandé."
    })


# ---------------------------------------------------------------------------
# RÉCEPTION D'UNE IMAGE DEPUIS L'AGENT
# ---------------------------------------------------------------------------

@app.route(
    "/api/devices/<device_id>/screen/frame",
    methods=["POST"]
)
@auth.agent_auth_required
def api_screen_frame(device_id):

    # Vérification supplémentaire :
    # l'appareil authentifié doit correspondre à l'URL.
    verified_device_id = getattr(
        request,
        "verified_device_id",
        None
    )

    if verified_device_id != device_id:
        return jsonify({
            "error": "Appareil non autorisé."
        }), 403

    if "frame" not in request.files:
        return jsonify({
            "error": "Image manquante."
        }), 400

    frame = request.files["frame"].read()

    if not frame:
        return jsonify({
            "error": "Image vide."
        }), 400

    # 5 Mo maximum
    if len(frame) > 5 * 1024 * 1024:
        return jsonify({
            "error": "Image trop volumineuse."
        }), 413

    set_screen_frame(
        device_id,
        frame
    )

    return jsonify({
        "success": True
    })


# ---------------------------------------------------------------------------
# RÉCUPÉRATION D'UNE IMAGE
# ---------------------------------------------------------------------------

@app.route(
    "/api/devices/<device_id>/screen/frame",
    methods=["GET"]
)
@auth.api_login_required
def api_screen_frame_get(device_id):

    device = database.get_device(device_id)

    if not device:
        return jsonify({
            "error": "Appareil introuvable."
        }), 404

    frame = get_screen_frame(device_id)

    if not frame:
        return jsonify({
            "error": "Aucune image disponible."
        }), 404

    return Response(
        frame,
        mimetype="image/jpeg",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )


# ---------------------------------------------------------------------------
# STREAM MJPEG
# ---------------------------------------------------------------------------

@app.route(
    "/api/devices/<device_id>/screen/stream"
)
@auth.api_login_required
def api_screen_stream(device_id):

    device = database.get_device(device_id)

    if not device:
        return jsonify({
            "error": "Appareil introuvable."
        }), 404

    def generate():

        last_frame = None

        while True:

            frame = get_screen_frame(
                device_id
            )

            if frame and frame != last_frame:

                last_frame = frame

                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Cache-Control: no-cache\r\n"
                    b"\r\n"
                    + frame
                    + b"\r\n"
                )

            time.sleep(0.08)

    return Response(
        generate(),
        mimetype=(
            "multipart/x-mixed-replace;"
            " boundary=frame"
        ),
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache"
        }
    )
# ---------------------------------------------------------------------------
# UTILITAIRES
# ---------------------------------------------------------------------------

def get_local_server_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        finally:
            s.close()

    except Exception:
        return "127.0.0.1"


def device_to_dict(device, include_metrics=True):
    d = dict(device)

    d["wol_enabled"] = bool(d["wol_enabled"])
    d["autostart_enabled"] = bool(d["autostart_enabled"])
    d["revoked"] = bool(d["revoked"])

    if include_metrics:

        latest = database.get_latest_metric(device["id"])

        if latest:

            d["cpu_percent"] = latest["cpu_percent"]
            d["ram_percent"] = latest["ram_percent"]
            d["disk_percent"] = latest["disk_percent"]
            d["battery_percent"] = latest["battery_percent"]

        else:

            d["cpu_percent"] = None
            d["ram_percent"] = None
            d["disk_percent"] = None
            d["battery_percent"] = None

    return d


# ---------------------------------------------------------------------------
# ALERTES
# ---------------------------------------------------------------------------

def check_and_raise_alerts(device_id, device_name, payload):

    cpu_th = float(
        database.get_setting(
            "cpu_threshold",
            config.DEFAULT_CPU_THRESHOLD
        )
    )

    ram_th = float(
        database.get_setting(
            "ram_threshold",
            config.DEFAULT_RAM_THRESHOLD
        )
    )

    disk_th = float(
        database.get_setting(
            "disk_threshold",
            config.DEFAULT_DISK_THRESHOLD
        )
    )

    batt_th = float(
        database.get_setting(
            "battery_threshold",
            config.DEFAULT_BATTERY_THRESHOLD
        )
    )

    cpu = payload.get("cpu", {}).get("percent")
    ram = payload.get("ram", {}).get("percent")
    disk = payload.get("disk_percent_avg")
    battery = payload.get("battery", {})

    new_alerts = []

    def maybe_alert(alert_type, value, threshold, message):

        if value is None:
            return

        if value >= threshold:

            if not database.get_recent_alert(
                device_id,
                alert_type,
                within_seconds=60
            ):

                database.insert_alert(
                    device_id,
                    device_name,
                    alert_type,
                    message,
                    value
                )

                new_alerts.append({
                    "device_id": device_id,
                    "device_name": device_name,
                    "type": alert_type,
                    "message": message,
                    "value": value,
                    "timestamp": time.time(),
                })

    maybe_alert(
        "cpu",
        cpu,
        cpu_th,
        f"CPU à {cpu:.0f}%" if cpu is not None else ""
    )

    maybe_alert(
        "ram",
        ram,
        ram_th,
        f"RAM à {ram:.0f}%" if ram is not None else ""
    )

    maybe_alert(
        "disk",
        disk,
        disk_th,
        f"Disque à {disk:.0f}%" if disk is not None else ""
    )

    # Batterie faible uniquement lorsque le PC n'est pas branché.
    if battery.get("available") and battery.get("plugged_in") is False:

        b_percent = battery.get("percent")

        if (
            b_percent is not None
            and b_percent <= batt_th
            and not database.get_recent_alert(
                device_id,
                "battery",
                within_seconds=300
            )
        ):

            msg = f"Batterie faible ({b_percent:.0f}%)"

            database.insert_alert(
                device_id,
                device_name,
                "battery",
                msg,
                b_percent
            )

            new_alerts.append({
                "device_id": device_id,
                "device_name": device_name,
                "type": "battery",
                "message": msg,
                "value": b_percent,
                "timestamp": time.time(),
            })

    for alert in new_alerts:
        socketio.emit("new_alert", alert)

    return new_alerts


# ---------------------------------------------------------------------------
# PAGES HTML
# ---------------------------------------------------------------------------

@app.route("/")
@auth.login_required
def index():
    return redirect(url_for("dashboard"))


@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "GET":

        return render_template(
            "login.html",
            error=None,
            needs_setup=not database.any_user_exists()
        )

    username = request.form.get(
        "username",
        ""
    ).strip()

    password = request.form.get(
        "password",
        ""
    )

    if not username or not password:

        return render_template(
            "login.html",
            error="Nom d'utilisateur et mot de passe requis.",
            needs_setup=not database.any_user_exists()
        )

    # Première utilisation :
    # création du compte administrateur.
    if not database.any_user_exists():

        database.create_user(
            username,
            auth.hash_password(password)
        )

        auth.login_user(username)

        return redirect(url_for("dashboard"))

    user = database.get_user_by_username(username)

    if (
        not user
        or not auth.verify_password(
            password,
            user["password_hash"]
        )
    ):

        return render_template(
            "login.html",
            error="Identifiants incorrects.",
            needs_setup=False
        )

    auth.login_user(username)

    return redirect(url_for("dashboard"))


@app.route("/logout")
def logout():

    auth.logout_user()

    return redirect(url_for("login"))


@app.route("/dashboard")
@auth.login_required
def dashboard():

    return render_template(
        "dashboard.html",
        username=auth.current_username(),
        server_ip=get_local_server_ip(),
        server_port=config.SERVER_PORT
    )


@app.route("/device/<device_id>")
@auth.login_required
def device_page(device_id):

    device = database.get_device(device_id)

    if not device:
        return redirect(url_for("dashboard"))

    return render_template(
        "device.html",
        device=device_to_dict(device),
        username=auth.current_username()
    )


# ---------------------------------------------------------------------------
# API — APPAREILS
# ---------------------------------------------------------------------------

@app.route("/api/devices")
@auth.api_login_required
def api_devices():

    devices = [
        device_to_dict(d)
        for d in database.get_all_devices()
    ]

    online = sum(
        1
        for d in devices
        if d["status"] == "online"
    )

    return jsonify({
        "devices": devices,
        "total": len(devices),
        "online": online,
        "offline": len(devices) - online,
    })


@app.route("/api/devices/<device_id>")
@auth.api_login_required
def api_device_detail(device_id):

    device = database.get_device(device_id)

    if not device:
        return jsonify({
            "error": "appareil introuvable"
        }), 404

    history = database.get_metric_history(
        device_id,
        limit=60
    )

    history_out = []

    for row in history:

        history_out.append({
            "timestamp": row["timestamp"],
            "cpu_percent": row["cpu_percent"],
            "ram_percent": row["ram_percent"],
            "disk_percent": row["disk_percent"],
            "battery_percent": row["battery_percent"],
        })

    latest = database.get_latest_metric(device_id)

    latest_payload = None

    if latest and latest["payload"]:

        import json

        latest_payload = json.loads(
            latest["payload"]
        )

    token_row = database.get_token_for_device(
        device_id
    )

    return jsonify({
        "device": device_to_dict(device),
        "history": history_out,
        "latest_payload": latest_payload,
        "token_masked": "*" * 8 if token_row else None,
    })


@app.route(
    "/api/devices/<device_id>/rename",
    methods=["POST"]
)
@auth.api_login_required
def api_rename_device(device_id):

    new_name = (
        request.json or {}
    ).get(
        "name",
        ""
    ).strip()

    if not new_name:
        return jsonify({
            "error": "nom invalide"
        }), 400

    if not database.get_device(device_id):
        return jsonify({
            "error": "appareil introuvable"
        }), 404

    database.rename_device(
        device_id,
        new_name
    )

    return jsonify({
        "success": True
    })


@app.route(
    "/api/devices/<device_id>/revoke",
    methods=["POST"]
)
@auth.api_login_required
def api_revoke_device(device_id):

    if not database.get_device(device_id):

        return jsonify({
            "error": "appareil introuvable"
        }), 404

    database.revoke_device_token(
        device_id
    )

    return jsonify({
        "success": True
    })


@app.route(
    "/api/devices/<device_id>/uninstall",
    methods=["POST"]
)
@auth.api_login_required
def api_uninstall_device(device_id):

    if not database.get_device(device_id):

        return jsonify({
            "error": "appareil introuvable"
        }), 404

    database.revoke_device_token(
        device_id
    )

    database.delete_device(
        device_id
    )

    return jsonify({
        "success": True
    })


@app.route(
    "/api/devices/<device_id>/wol_toggle",
    methods=["POST"]
)
@auth.api_login_required
def api_toggle_wol(device_id):

    enabled = bool(
        (request.json or {}).get(
            "enabled",
            True
        )
    )

    if not database.get_device(device_id):

        return jsonify({
            "error": "appareil introuvable"
        }), 404

    database.set_device_wol(
        device_id,
        enabled
    )

    return jsonify({
        "success": True
    })


# ---------------------------------------------------------------------------
# COMMANDES D'ALIMENTATION
# ---------------------------------------------------------------------------

def _queue_power_command(device_id, action):

    device = database.get_device(device_id)

    if not device:
        return None, (
            "appareil introuvable",
            404
        )

    if device["revoked"]:
        return None, (
            "appareil révoqué",
            403
        )

    command_id = database.insert_command(
        device_id,
        device["name"],
        action,
        "pending",
        auth.current_username()
    )

    database.queue_agent_command(
        device_id,
        command_id,
        action
    )

    socketio.emit(
        "command_queued",
        {
            "device_id": device_id,
            "action": action
        }
    )

    return command_id, None


@app.route(
    "/api/devices/<device_id>/shutdown",
    methods=["POST"]
)
@auth.api_login_required
def api_shutdown(device_id):

    command_id, error = _queue_power_command(
        device_id,
        "shutdown"
    )

    if error:
        return jsonify({
            "error": error[0]
        }), error[1]

    return jsonify({
        "success": True,
        "message": "Commande d'arrêt envoyée à l'appareil.",
        "command_id": command_id
    })


@app.route(
    "/api/devices/<device_id>/restart",
    methods=["POST"]
)
@auth.api_login_required
def api_restart(device_id):

    command_id, error = _queue_power_command(
        device_id,
        "restart"
    )

    if error:
        return jsonify({
            "error": error[0]
        }), error[1]

    return jsonify({
        "success": True,
        "message": "Commande de redémarrage envoyée à l'appareil.",
        "command_id": command_id
    })


@app.route(
    "/api/devices/<device_id>/wake",
    methods=["POST"]
)
@auth.api_login_required
def api_wake(device_id):

    device = database.get_device(device_id)

    if not device:
        return jsonify({
            "error": "appareil introuvable"
        }), 404

    if not device["wol_enabled"]:
        return jsonify({
            "error": "Wake-on-LAN désactivé pour cet appareil."
        }), 400

    mac = device["mac_address"]

    if not wol.is_valid_mac(mac or ""):

        database.insert_command(
            device_id,
            device["name"],
            "wake",
            "failed",
            auth.current_username(),
            "Adresse MAC invalide ou inconnue."
        )

        return jsonify({
            "error": "Wake-on-LAN indisponible.",
            "details": [
                "BIOS/UEFI",
                "carte réseau",
                "paramètres Windows",
                "alimentation",
                "connexion réseau"
            ]
        }), 400

    sent = wol.send_magic_packet(mac)

    status = "sent" if sent else "failed"

    result_msg = (
        "Paquet Wake-on-LAN envoyé."
        if sent
        else
        "Échec de l'envoi du paquet Wake-on-LAN."
    )

    database.insert_command(
        device_id,
        device["name"],
        "wake",
        status,
        auth.current_username(),
        result_msg
    )

    if not sent:

        return jsonify({
            "error": "Wake-on-LAN indisponible.",
            "details": [
                "BIOS/UEFI",
                "carte réseau",
                "paramètres Windows",
                "alimentation",
                "connexion réseau"
            ]
        }), 400

    return jsonify({
        "success": True,
        "message": "Paquet Wake-on-LAN envoyé."
    })


# ---------------------------------------------------------------------------
# MODE URGENCE PANIC98
# ---------------------------------------------------------------------------

@app.route(
    "/api/devices/<device_id>/emergency/verify",
    methods=["POST"]
)
@auth.api_login_required
def api_emergency_verify(device_id):

    username = auth.current_username()

    lock = database.get_emergency_lock(
        username
    )

    if lock and lock["locked_until"] > time.time():

        remaining = int(
            lock["locked_until"] - time.time()
        )

        return jsonify({
            "error": (
                f"Trop de tentatives incorrectes. "
                f"Réessayez dans {remaining}s."
            )
        }), 429

    code = (
        request.json or {}
    ).get(
        "code",
        ""
    )

    if code != config.EMERGENCY_CODE:

        database.register_emergency_failure(
            username
        )

        return jsonify({
            "error": "Code incorrect. Aucune action effectuée."
        }), 403

    database.reset_emergency_failures(
        username
    )

    device = database.get_device(
        device_id
    )

    if not device:

        return jsonify({
            "error": "appareil introuvable"
        }), 404

    return jsonify({
        "success": True,
        "device_name": device["name"]
    })


@app.route(
    "/api/devices/<device_id>/emergency/confirm",
    methods=["POST"]
)
@auth.api_login_required
def api_emergency_confirm(device_id):

    username = auth.current_username()

    lock = database.get_emergency_lock(
        username
    )

    if lock and lock["locked_until"] > time.time():

        remaining = int(
            lock["locked_until"] - time.time()
        )

        return jsonify({
            "error": (
                f"Trop de tentatives incorrectes. "
                f"Réessayez dans {remaining}s."
            )
        }), 429

    code = (
        request.json or {}
    ).get(
        "code",
        ""
    )

    if code != config.EMERGENCY_CODE:

        database.register_emergency_failure(
            username
        )

        return jsonify({
            "error": "Code incorrect. Aucune action effectuée."
        }), 403

    device = database.get_device(
        device_id
    )

    if not device:

        return jsonify({
            "error": "appareil introuvable"
        }), 404

    if device["revoked"]:

        return jsonify({
            "error": "appareil révoqué"
        }), 403

    command_id = database.insert_command(
        device_id,
        device["name"],
        "emergency_shutdown",
        "pending",
        username,
        "Mode urgence PANIC98 déclenché"
    )

    database.queue_agent_command(
        device_id,
        command_id,
        "emergency_shutdown"
    )

    socketio.emit(
        "command_queued",
        {
            "device_id": device_id,
            "action": "emergency_shutdown"
        }
    )

    return jsonify({
        "success": True,
        "message": "Procédure d'urgence envoyée à l'appareil."
    })


# ---------------------------------------------------------------------------
# ALERTES / HISTORIQUE
# ---------------------------------------------------------------------------

@app.route("/api/alerts")
@auth.api_login_required
def api_alerts():

    alerts = [
        dict(a)
        for a in database.get_alerts(limit=200)
    ]

    return jsonify({
        "alerts": alerts
    })


@app.route("/api/history")
@auth.api_login_required
def api_history():

    commands = [
        dict(c)
        for c in database.get_command_history(
            limit=200
        )
    ]

    return jsonify({
        "commands": commands
    })


# ---------------------------------------------------------------------------
# PARAMÈTRES
# ---------------------------------------------------------------------------

@app.route(
    "/api/settings",
    methods=["GET", "POST"]
)
@auth.api_login_required
def api_settings():

    if request.method == "GET":

        return jsonify(
            database.get_all_settings()
        )

    data = request.json or {}

    allowed_keys = {
        "server_name",
        "collect_interval",
        "port",
        "cpu_threshold",
        "ram_threshold",
        "disk_threshold",
        "battery_threshold",
    }

    for key, value in data.items():

        if key in allowed_keys:

            database.set_setting(
                key,
                value
            )

    return jsonify({
        "success": True
    })


@app.route("/api/server_info")
@auth.api_login_required
def api_server_info():

    return jsonify({
        "ip": get_local_server_ip(),
        "port": config.SERVER_PORT
    })


# ---------------------------------------------------------------------------
# API AGENTS
# ---------------------------------------------------------------------------

@app.route(
    "/api/register",
    methods=["POST"]
)
def api_register():

    data = request.json or {}

    device_id = data.get(
        "device_id"
    )

    if not device_id:

        return jsonify({
            "error": "device_id manquant"
        }), 400

    existing = database.get_device(
        device_id
    )

    if existing and existing["revoked"]:

        return jsonify({
            "error": (
                "cet appareil a été révoqué "
                "par l'administrateur"
            )
        }), 403

    database.upsert_device(
        device_id=device_id,
        name=(
            data.get("name")
            or data.get("hostname")
            or f"PC-{device_id[:8]}"
        ),
        hostname=data.get("hostname"),
        os_name=data.get("os_name"),
        os_version=data.get("os_version"),
        architecture=data.get("architecture"),
        mac_address=data.get("mac_address"),
        last_ip=data.get("last_ip"),
    )

    token = database.create_device_token(
        device_id
    )

    logger.info(
        "Nouvel appareil enregistré : %s (%s)",
        data.get("hostname"),
        device_id
    )

    socketio.emit(
        "device_registered",
        {
            "device_id": device_id
        }
    )

    return jsonify({
        "success": True,
        "device_token": token
    })


@app.route(
    "/api/telemetry",
    methods=["POST"]
)
@auth.agent_auth_required
def api_telemetry():

    device_id = request.verified_device_id

    payload = request.json or {}

    device = database.get_device(
        device_id
    )

    if not device:

        return jsonify({
            "error": "appareil introuvable"
        }), 404

    database.touch_device_seen(
        device_id
    )

    # Mise à jour IP / MAC.
    if (
        payload.get("last_ip")
        or payload.get("mac_address")
    ):

        database.upsert_device(
            device_id=device_id,
            name=device["name"],
            hostname=payload.get(
                "system",
                {}
            ).get(
                "hostname",
                device["hostname"]
            ),
            os_name=payload.get(
                "system",
                {}
            ).get(
                "os_name",
                device["os_name"]
            ),
            os_version=payload.get(
                "system",
                {}
            ).get(
                "os_version",
                device["os_version"]
            ),
            architecture=payload.get(
                "system",
                {}
            ).get(
                "architecture",
                device["architecture"]
            ),
            mac_address=payload.get(
                "mac_address",
                device["mac_address"]
            ),
            last_ip=payload.get(
                "last_ip",
                device["last_ip"]
            ),
        )

    cpu = payload.get(
        "cpu",
        {}
    ).get(
        "percent"
    )

    ram = payload.get(
        "ram",
        {}
    ).get(
        "percent"
    )

    disk = payload.get(
        "disk_percent_avg"
    )

    battery_data = payload.get(
        "battery",
        {}
    )

    battery = (
        battery_data.get("percent")
        if battery_data.get("available")
        else None
    )

    database.insert_metric(
        device_id,
        cpu,
        ram,
        disk,
        battery,
        payload
    )

    alerts = check_and_raise_alerts(
        device_id,
        device["name"],
        payload
    )

    socketio.emit(
        "telemetry_update",
        {
            "device_id": device_id,
            "cpu_percent": cpu,
            "ram_percent": ram,
            "disk_percent": disk,
            "battery_percent": battery,
            "status": "online",
            "timestamp": payload.get(
                "timestamp",
                time.time()
            ),
        }
    )

    # -------------------------------------------------------
    # COMMANDES EN ATTENTE
    # -------------------------------------------------------

    pending = database.pop_pending_commands_for_device(
        device_id
    )

    pending_out = []

    for command in pending:

        database.update_command_status(
            command["command_id"],
            "sent",
            "Commande transmise à l'agent."
        )

        pending_out.append({
            "action": command["action"],
            "command_id": command["command_id"],
        })

        socketio.emit(
            "command_sent",
            {
                "device_id": device_id,
                "action": command["action"],
            }
        )

    return jsonify({
        "success": True,
        "pending_commands": pending_out,
        "alerts_raised": len(alerts),
    })


# ---------------------------------------------------------------------------
# RÉSULTAT DE COMMANDE
# ---------------------------------------------------------------------------

@app.route(
    "/api/devices/<device_id>/command_result",
    methods=["POST"]
)
@auth.agent_auth_required
def api_command_result(device_id):

    data = request.json or {}

    command_id = data.get(
        "command_id"
    )

    success = data.get(
        "success",
        False
    )

    message = data.get(
        "message",
        ""
    )

    if command_id:

        database.update_command_status(
            command_id,
            "success" if success else "failed",
            message
        )

    return jsonify({
        "success": True
    })


# ---------------------------------------------------------------------------
# DÉTECTION HORS LIGNE
# ---------------------------------------------------------------------------

def offline_watcher():

    while True:

        try:

            newly_offline = (
                database.mark_stale_devices_offline(
                    config.OFFLINE_THRESHOLD_SECONDS
                )
            )

            for device_id in newly_offline:

                device = database.get_device(
                    device_id
                )

                device_name = (
                    device["name"]
                    if device
                    else device_id
                )

                database.insert_alert(
                    device_id,
                    device_name,
                    "offline",
                    "Appareil hors ligne"
                )

                socketio.emit(
                    "device_offline",
                    {
                        "device_id": device_id,
                        "device_name": device_name,
                    }
                )

        except Exception:

            logger.exception(
                "Erreur dans le thread de détection hors-ligne"
            )

        time.sleep(3)


# ---------------------------------------------------------------------------
# SOCKETIO
# ---------------------------------------------------------------------------

@socketio.on("connect")
def on_connect():

    logger.debug(
        "Client dashboard connecté en WebSocket."
    )


# ---------------------------------------------------------------------------
# POINT D'ENTRÉE
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    watcher_thread = threading.Thread(
        target=offline_watcher,
        daemon=True
    )

    watcher_thread.start()

    local_ip = get_local_server_ip()

    print(
        "PC Monitor démarré. Dashboard accessible sur :"
    )

    print(
        f"  http://{local_ip}:{config.SERVER_PORT}"
    )

    socketio.run(
        app,
        host=config.SERVER_HOST,
        port=config.SERVER_PORT,
        debug=False,
        allow_unsafe_werkzeug=True
    )