# Bot Telegram — Sponge Exotic

Bot d'accueil qui répond à `/start` (ou à n'importe quel message) par la
bannière, le message de bienvenue et deux boutons :
- 👻 Snapchat → https://snapchat.com/add/m_mara59
- 🛍️ Boutique → https://nocturne-neon-boutique.lovable.app

Commandes :
- `/start` : message de bienvenue (image + boutons).
- `/broadcast <message>` : envoie `<message>` à **tous** les utilisateurs qui
  ont déjà écrit au bot. ⚠️ Accessible à n'importe qui.

## Fichiers
- `bot.py` : le code du bot (texte, liens et boutons à modifier ici).
- `banner.png` : l'image de bienvenue (remplace-la pour changer la bannière).
- `bot.db` : base SQLite créée automatiquement, stocke les chat_id pour le broadcast.
- `requirements.txt` : les dépendances (`python-telegram-bot`, `aiohttp`).
- `railway.json` : configuration de déploiement Railway.
- `.gitignore` : exclut `.env`, `bot.db` et `__pycache__`.
- `Démarrer le bot.bat` : double-clique pour lancer le bot en local (Windows).

## Lancer en local (une seule fois pour installer)
```
python -m pip install -r requirements.txt
```
Crée un fichier `.env` à côté de `bot.py` (il est ignoré par git) contenant :
```
BOT_TOKEN=ton_token_ici
```
Puis double-clique sur `Démarrer le bot.bat`, ou :
```
python bot.py
```
La fenêtre doit rester ouverte. Arrêt avec `Ctrl+C`.

## Héberger sur Railway
1. Crée un compte sur [railway.app](https://railway.app) et connecte ton dépôt
   GitHub contenant ce dossier.
2. Railway détecte `railway.json` et `requirements.txt` automatiquement.
3. Ajoute les variables d'environnement :
   - `BOT_TOKEN` = le token donné par @BotFather
4. Ajoute un **volume** Railway monté sur `/data` (pour que `bot.db` et la liste
   des utilisateurs survivent aux redéploiements). Le bot détecte
   automatiquement le volume et écrit dans `/data/bot.db`.
5. Déploie. Le bot fonctionne dans les deux cas :
   - **sans domaine public** → mode *polling* (le plus simple, rien à configurer) ;
   - **avec un domaine public** (Settings → Networking) → mode *webhook*, le bot
     enregistre lui-même `https://<ton-domaine>/webhook`. Pense alors à mettre le
     port cible sur `8080` (ou à définir une variable `PORT` identique).
   Dans les deux cas, un serveur HTTP répond sur `/health` pour le healthcheck.
6. Redéploie après tout changement de code : le conteneur ne se met pas à jour
   tout seul si l'auto-deploy GitHub n'est pas activé.

⚠️ Ce dépôt est **public** : le token ne doit jamais y apparaître. Utilise la
variable d'environnement `BOT_TOKEN` sur Railway, et un fichier `.env` local
(non versionné) pour tes tests.
