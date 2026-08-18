"""
consent.py — Point d'entrée de l'agent PC Monitor.

Fonctions :
- Demande de consentement lors de la première ouverture.
- Création d'un identifiant unique pour l'appareil.
- Démarrage de l'agent après consentement.
- Révocation du consentement avec --revoke ou --uninstall.

Lancement :
    python consent.py

Révocation :
    python consent.py --revoke
    python consent.py --uninstall
"""

import json
import os
import sys
import time
import uuid

import config


# ============================================================
# CONFIGURATION
# ============================================================

CONSENT_TEXT = """PC MONITOR

Ce programme permet à un administrateur autorisé
de surveiller cet ordinateur depuis un tableau
de bord local.

Les informations peuvent inclure :

• utilisation CPU
• utilisation RAM
• stockage
• batterie
• réseau
• système d'exploitation
• température si disponible
• état de la machine
• informations générales du matériel

Certaines commandes d'administration peuvent également
être disponibles si elles sont activées par l'administrateur.

Aucune collecte de mots de passe, frappes clavier,
cookies, fichiers personnels ou contenu privé.

Voulez-vous continuer ?"""


# ============================================================
# CONSENTEMENT
# ============================================================

def has_consent() -> bool:
    """
    Vérifie si l'utilisateur a déjà donné son consentement.
    """
    return os.path.exists(config.CONSENT_FILE)


def save_consent():
    """
    Enregistre le consentement localement.
    """

    os.makedirs(
        config.AGENT_DATA_DIR,
        exist_ok=True
    )

    data = {
        "consent_given": True,
        "timestamp": time.time()
    }

    with open(
        config.CONSENT_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            data,
            file,
            indent=4
        )


# ============================================================
# IDENTIFIANT APPAREIL
# ============================================================

def get_or_create_device_id() -> str:
    """
    Retourne l'UUID unique de cet appareil.

    Si aucun UUID n'existe encore,
    un nouvel UUID est créé.
    """

    if os.path.exists(config.IDENTITY_FILE):

        try:

            with open(
                config.IDENTITY_FILE,
                "r",
                encoding="utf-8"
            ) as file:

                data = json.load(file)

            if "device_id" in data:

                return data["device_id"]

        except Exception:

            # Si le fichier est corrompu,
            # on recrée un identifiant propre.
            pass

    device_id = str(
        uuid.uuid4()
    )

    os.makedirs(
        config.AGENT_DATA_DIR,
        exist_ok=True
    )

    data = {
        "device_id": device_id,
        "created_at": time.time()
    }

    with open(
        config.IDENTITY_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            data,
            file,
            indent=4
        )

    return device_id


# ============================================================
# FENÊTRE DE CONSENTEMENT
# ============================================================

