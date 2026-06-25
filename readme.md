# YT-Podcast — PaduTeam sur Apple Podcasts

Convertit la chaîne YouTube **PaduTeam** en vrai flux RSS podcast (audio uniquement).

## Déploiement sur Render (gratuit, 5 minutes)

### 1. Mettre les fichiers sur GitHub

1. Crée un compte [github.com](https://github.com) si tu n'en as pas
2. Crée un nouveau dépôt public : **New repository** → nom `yt-podcast` → Create
3. Upload les 3 fichiers (`app.py`, `requirements.txt`, `render.yaml`) via **Add file → Upload files**

### 2. Déployer sur Render

1. Crée un compte sur [render.com](https://render.com) (gratuit)
2. **New → Web Service**
3. Connecte ton compte GitHub et sélectionne le dépôt `yt-podcast`
4. Render détecte automatiquement le `render.yaml`
5. Clique **Create Web Service**

### 3. Mettre à jour BASE_URL

Une fois déployé, Render te donne une URL du type `https://yt-podcast-xxxx.onrender.com`.

Dans Render → ton service → **Environment** → modifie `BASE_URL` avec cette URL exacte.

Puis **Manual Deploy → Deploy latest commit** pour relancer.

### 4. Ajouter dans Apple Podcasts

1. Ouvre Apple Podcasts
2. Menu **Fichier → S'abonner à un podcast** (macOS) ou cherche l'option **Ajouter par URL** (iOS : onglet Bibliothèque → ... → Ajouter un podcast par URL)
3. Colle : `https://ton-url.onrender.com/feed.xml`

## Notes

- Le plan gratuit Render met l'app en veille après 15 min d'inactivité → le premier chargement peut prendre ~30s
- Le cache audio dure 1h (les URLs YouTube expirent)
- Pour changer de chaîne : modifie `CHANNEL_ID` et `CHANNEL_NAME` dans les variables d'environnement Render
