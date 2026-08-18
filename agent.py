"""
agent.py — Agent de supervision PC Monitor

Fonctions :
- identification de l'appareil
- enregistrement auprès du serveur
- télémétrie CPU / RAM / disques / batterie / température / réseau
- réception de commandes
- arrêt
- redémarrage
- arrêt d'urgence
- partage d'écran explicite

Le partage d'écran ne démarre QUE lorsqu'une commande
screen_start est reçue depuis le serveur.
"""

import io
import json
import logging
import os
import platform
import socket
import sys
import threading
import time
import uuid

from PIL import ImageGrab

import psutil
import requests

import config
import power


# ============================================================
# PARTAGE D'ÉCRAN
# ============================================================

screen_sharing = False
screen_thread = None
screen_lock = threading.Lock()


def is_screen_sharing():
    with screen_lock:
        return screen_sharing


def set_screen_sharing(enabled):
    global screen_sharing

    with screen_lock:
        screen_sharing = bool(enabled)


def capture_screen():
    """
    Capture l'écran uniquement lorsque le partage
    a été explicitement activé.
    """

    image = ImageGrab.grab()

    # Réduction de la résolution
    max_width = 1280

    if image.width > max_width:

        ratio = max_width / image.width

        new_size = (
            max_width,
            int(image.height * ratio)
        )

        image = image.resize(
            new_size
        )

    buffer = io.BytesIO()

    image.convert("RGB").save(
        buffer,
        format="JPEG",
        quality=70
    )

    return buffer.getvalue()


def screen_share_loop(
    server_url,
    device_id,
    token
):
    """
    Envoie régulièrement les images capturées
    au serveur.
    """

    logger.info(
        "Partage d'écran activé."
    )

    while is_screen_sharing():

        try:

            frame = capture_screen()

            headers = {
                "X-Device-Id": device_id,
                "X-Device-Token": token,
            }

            response = requests.post(
                f"{server_url}/api/devices/"
                f"{device_id}/screen/frame",

                files={
                    "frame": (
                        "screen.jpg",
                        frame,
                        "image/jpeg"
                    )
                },

                headers=headers,

                timeout=5
            )

            if response.status_code in (401, 403):

                logger.error(
                    "Authentification refusée "
                    "pendant le partage d'écran."
                )

                set_screen_sharing(False)
                break

            response.raise_for_status()

        except Exception as exc:

            logger.warning(
                "Erreur partage d'écran : %s",
                exc
            )

        # Environ 4 images/seconde
        time.sleep(0.25)

    logger.info(
        "Partage d'écran arrêté."
    )


def start_screen_sharing(
    server_url,
    device_id,
    token
):
    """
    Démarre le thread de partage d'écran.
    """

    global screen_thread

    if is_screen_sharing():

        logger.info(
            "Partage d'écran déjà actif."
        )

        return

    set_screen_sharing(True)

    screen_thread = threading.Thread(
        target=screen_share_loop,
        args=(
            server_url,
            device_id,
            token
        ),
        daemon=True,
        name="ScreenShareThread"
    )

    screen_thread.start()


def stop_screen_sharing():
    """
    Arrête le partage d'écran.
    """

    if not is_screen_sharing():
        return

    set_screen_sharing(False)

    logger.info(
        "Arrêt du partage d'écran demandé."
    )


# ============================================================
# CONFIGURATION LOGGING
# ============================================================

os.makedirs(
    config.AGENT_DATA_DIR,
    exist_ok=True
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [agent] %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),

        logging.FileHandler(
            os.path.join(
                config.AGENT_DATA_DIR,
                "agent.log"
            ),
            encoding="utf-8"
        ),
    ],
)

logger = logging.getLogger(
    "pcmonitor.agent"
)


# ============================================================
# FICHIERS
# ============================================================

TOKEN_FILE = os.path.join(
    config.AGENT_DATA_DIR,
    "token.json"
)


# ============================================================
# IDENTITÉ
# ============================================================