def show_consent_dialog() -> bool:
    """
    Affiche la fenêtre graphique de consentement.

    Retour :
        True  = CONTINUER
        False = ANNULER
    """

    try:

        import tkinter as tk
        from tkinter import font as tkfont

    except ImportError:

        print(CONSENT_TEXT)

        print()
        print(
            "Interface graphique indisponible."
        )

        answer = input(
            "\nTapez CONTINUER pour accepter "
            "ou appuyez sur Entrée pour annuler : "
        )

        return (
            answer.strip().upper()
            == "CONTINUER"
        )

    result = {
        "accepted": False
    }

    # --------------------------------------------------------
    # FENÊTRE
    # --------------------------------------------------------

    root = tk.Tk()

    root.title(
        "PC Monitor — Consentement"
    )

    root.geometry(
        "600x560"
    )

    root.resizable(
        False,
        False
    )

    root.configure(
        bg="#F5F7FA"
    )

    # --------------------------------------------------------
    # POLICES
    # --------------------------------------------------------

    title_font = tkfont.Font(
        family="Segoe UI",
        size=18,
        weight="bold"
    )

    body_font = tkfont.Font(
        family="Segoe UI",
        size=10
    )

    button_font = tkfont.Font(
        family="Segoe UI",
        size=10,
        weight="bold"
    )

    # --------------------------------------------------------
    # HEADER
    # --------------------------------------------------------

    header = tk.Frame(
        root,
        bg="#2563EB",
        height=75
    )

    header.pack(
        fill="x"
    )

    header.pack_propagate(
        False
    )

    title = tk.Label(
        header,
        text="PC MONITOR",
        font=title_font,
        bg="#2563EB",
        fg="white"
    )

    title.pack(
        expand=True
    )

    # --------------------------------------------------------
    # CONTENU
    # --------------------------------------------------------

    content = tk.Frame(
        root,
        bg="#F5F7FA"
    )

    content.pack(
        fill="both",
        expand=True,
        padx=30,
        pady=20
    )

    body_text = (
        "Ce programme permet à un administrateur autorisé "
        "de surveiller cet ordinateur depuis un tableau "
        "de bord local.\n\n"

        "Les informations peuvent inclure :\n\n"

        "• utilisation CPU\n"
        "• utilisation RAM\n"
        "• stockage\n"
        "• batterie\n"
        "• réseau\n"
        "• système d'exploitation\n"
        "• température si disponible\n"
        "• état de la machine\n"
        "• informations générales du matériel\n\n"

        "Certaines commandes d'administration peuvent "
        "également être disponibles si elles sont activées "
        "par l'administrateur.\n\n"

        "Aucune collecte de mots de passe, frappes clavier, "
        "cookies, fichiers personnels ou contenu privé.\n\n"

        "Voulez-vous continuer ?"
    )

    message = tk.Label(
        content,
        text=body_text,
        font=body_font,
        bg="#F5F7FA",
        fg="#111827",
        justify="left",
        anchor="nw",
        wraplength=530
    )

    message.pack(
        fill="both",
        expand=True
    )

    # --------------------------------------------------------
    # ZONE DES BOUTONS
    # --------------------------------------------------------

    button_frame = tk.Frame(
        root,
        bg="#F5F7FA",
        height=85
    )

    button_frame.pack(
        fill="x",
        padx=30,
        pady=(0, 25)
    )

    button_frame.pack_propagate(
        False
    )

    # --------------------------------------------------------
    # ACTION ANNULER
    # --------------------------------------------------------

    def on_cancel():

        result["accepted"] = False

        root.destroy()

    # --------------------------------------------------------
    # ACTION CONTINUER
    # --------------------------------------------------------

    def on_continue():

        result["accepted"] = True

        root.destroy()

    # --------------------------------------------------------
    # BOUTON ANNULER
    # --------------------------------------------------------

    cancel_button = tk.Button(
        button_frame,
        text="ANNULER",
        font=button_font,
        bg="#E5E7EB",
        fg="#111827",
        activebackground="#D1D5DB",
        activeforeground="#111827",
        relief="flat",
        cursor="hand2",
        width=18,
        height=2,
        command=on_cancel
    )

    cancel_button.pack(
        side="left",
        padx=10
    )

    # --------------------------------------------------------
    # BOUTON CONTINUER
    # --------------------------------------------------------

    continue_button = tk.Button(
        button_frame,
        text="CONTINUER",
        font=button_font,
        bg="#2563EB",
        fg="white",
        activebackground="#1D4ED8",
        activeforeground="white",
        relief="flat",
        cursor="hand2",
        width=18,
        height=2,
        command=on_continue
    )

    continue_button.pack(
        side="right",
        padx=10
    )

    # --------------------------------------------------------
    # RACCOURCIS
    # --------------------------------------------------------

    # Entrée = continuer
    root.bind(
        "<Return>",
        lambda event: on_continue()
    )

    # Échap = annuler
    root.bind(
        "<Escape>",
        lambda event: on_cancel()
    )

    # X = annuler
    root.protocol(
        "WM_DELETE_WINDOW",
        on_cancel
    )

    # --------------------------------------------------------
    # CENTRAGE
    # --------------------------------------------------------

    root.update_idletasks()

    width = root.winfo_width()
    height = root.winfo_height()

    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()

    x = (
        screen_width - width
    ) // 2

    y = (
        screen_height - height
    ) // 2

    root.geometry(
        f"{width}x{height}+{x}+{y}"
    )

    # --------------------------------------------------------
    # BOUTON CONTINUER FOCUS
    # --------------------------------------------------------

    continue_button.focus_set()

    # --------------------------------------------------------
    # LANCEMENT FENÊTRE
    # --------------------------------------------------------

    root.mainloop()

    return result["accepted"]


