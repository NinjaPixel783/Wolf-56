# Notes de packaging — PC Monitor

Ce dossier ne contient pas d'installeur binaire prêt à l'emploi : PC Monitor
est livré sous forme de code source Python, à exécuter avec
`python server.py` (serveur) et `python consent.py` (agent), comme décrit
dans le README principal.

Si vous souhaitez packager l'agent pour un déploiement plus simple sur
plusieurs postes, voici deux approches courantes et sans persistance
cachée :

## Option A — Script de déploiement simple

1. Copiez le dossier `PC-Monitor` sur le PC cible (partage réseau, clé USB,
   ou outil de déploiement de votre choix).
2. Créez un fichier `install.bat` à la racine du dossier copié :

   ```bat
   @echo off
   python -m pip install -r requirements.txt
   set MONITOR_SERVER=http://ADRESSE_DU_SERVEUR:8765
   python consent.py
   ```

3. Exécutez `install.bat`. La fenêtre de consentement s'affichera
   normalement.

## Option B — Exécutable autonome avec PyInstaller

Pour éviter d'avoir à installer Python sur chaque poste :

```bash
pip install pyinstaller
pyinstaller --onefile --noconsole --name PCMonitorAgent consent.py
```

L'exécutable généré (`dist/PCMonitorAgent.exe`) reste soumis à la même
fenêtre de consentement au premier lancement, et à la même politique de
démarrage automatique visible via le Planificateur de tâches Windows —
aucun raccourci ni mécanisme caché n'est ajouté automatiquement par ce
projet.

## Icône / raccourci bureau (optionnel)

Vous pouvez créer manuellement un raccourci Windows vers
`consent.py` (ou l'exécutable PyInstaller) sur le Bureau ou dans le menu
Démarrer, pour faciliter le lancement manuel de l'agent. Ce projet ne crée
aucun raccourci automatiquement.