def load_device_id() -> str:

    if not os.path.exists(
        config.IDENTITY_FILE
    ):

        raise FileNotFoundError(
            f"Fichier identité introuvable : "
            f"{config.IDENTITY_FILE}"
        )

    with open(
        config.IDENTITY_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        data = json.load(f)

    device_id = data.get(
        "device_id"
    )

    if not device_id:

        raise RuntimeError(
            "device_id absent du fichier identité."
        )

    return device_id


# ============================================================
# TOKEN
# ============================================================

def load_saved_token():

    if not os.path.exists(
        TOKEN_FILE
    ):
        return None

    try:

        with open(
            TOKEN_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            data = json.load(f)

        return data.get(
            "device_token"
        )

    except Exception as exc:

        logger.warning(
            "Impossible de lire le token : %s",
            exc
        )

        return None


def save_token(token: str):

    os.makedirs(
        config.AGENT_DATA_DIR,
        exist_ok=True
    )

    with open(
        TOKEN_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            {
                "device_token": token
            },
            f,
            indent=2
        )


# ============================================================
# RÉSEAU / IDENTIFICATION
# ============================================================

def get_mac_address() -> str:

    mac_int = uuid.getnode()

    mac = ":".join(
        f"{(mac_int >> ele) & 0xff:02x}"
        for ele in range(
            40,
            -8,
            -8
        )
    )

    return mac.upper()


def get_local_ip() -> str:

    try:

        sock = socket.socket(
            socket.AF_INET,
            socket.SOCK_DGRAM
        )

        sock.settimeout(0.5)

        try:

            sock.connect(
                ("8.8.8.8", 80)
            )

            return sock.getsockname()[0]

        finally:

            sock.close()

    except Exception:

        try:

            return socket.gethostbyname(
                socket.gethostname()
            )

        except Exception:

            return "127.0.0.1"


# ============================================================
# INFORMATIONS STATIQUES
# ============================================================

def static_device_info(
    device_id: str
) -> dict:

    return {

        "device_id": device_id,

        "name": platform.node(),

        "hostname": platform.node(),

        "os_name": platform.system(),

        "os_version": platform.version(),

        "architecture": platform.machine(),

        "mac_address": get_mac_address(),

        "last_ip": get_local_ip(),
    }


# ============================================================
# CPU
# ============================================================

def collect_cpu() -> dict:

    try:

        frequency = psutil.cpu_freq()

    except Exception:

        frequency = None

    try:

        cpu_percent = psutil.cpu_percent(
            interval=0.3
        )

    except Exception:

        cpu_percent = None

    return {

        "percent": cpu_percent,

        "cores_physical": (
            psutil.cpu_count(
                logical=False
            )
            or None
        ),

        "cores_logical": (
            psutil.cpu_count(
                logical=True
            )
            or None
        ),

        "frequency_mhz": (
            round(
                frequency.current,
                0
            )
            if frequency
            else None
        ),
    }


# ============================================================
# RAM
# ============================================================

def collect_ram() -> dict:

    vm = psutil.virtual_memory()

    return {

        "percent": vm.percent,

        "total_bytes": vm.total,

        "used_bytes": vm.used,

        "available_bytes": vm.available,
    }


# ============================================================
# DISQUES
# ============================================================

def collect_disks() -> list:

    disks = []

    try:

        partitions = psutil.disk_partitions(
            all=False
        )

    except Exception as exc:

        logger.warning(
            "Impossible de récupérer les partitions : %s",
            exc
        )

        return disks

    for partition in partitions:

        try:

            usage = psutil.disk_usage(
                partition.mountpoint
            )

        except (
            PermissionError,
            OSError
        ):

            continue

        disks.append(
            {

                "letter": partition.device,

                "total_bytes": usage.total,

                "used_bytes": usage.used,

                "free_bytes": usage.free,

                "percent": usage.percent,
            }
        )

    return disks


# ============================================================
# BATTERIE
# ============================================================

def collect_battery() -> dict:

    try:

        battery = psutil.sensors_battery()

    except Exception:

        battery = None

    if battery is None:

        return {
            "available": False
        }

    seconds_left = battery.secsleft

    time_left = None

    if (
        seconds_left
        and seconds_left != psutil.POWER_TIME_UNLIMITED
        and seconds_left > 0
    ):

        hours, remainder = divmod(
            seconds_left,
            3600
        )

        minutes, _ = divmod(
            remainder,
            60
        )

        time_left = (
            f"{int(hours)}h"
            f"{int(minutes):02d}"
        )

    return {

        "available": True,

        "percent": battery.percent,

        "plugged_in": battery.power_plugged,

        "time_left": time_left,
    }


# ============================================================
# TEMPÉRATURE
# ============================================================

def collect_temperature() -> dict:

    try:

        temperatures = (
            psutil.sensors_temperatures()
        )

    except Exception:

        temperatures = None

    if not temperatures:

        return {
            "available": False
        }

    for name, entries in temperatures.items():

        for entry in entries:

            if entry.current is not None:

                return {

                    "available": True,

                    "celsius": entry.current,

                    "label": (
                        entry.label
                        or name
                    ),
                }

    return {
        "available": False
    }


# ============================================================
# RÉSEAU
# ============================================================

def collect_network() -> list:

    interfaces = []

    try:

        stats = psutil.net_if_stats()

        addresses = psutil.net_if_addrs()

    except Exception as exc:

        logger.warning(
            "Impossible de récupérer le réseau : %s",
            exc
        )

        return interfaces

    for interface_name, interface_addresses in (
        addresses.items()
    ):

        stat = stats.get(
            interface_name
        )

        ipv4 = next(
            (
                address.address
                for address in interface_addresses
                if address.family == socket.AF_INET
            ),
            None
        )

        if not ipv4:
            continue

        mac = None

        if hasattr(
            psutil,
            "AF_LINK"
        ):

            mac = next(
                (
                    address.address
                    for address in interface_addresses
                    if address.family == psutil.AF_LINK
                ),
                None
            )

        interfaces.append(
            {

                "name": interface_name,

                "ip": ipv4,

                "mac": mac,

                "up": (
                    bool(stat.isup)
                    if stat
                    else None
                ),

                "speed_mbps": (
                    stat.speed
                    if stat
                    else None
                ),
            }
        )

    return interfaces


# ============================================================
# PROCESSUS
# ============================================================

def collect_processes() -> dict:

    try:

        process_count = len(
            psutil.pids()
        )

    except Exception:

        process_count = None

    try:

        cpu_percent = psutil.cpu_percent(
            interval=None
        )

    except Exception:

        cpu_percent = None

    try:

        ram_percent = (
            psutil.virtual_memory().percent
        )

    except Exception:

        ram_percent = None

    return {

        "count": process_count,

        "cpu_percent": cpu_percent,

        "ram_percent": ram_percent,
    }


# ============================================================
# SYSTÈME
# ============================================================

def collect_system() -> dict:

    try:

        boot_time = psutil.boot_time()

        uptime_seconds = int(
            time.time() - boot_time
        )

    except Exception:

        uptime_seconds = None

    return {

        "hostname": platform.node(),

        "os_name": platform.system(),

        "os_version": platform.version(),

        "architecture": platform.machine(),

        "python_version": platform.python_version(),

        "uptime_seconds": uptime_seconds,
    }


# ============================================================
# TÉLÉMÉTRIE
# ============================================================

def build_telemetry_payload(
    device_id: str
) -> dict:

    disks = collect_disks()

    if disks:

        disk_percent_avg = round(
            sum(
                disk["percent"]
                for disk in disks
            )
            / len(disks),
            1
        )

    else:

        disk_percent_avg = None

    return {

        "device_id": device_id,

        "timestamp": time.time(),

        "cpu": collect_cpu(),

        "ram": collect_ram(),

        "disks": disks,

        "disk_percent_avg": disk_percent_avg,

        "battery": collect_battery(),

        "temperature": collect_temperature(),

        "network": collect_network(),

        "processes": collect_processes(),

        "system": collect_system(),

        "mac_address": get_mac_address(),

        "last_ip": get_local_ip(),
    }


# ============================================================
# ENREGISTREMENT
# ============================================================

def register_device(
    device_id: str,
    server_url: str
) -> str:

    info = static_device_info(
        device_id
    )

    logger.info(
        "Enregistrement de l'appareil..."
    )

    response = requests.post(
        f"{server_url}/api/register",
        json=info,
        timeout=10
    )

    response.raise_for_status()

    data = response.json()

    token = data.get(
        "device_token"
    )

    if not token:

        raise RuntimeError(
            "Le serveur n'a pas fourni de token."
        )

    save_token(
        token
    )

    logger.info(
        "Appareil enregistré auprès du serveur."
    )

    return token


# ============================================================
# ENVOI TÉLÉMÉTRIE
# ============================================================

def send_telemetry(
    server_url,
    device_id,
    token,
    payload
):

    headers = {

        "X-Device-Id": device_id,

        "X-Device-Token": token,
    }

    response = requests.post(
        f"{server_url}/api/telemetry",
        json=payload,
        headers=headers,
        timeout=10
    )

    if response.status_code in (
        401,
        403
    ):

        raise PermissionError(
            "Token invalide ou révoqué."
        )

    response.raise_for_status()

    return response.json()


# ============================================================
# RÉSULTAT COMMANDE
# ============================================================

def send_command_result(
    server_url,
    device_id,
    token,
    command_id,
    success,
    message
):

    if not token:

        raise PermissionError(
            "Aucun token disponible."
        )

    headers = {

        "X-Device-Id": device_id,

        "X-Device-Token": token,
    }

    response = requests.post(

        f"{server_url}/api/devices/"
        f"{device_id}/command_result",

        json={

            "command_id": command_id,

            "success": bool(success),

            "message": str(message),
        },

        headers=headers,

        timeout=10
    )

    if response.status_code in (
        401,
        403
    ):

        raise PermissionError(
            "Token invalide ou révoqué."
        )

    response.raise_for_status()


# ============================================================
# COMMANDES ÉCRAN
# ============================================================

def process_screen_command(
    command,
    server_url,
    device_id,
    token
):
    """
    Traite uniquement les commandes écran.
    """

    action = command.get(
        "action"
    )

    # --------------------------------------------------------
    # START
    # --------------------------------------------------------

    if action == "screen_start":

        if is_screen_sharing():

            return (
                True,
                "Partage d'écran déjà actif."
            )

        start_screen_sharing(
            server_url,
            device_id,
            token
        )

        return (
            True,
            "Partage d'écran activé."
        )

    # --------------------------------------------------------
    # STOP
    # --------------------------------------------------------

    if action == "screen_stop":

        stop_screen_sharing()

        return (
            True,
            "Partage d'écran arrêté."
        )

    return None


# ============================================================
# EXÉCUTION DES COMMANDES
# ============================================================

def execute_pending_commands(
    commands,
    server_url,
    device_id,
    token
):
    """
    Exécute toutes les commandes envoyées
    par le serveur.
    """

    if not commands:
        return

    for command in commands:

        if not isinstance(
            command,
            dict
        ):
            continue

        action = command.get(
            "action"
        )

        command_id = command.get(
            "command_id"
        )

        logger.info(
            "Commande reçue : %s",
            action
        )

        success = False

        message = ""

        try:

            # =================================================
            # PARTAGE D'ÉCRAN
            # =================================================

            if action in (
                "screen_start",
                "screen_stop"
            ):

                result = process_screen_command(
                    command,
                    server_url,
                    device_id,
                    token
                )

                if result is not None:

                    success, message = result

                else:

                    success = False

                    message = (
                        f"Commande écran inconnue : "
                        f"{action}"
                    )

            # =================================================
            # ARRÊT
            # =================================================

            elif action == "shutdown":

                success, message = (
                    power.shutdown_now()
                )

            # =================================================
            # REDÉMARRAGE
            # =================================================

            elif action == "restart":

                success, message = (
                    power.restart_now()
                )

            # =================================================
            # ARRÊT D'URGENCE
            # =================================================

            elif action == "emergency_shutdown":

                success, message = (
                    power.emergency_shutdown()
                )

            # =================================================
            # INCONNUE
            # =================================================

            else:

                success = False

                message = (
                    f"Action inconnue : {action}"
                )

        except Exception as exc:

            success = False

            message = str(
                exc
            )

            logger.exception(
                "Erreur pendant l'exécution "
                "de la commande %s",
                action
            )

        logger.info(
            "Résultat commande '%s' : "
            "success=%s message=%s",
            action,
            success,
            message
        )

        # ----------------------------------------------------
        # RETOUR SERVEUR
        # ----------------------------------------------------

        if command_id:

            try:

                send_command_result(
                    server_url,
                    device_id,
                    token,
                    command_id,
                    success,
                    message
                )

            except Exception as exc:

                logger.warning(
                    "Impossible d'envoyer le résultat "
                    "de commande : %s",
                    exc
                )


# ============================================================
# BOUCLE PRINCIPALE
# ============================================================

def run():

    # --------------------------------------------------------
    # IDENTITÉ
    # --------------------------------------------------------

    device_id = load_device_id()

    # --------------------------------------------------------
    # SERVEUR
    # --------------------------------------------------------

    server_url = (
        config.AGENT_SERVER_URL
        .rstrip("/")
    )

    # --------------------------------------------------------
    # INTERVALLE
    # --------------------------------------------------------

    interval = max(
        1,
        int(
            config.AGENT_INTERVAL_SECONDS
        )
    )

    logger.info(
        "=========================================="
    )

    logger.info(
        "PC Monitor Agent"
    )

    logger.info(
        "Device ID : %s",
        device_id
    )

    logger.info(
        "Serveur : %s",
        server_url
    )

    logger.info(
        "Intervalle : %ss",
        interval
    )

    logger.info(
        "Partage écran : disponible"
    )

    logger.info(
        "=========================================="
    )

    # --------------------------------------------------------
    # TOKEN
    # --------------------------------------------------------

    token = load_saved_token()

    if not token:

        logger.info(
            "Aucun token trouvé. "
            "Tentative d'enregistrement..."
        )

        while token is None:

            try:

                token = register_device(
                    device_id,
                    server_url
                )

            except requests.RequestException as exc:

                logger.warning(
                    "Serveur inaccessible : %s",
                    exc
                )

                time.sleep(5)

            except Exception as exc:

                logger.warning(
                    "Erreur d'enregistrement : %s",
                    exc
                )

                time.sleep(5)

    # --------------------------------------------------------
    # BOUCLE
    # --------------------------------------------------------

    consecutive_failures = 0

    while True:

        try:

            # ----------------------------------------------
            # TÉLÉMÉTRIE
            # ----------------------------------------------

            payload = build_telemetry_payload(
                device_id
            )

            # ----------------------------------------------
            # ENVOI
            # ----------------------------------------------

            result = send_telemetry(
                server_url,
                device_id,
                token,
                payload
            )

            consecutive_failures = 0

            # ----------------------------------------------
            # COMMANDES
            # ----------------------------------------------

            pending_commands = result.get(
                "pending_commands",
                []
            )

            if pending_commands:

                execute_pending_commands(
                    pending_commands,
                    server_url,
                    device_id,
                    token
                )

        except PermissionError as exc:

            logger.error(
                "Accès refusé : %s",
                exc
            )

            sys.exit(1)

        except requests.RequestException as exc:

            consecutive_failures += 1

            logger.warning(
                "Échec de communication avec le serveur "
                "(tentative %s) : %s",
                consecutive_failures,
                exc
            )

        except KeyboardInterrupt:

            logger.info(
                "Arrêt demandé par l'utilisateur."
            )

            stop_screen_sharing()

            break

        except Exception as exc:

            consecutive_failures += 1

            logger.exception(
                "Erreur inattendue dans la boucle "
                "de supervision : %s",
                exc
            )

        time.sleep(
            interval
        )


# ============================================================
# POINT D'ENTRÉE
# ============================================================

if __name__ == "__main__":

    try:

        run()

    except KeyboardInterrupt:

        stop_screen_sharing()

        logger.info(
            "Agent arrêté."
        )

    except Exception as exc:

        logger.exception(
            "Erreur fatale : %s",
            exc
        )

        sys.exit(1)