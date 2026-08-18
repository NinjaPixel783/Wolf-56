"""
power.py — Exécution locale des commandes d'alimentation sur l'agent.

Utilise exclusivement les commandes Windows standard (`shutdown.exe`).
Aucune méthode cachée, aucun contournement des protections système,
aucune tentative de provoquer un crash, un BSOD, ou une perte de données.

Ce module ne fait rien sur le serveur central : il tourne côté agent, sur
la machine que l'on souhaite éteindre/redémarrer.
"""

import logging
import platform
import subprocess

logger = logging.getLogger("pcmonitor.power")

IS_WINDOWS = platform.system().lower() == "windows"


def _run_shutdown_command(args):
    """Exécute shutdown.exe avec les arguments donnés. Retourne (ok, message)."""
    if not IS_WINDOWS:
        # Environnement non-Windows (ex : développement/test sur Linux/macOS).
        # On ne simule jamais une réussite silencieuse : on le signale
        # clairement pour éviter toute confusion.
        logger.warning("Commande d'alimentation ignorée : système non-Windows (%s)", platform.system())
        return False, "Commande d'alimentation non supportée sur ce système d'exploitation."

    try:
        result = subprocess.run(
            ["shutdown"] + args,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            return True, "Commande exécutée avec succès."
        return False, f"shutdown a retourné le code {result.returncode}: {result.stderr.strip()}"
    except FileNotFoundError:
        return False, "Exécutable shutdown.exe introuvable."
    except subprocess.TimeoutExpired:
        return False, "Délai d'exécution dépassé."
    except Exception as exc:  # pragma: no cover - défense en profondeur
        logger.exception("Erreur lors de l'exécution de la commande d'alimentation")
        return False, f"Erreur inattendue : {exc}"


def shutdown_now():
    """Arrêt propre immédiat : `shutdown /s /t 0`."""
    logger.info("Exécution de l'arrêt système demandé à distance")
    return _run_shutdown_command(["/s", "/t", "0"])


def restart_now():
    """Redémarrage propre immédiat : `shutdown /r /t 0`."""
    logger.info("Exécution du redémarrage système demandé à distance")
    return _run_shutdown_command(["/r", "/t", "0"])


def emergency_shutdown():
    """Arrêt d'urgence sécurisé (mode PANIC98).

    Utilise la même procédure d'arrêt Windows standard que `shutdown_now`.
    Aucune action destructrice n'est effectuée : il ne s'agit que d'une
    mise hors service propre et immédiate, sans /f forcé destiné à tuer
    des processus de façon brutale au-delà de ce que Windows fait déjà
    normalement lors d'un arrêt.
    """
    logger.info("Exécution de la procédure d'urgence PANIC98 (arrêt sécurisé)")
    return _run_shutdown_command(["/s", "/t", "0"])


def cancel_pending_shutdown():
    """Annule un arrêt/redémarrage planifié (`shutdown /a`), utile en cas
    d'erreur d'utilisation avant que le délai ne soit écoulé."""
    return _run_shutdown_command(["/a"])
