"""
auth.py — Authentification des utilisateurs du dashboard et des appareils.

- Les mots de passe utilisateurs sont hachés avec Werkzeug (PBKDF2-SHA256).
- Les sessions Flask sont signées avec la clé secrète du serveur.
- Les agents s'authentifient avec un token propre à l'appareil (DEVICE_ID +
  DEVICE_TOKEN), vérifié en base à chaque requête.
"""

from functools import wraps

from flask import session, redirect, url_for, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

import database


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return check_password_hash(password_hash, password)


def login_user(username: str):
    session.clear()
    session["username"] = username
    session.permanent = True


def logout_user():
    session.clear()


def current_username():
    return session.get("username")


def is_logged_in() -> bool:
    return "username" in session


def login_required(view_func):
    """Protège une route de page HTML : redirige vers /login si non connecté."""
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not is_logged_in():
            return redirect(url_for("login"))
        return view_func(*args, **kwargs)
    return wrapped


def api_login_required(view_func):
    """Protège une route API JSON : renvoie 401 si non connecté."""
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not is_logged_in():
            return jsonify({"error": "authentification requise"}), 401
        return view_func(*args, **kwargs)
    return wrapped


def verify_agent_request():
    """Vérifie qu'une requête entrante d'un agent porte un DEVICE_ID et un
    DEVICE_TOKEN valides et non révoqués. Retourne le device_id si valide,
    sinon None."""
    device_id = request.headers.get("X-Device-Id") or (request.json or {}).get("device_id")
    token = request.headers.get("X-Device-Token") or (request.json or {}).get("device_token")

    if not device_id or not token:
        return None

    if not database.validate_device_token(device_id, token):
        return None

    return device_id


def agent_auth_required(view_func):
    """Protège une route API destinée aux agents (télémétrie, etc.)."""
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        device_id = verify_agent_request()
        if not device_id:
            return jsonify({"error": "appareil non autorisé ou token invalide"}), 401
        request.verified_device_id = device_id
        return view_func(*args, **kwargs)
    return wrapped
