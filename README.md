# PC Monitor

Application de supervision et d'administration à distance pour plusieurs
ordinateurs **dont vous êtes propriétaire ou administrateur autorisé**.

PC Monitor est composé de deux programmes :

- **`server.py`** — le serveur central, avec un dashboard web (Flask + Socket.IO).
- **`agent.py`** (lancé via `consent.py`) — l'agent installé sur chaque PC à
  superviser, qui envoie sa télémétrie et exécute les commandes autorisées.

```
┌──────────────────────┐
│     PC MONITOR       │
│   Serveur central     │
└──────────┬────────────┘
           │  Réseau local
    ┌──────┼──────┐
    ▼      ▼      ▼
   PC 1   PC 2   PC 3
  Agent  Agent  Agent
```

---

## 1. Arborescence du projet

```
PC-Monitor/
│
├── server.py              Serveur Flask + Socket.IO (dashboard + API)
├── agent.py                Agent : collecte psutil + envoi télémétrie
├── consent.py               Point d'entrée agent : fenêtre de consentement
├── autostart_windows.py    Démarrage automatique via le Planificateur de tâches
├── config.py                 Configuration centrale (ports, seuils, chemins)
├── database.py               Accès SQLite (schéma + requêtes)
├── auth.py                   Authentification dashboard + agents
├── power.py                  Commandes d'arrêt/redémarrage Windows
├── wol.py                    Envoi de paquets Wake-on-LAN
├── requirements.txt
├── README.md
│
├── data/
│   └── monitor.db           Base SQLite (créée automatiquement)
│
├── templates/
│   ├── login.html
│   ├── dashboard.html
│   └── device.html
│
├── static/
│   ├── css/style.css
│   └── js/
│       ├── dashboard.js
│       └── device.js
│
└── installer/
    └── README.md            Notes de packaging (raccourcis, exécutable, etc.)
```

---

## 2. Installation

Prérequis : **Python 3.12** sous **Windows 11** (le serveur peut aussi tourner
sur une autre machine du même réseau local, y compris Linux/macOS, mais les
commandes d'arrêt/redémarrage/urgence ne fonctionnent que sur les agents
Windows).

```bash
python -m pip install -r requirements.txt
```

---

## 3. Lancer le serveur

Sur le PC qui fera office de serveur central :

```bash
python server.py
```

Le serveur affiche automatiquement son adresse :

```
PC Monitor démarré. Dashboard accessible sur :
  http://127.0.0.1:8765
  http://192.168.1.20:8765   (réseau local)
```

Ouvrez cette adresse dans un navigateur. **La toute première connexion crée
le compte administrateur** (nom d'utilisateur + mot de passe) — il n'y a pas
de compte par défaut.

---

## 4. Installer l'agent sur un PC à superviser

Copiez le dossier `PC-Monitor` (ou au minimum : `agent.py`, `consent.py`,
`config.py`, `power.py`, `autostart_windows.py`, `requirements.txt`) sur le
PC à surveiller, puis :

```bash
python -m pip install -r requirements.txt
python consent.py
```

Une fenêtre de consentement s'affiche et **doit être acceptée explicitement**
avant toute collecte de données. Sans acceptation, rien n'est installé et
aucune persistance n'est créée.

L'agent tente ensuite de joindre le serveur à l'adresse définie par la
variable d'environnement `MONITOR_SERVER` (par défaut `http://127.0.0.1:8765`,
ce qui ne fonctionne que si l'agent tourne sur la même machine que le
serveur).

### Configurer un autre PC (agent distant)

Sous Windows, dans une invite de commandes, avant de lancer l'agent :

```cmd
set MONITOR_SERVER=http://192.168.1.20:8765
python consent.py
```

Remplacez `192.168.1.20` par l'adresse affichée au lancement du serveur.
Répétez cette opération sur chaque PC à superviser.

---

## 5. Multi-PC — vue d'ensemble

| Élément                          | Où ça tourne                          |
|-----------------------------------|----------------------------------------|
| `server.py`                       | Une seule machine (le "serveur")       |
| `consent.py` → `agent.py`         | Sur chaque PC à superviser             |
| Dashboard (navigateur web)        | N'importe quel appareil du réseau local pouvant joindre le serveur |

Chaque agent est identifié par un **UUID unique**, généré à la première
exécution et stocké localement (`data/identity.json`). Vous pouvez renommer
chaque appareil depuis le dashboard (ex. `PC-SALON`, `PC-BUREAU`).

---

## 6. Wake-on-LAN

Pour pouvoir allumer un PC éteint depuis le dashboard :

1. Activez Wake-on-LAN dans le BIOS/UEFI du PC (option souvent nommée
   "Wake on LAN" ou "Power On by PCI-E").
2. Sous Windows 11 : *Gestionnaire de périphériques → Cartes réseau →
   [votre carte] → Propriétés → Gestion de l'alimentation* → cochez
   *"Autoriser ce périphérique à sortir l'ordinateur du mode veille"*, puis
   dans l'onglet *Avancé*, activez *"Wake on Magic Packet"*.
