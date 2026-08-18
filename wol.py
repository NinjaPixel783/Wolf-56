"""
wol.py — Envoi de paquets Wake-on-LAN (magic packet).

N'utilise que l'adresse MAC enregistrée pour l'appareil. Le serveur ne peut
jamais garantir que l'appareil s'est réellement allumé : seul le retour de
télémétrie de l'agent (voir server.py) confirme l'état "EN LIGNE".
"""

import logging
import re
import socket

logger = logging.getLogger("pcmonitor.wol")

MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}[:\-]){5}([0-9A-Fa-f]{2})$")


def is_valid_mac(mac: str) -> bool:
    return bool(mac) and bool(MAC_RE.match(mac.strip()))


def send_magic_packet(mac_address: str, broadcast_ip: str = "255.255.255.255", port: int = 9) -> bool:
    """Construit et envoie un magic packet WoL en broadcast UDP.

    Retourne True si le paquet a été envoyé sans erreur réseau locale
    (cela ne garantit PAS que l'appareil s'est allumé).
    """
    if not is_valid_mac(mac_address):
        logger.warning("Adresse MAC invalide pour Wake-on-LAN: %s", mac_address)
        return False

    mac_bytes = bytes.fromhex(mac_address.replace(":", "").replace("-", ""))
    magic_packet = b"\xff" * 6 + mac_bytes * 16

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(magic_packet, (broadcast_ip, port))
        logger.info("Paquet Wake-on-LAN envoyé pour %s via %s:%s", mac_address, broadcast_ip, port)
        return True
    except OSError as exc:
        logger.error("Échec de l'envoi du paquet Wake-on-LAN pour %s: %s", mac_address, exc)
        return False