# ============================================================
# RÉVOCATION / DÉSINSTALLATION
# ============================================================

def revoke_and_uninstall():
    """
    Révoque le consentement local et désactive
    le démarrage automatique.
    """

    print()
    print(
        "Révocation du consentement..."
    )

    # --------------------------------------------------------
    # AUTOSTART
    # --------------------------------------------------------

    try:

        from autostart_windows import (
            disable_autostart
        )

        disable_autostart()

        print(
            "Démarrage automatique désactivé."
        )

    except ImportError:

        print(
            "Module autostart_windows indisponible."
        )

    except Exception as exc:

        print(
            "Impossible de supprimer "
            f"le démarrage automatique : {exc}"
        )

    # --------------------------------------------------------
    # FICHIERS LOCAUX
    # --------------------------------------------------------

    files_to_remove = [
        config.CONSENT_FILE,
        config.IDENTITY_FILE
    ]

    for path in files_to_remove:

        try:

            if os.path.exists(path):

                os.remove(path)

                print(
                    f"Supprimé : {path}"
                )

        except Exception as exc:

            print(
                f"Impossible de supprimer "
                f"{path} : {exc}"
            )

    # --------------------------------------------------------
    # FIN
    # --------------------------------------------------------

    print()
    print(
        "PC Monitor a été désinstallé "
        "de cette machine."
    )

    print()
    print(
        "Si l'appareil est encore enregistré "
        "dans le dashboard, utilisez le bouton "
        "'RÉVOQUER' pour supprimer son accès."
    )


# ============================================================
# DÉMARRAGE AGENT
# ============================================================

def start_agent():

    try:

        import agent

    except ImportError as exc:

        print()
        print(
            "Impossible de charger agent.py :"
        )

        print(exc)

        sys.exit(1)

    try:

        agent.run()

    except AttributeError:

        print()
        print(
            "Erreur : agent.py ne contient "
            "pas de fonction run()."
        )

        print(
            "Ajoutez une fonction :"
        )

        print()
        print(
            "def run():"
        )

        print(
            "    ..."
        )

        sys.exit(1)

    except KeyboardInterrupt:

        print()
        print(
            "Agent arrêté."
        )

    except Exception as exc:

        print()
        print(
            f"Erreur de l'agent : {exc}"
        )

        sys.exit(1)


# ============================================================
# MAIN
# ============================================================

def main():

    # --------------------------------------------------------
    # RÉVOCATION
    # --------------------------------------------------------

    if (
        "--revoke" in sys.argv
        or "--uninstall" in sys.argv
    ):

        revoke_and_uninstall()

        return

    # --------------------------------------------------------
    # PREMIÈRE EXÉCUTION
    # --------------------------------------------------------

    if not has_consent():

        print(
            "Aucun consentement trouvé."
        )

        accepted = show_consent_dialog()

        if not accepted:

            print()
            print(
                "Installation annulée "
                "par l'utilisateur."
            )

            print(
                "Aucune donnée collectée."
            )

            print(
                "Aucune installation effectuée."
            )

            sys.exit(0)

        # ----------------------------------------------------
        # SAUVEGARDE CONSENTEMENT
        # ----------------------------------------------------

        save_consent()

        print()
        print(
            "Consentement enregistré."
        )

    else:

        print(
            "Consentement déjà enregistré."
        )

    # --------------------------------------------------------
    # ID APPAREIL
    # --------------------------------------------------------

    device_id = get_or_create_device_id()

    print()
    print(
        "Identifiant de cet appareil :"
    )

    print(
        device_id
    )

    print()

    # --------------------------------------------------------
    # DÉMARRAGE AGENT
    # --------------------------------------------------------

    start_agent()


# ============================================================
# POINT D'ENTRÉE
# ============================================================

if __name__ == "__main__":
    main()