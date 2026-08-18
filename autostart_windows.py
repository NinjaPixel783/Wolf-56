"""
autostart_windows.py — Démarrage automatique de l'agent avec Windows.

Utilise le Planificateur de tâches Windows (schtasks.exe), une méthode
standard et visible dans l'interface Windows ("Planificateur de tâches").
Aucune persistance cachée : la tâche est nommée explicitement "PCMonitorAgent"
et apparaît normalement dans le Planificateur.
"""

import logging
import platform
import subprocess
import sys
import os

logger = logging.getLogger("pcmonitor.autostart")

TASK_NAME = "PCMonitorAgent"
IS_WINDOWS = platform.system().lower() == "windows"


def _agent_launch_command():
    """Commande utilisée pour relancer l'agent au démarrage de session."""
    python_exe = sys.executable
    consent_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "consent.py")
    return f'"{python_exe}" "{consent_script}"'


def is_autostart_enabled() -> bool:
    if not IS_WINDOWS:
        return False
    try:
        result = subprocess.run(
            ["schtasks", "/Query", "/TN", TASK_NAME],
            capture_output=True, text=True, timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def enable_autostart() -> bool:
    """Crée une tâche planifiée standard exécutée à l'ouverture de session
    de l'utilisateur courant. Nécessite un consentement explicite préalable
    (vérifié par l'appelant)."""
    if not IS_WINDOWS:
        logger.warning("Démarrage automatique non supporté hors Windows.")
        return False

    command = _agent_launch_command()
    try:
        result = subprocess.run(
            [
                "schtasks", "/Create", "/TN", TASK_NAME,
                "/TR", command,
                "/SC", "ONLOGON",
                "/RL", "LIMITED",
                "/F",  # remplace la tâche existante si présente
            ],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            logger.info("Démarrage automatique activé (tâche planifiée '%s').", TASK_NAME)
            return True
        logger.error("Échec de création de la tâche planifiée: %s", result.stderr)
        return False
    except Exception as exc:
        logger.exception("Erreur lors de l'activation du démarrage automatique")
        return False


def disable_autostart() -> bool:
    if not IS_WINDOWS:
        return False
    try:
        result = subprocess.run(
            ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
            capture_output=True, text=True, timeout=15,
        )
        # Code 0 = supprimée, code non-zéro possible si la tâche n'existait
        # déjà plus : ce n'est pas une erreur dans ce contexte.
        logger.info("Démarrage automatique désactivé.")
        return True
    except Exception:
        logger.exception("Erreur lors de la désactivation du démarrage automatique")
        return False
