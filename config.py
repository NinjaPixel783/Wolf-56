"""
config.py — Configuration centrale pour PC Monitor.

Ce fichier est utilisé par :
- le serveur PC Monitor ;
- les agents installés sur les appareils supervisés.

IMPORTANT :
Sur les ordinateurs agents, AGENT_SERVER_URL doit pointer vers
l'adresse IP du PC qui héberge le serveur PC Monitor.
"""

import os


# ============================================================
# CHEMINS
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = os.path.join(BASE_DIR, "data")

DB_PATH = os.path.join(DATA_DIR, "monitor.db")

os.makedirs(DATA_DIR, exist_ok=True)


# ============================================================
# SERVEUR PC MONITOR
# ============================================================

# Le serveur écoute sur toutes les interfaces réseau.
SERVER_HOST = os.environ.get(
    "MONITOR_HOST",
    "0.0.0.0"
)

# Port utilisé par le dashboard et l'API.
SERVER_PORT = int(
    os.environ.get(
        "MONITOR_PORT",
        "8765"
    )
)

SERVER_NAME = os.environ.get(
    "MONITOR_SERVER_NAME",
    "PC Monitor"
)


# ============================================================
# ADRESSE DU SERVEUR POUR LES AGENTS
# ============================================================

# IMPORTANT :
#
# Remplace 192.168.1.20 par l'adresse IPv4 du PC qui héberge
# server.py.
#
# Exemple :
#
#   AGENT_SERVER_URL = "http://192.168.1.35:8765"
#
# Pour connaître l'adresse du serveur :
#
#   ipconfig
#
# puis chercher "Adresse IPv4".
#
# Cette adresse est utilisée directement par agent.py.

AGENT_SERVER_URL = os.environ.get(
    "MONITOR_SERVER",
    "http://192.168.1.195:8765"
)


# ============================================================
# INTERVALLE DE TÉLÉMÉTRIE
# ============================================================

# Nombre de secondes entre deux envois de données.

AGENT_INTERVAL_SECONDS = float(
    os.environ.get(
        "MONITOR_INTERVAL",
        "2"
    )
)


# ============================================================
# DÉTECTION HORS LIGNE
# ============================================================

# Si aucun paquet n'est reçu pendant cette durée,
# l'appareil est considéré comme hors ligne.

OFFLINE_THRESHOLD_SECONDS = 8


# ============================================================
# DONNÉES LOCALES DE L'AGENT
# ============================================================

# Dossier utilisé par chaque agent pour conserver
# son consentement, son identité et son token.

AGENT_DATA_DIR = os.path.join(
    BASE_DIR,
    "data"
)

CONSENT_FILE = os.path.join(
    AGENT_DATA_DIR,
    "consent.json"
)

IDENTITY_FILE = os.path.join(
    AGENT_DATA_DIR,
    "identity.json"
)

TOKEN_FILE = os.path.join(
    AGENT_DATA_DIR,
    "token.json"
)


# ============================================================
# CLÉ SECRÈTE FLASK
# ============================================================

SECRET_KEY_PATH = os.path.join(
    DATA_DIR,
    "secret.key"
)


def get_flask_secret_key() -> str:
    """
    Retourne la clé secrète Flask.

    Si elle n'existe pas encore, une nouvelle clé est générée
    et enregistrée dans data/secret.key.
    """

    if os.path.exists(SECRET_KEY_PATH):

        with open(
            SECRET_KEY_PATH,
            "r",
            encoding="utf-8"
        ) as f:

            key = f.read().strip()

            if key:
                return key

    key = os.urandom(32).hex()

    with open(
        SECRET_KEY_PATH,
        "w",
        encoding="utf-8"
    ) as f:

        f.write(key)

    return key


# ============================================================
# SEUILS D'ALERTE
# ============================================================

DEFAULT_CPU_THRESHOLD = 90

DEFAULT_RAM_THRESHOLD = 90

DEFAULT_DISK_THRESHOLD = 95

DEFAULT_BATTERY_THRESHOLD = 15


# ============================================================
# HISTORIQUE
# ============================================================

# Nombre maximum de métriques conservées par appareil.

MAX_METRICS_PER_DEVICE = 500

# Nombre maximum de commandes conservées.

MAX_COMMAND_HISTORY = 1000

# Nombre maximum d'alertes conservées.

MAX_ALERT_HISTORY = 1000


# ============================================================
# MODE URGENCE
# ============================================================

# Code utilisé pour confirmer une action d'urgence.
#
# Il n'est pas affiché dans le dashboard.

EMERGENCY_CODE = os.environ.get(
    "MONITOR_PANIC_CODE",
    "PANIC98"
)


# ============================================================
# PROTECTION CONTRE LES TENTATIVES RÉPÉTÉES
# ============================================================

# Nombre maximal de tentatives incorrectes.

EMERGENCY_MAX_ATTEMPTS = 3

# Durée du verrouillage en secondes.

EMERGENCY_LOCKOUT_SECONDS = 60


# ============================================================
# INFORMATIONS DE CONFIGURATION
# ============================================================

def get_config_info():
    """
    Retourne quelques informations utiles pour le diagnostic.
    """

    return {
        "server_host": SERVER_HOST,
        "server_port": SERVER_PORT,
        "server_name": SERVER_NAME,
        "agent_server_url": AGENT_SERVER_URL,
        "agent_interval": AGENT_INTERVAL_SECONDS,
        "offline_threshold": OFFLINE_THRESHOLD_SECONDS,
    }


# ============================================================
# AFFICHAGE DE CONFIGURATION
# ============================================================

if __name__ == "__main__":

    print("=" * 55)
    print("PC MONITOR — CONFIGURATION")
    print("=" * 55)

    print()
    print("Serveur :")
    print(f"  Host      : {SERVER_HOST}")
    print(f"  Port      : {SERVER_PORT}")
    print(f"  Nom       : {SERVER_NAME}")

    print()
    print("Agent :")
    print(f"  Serveur   : {AGENT_SERVER_URL}")
    print(f"  Intervalle: {AGENT_INTERVAL_SECONDS}s")

    print()
    print("Hors ligne :")
    print(f"  Seuil     : {OFFLINE_THRESHOLD_SECONDS}s")

    print()
    print("Dossiers :")
    print(f"  Data      : {DATA_DIR}")
    print(f"  Database  : {DB_PATH}")

    print()
    print("=" * 55)