3. Le PC doit rester relié à l'alimentation électrique (Wake-on-LAN ne
   fonctionne pas sur un PC totalement débranché).
4. Le serveur doit se trouver sur le **même réseau local** (ou le même
   segment de diffusion / VLAN) que le PC à réveiller — le paquet magique est
   envoyé en broadcast UDP et ne traverse pas Internet par défaut.

Un guide identique est intégré directement dans la page détaillée de chaque
appareil du dashboard, section "Wake-on-LAN".

Si Wake-on-LAN échoue, le dashboard n'affiche jamais l'appareil comme
"allumé" tant que l'agent ne s'est pas reconnecté de lui-même.

---

## 7. Démarrage automatique de l'agent

Depuis la page détaillée d'un appareil (ou en exécutant la fonction
`enable_autostart()` de `autostart_windows.py`), vous pouvez activer le
démarrage automatique de l'agent à l'ouverture de session Windows. Cela crée
une tâche planifiée **visible** nommée `PCMonitorAgent` dans le Planificateur
de tâches Windows — aucune persistance cachée.

---

## 8. Mode Urgence — PANIC98

Le dashboard propose, sur la page de chaque appareil, un bouton **⚠️
URGENCE** qui déclenche un arrêt sécurisé immédiat, protégé par :

1. le code de confirmation `PANIC98` (jamais affiché dans l'interface) ;
2. une seconde confirmation explicite nommant l'appareil ciblé ;
3. l'authentification de l'utilisateur du dashboard ;
4. le token valide de l'appareil.

Après plusieurs codes incorrects, un délai temporaire est appliqué avant de
pouvoir retenter (protection anti-bruteforce). L'action exécute uniquement
la commande Windows standard `shutdown /s /t 0` — **jamais** de BSOD, de
suppression de fichiers ou de contournement des protections système. Chaque
déclenchement est enregistré dans l'historique avec l'utilisateur, l'heure
et le résultat.

---

## 9. Désinstallation

**Sur le PC agent**, pour arrêter la persistance et supprimer les données
locales :

```bash
python consent.py --revoke
```

Cette commande supprime la tâche planifiée de démarrage automatique et
efface le consentement/l'identité stockés localement.

**Sur le dashboard**, dans la section *Sécurité*, cliquez sur **RÉVOQUER**
pour l'appareil concerné (ou utilisez le bouton de désinstallation complète
sur la page détaillée), afin que le serveur refuse toute future donnée ou
commande provenant de cet appareil.

---

## 10. Sécurité — ce que PC Monitor ne fait jamais

- Pas de collecte de mots de passe, cookies ou frappes clavier (aucun keylogger).
- Pas de webcam, microphone ou capture d'écran cachés.
- Pas de récupération de fichiers personnels.
- Pas de mécanisme de dissimulation ni de contournement d'antivirus.
- Pas de persistance cachée : le démarrage automatique passe par le
  Planificateur de tâches Windows standard, visible et désactivable.
- Toute commande d'alimentation (arrêt, redémarrage, urgence) exige une
  authentification du dashboard **et** un token d'appareil valide, et est
  journalisée dans l'historique.

---

## 11. Fonctions nécessitant que les appareils soient sur le même réseau local

| Fonction                                  | Contrainte réseau |
|--------------------------------------------|--------------------|
| Envoi de la télémétrie (agent → serveur)   | L'agent doit pouvoir joindre l'adresse IP/port du serveur (réseau local, VPN, ou tunnel explicite si vous l'exposez vous-même). |
| Wake-on-LAN                                | **Obligatoirement** le même réseau local / segment de diffusion — le paquet magique est un broadcast UDP qui ne traverse pas Internet ni la plupart des routeurs sans configuration spécifique. |
| Arrêt / redémarrage / mode urgence         | Fonctionne dès que l'agent est en ligne et joignable par le serveur, quel que soit le réseau (local ou distant via VPN), puisque la commande est relayée via la connexion HTTP existante de l'agent, pas en direct. |
| Consultation du dashboard                  | Le navigateur doit pouvoir joindre l'adresse IP/port du serveur. |

Le serveur n'expose jamais automatiquement son port sur Internet : par
défaut, il écoute sur toutes les interfaces locales (`0.0.0.0`) mais reste
inaccessible depuis l'extérieur tant que vous ne configurez pas vous-même une
redirection de port ou un VPN. Si vous exposez le serveur au-delà d'un réseau
local de confiance, utilisez HTTPS (reverse proxy avec certificat TLS) plutôt
que le serveur de développement fourni.

---

## 12. Compatibilité

- Testé pour Windows 11 + Python 3.12.
- Les fonctionnalités matérielles indisponibles (température, batterie sur un
  PC fixe, etc.) affichent toujours **"Non disponible"** plutôt qu'une valeur
  inventée.
- Les commandes d'alimentation (`shutdown`, `restart`, mode urgence) ne
  s'exécutent que si l'agent tourne sous Windows ; sur un autre système, un
  message d'erreur explicite est renvoyé sans rien exécuter.
