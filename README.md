# 📱 Mobile Games Release Calendar

Calendrier interactif des sorties de jeux mobiles iOS & Android, mis à jour automatiquement chaque semaine.

## Structure
- `index.html` — le calendrier (site statique)
- `data/games.json` — base de données des sorties
- `scripts/scrape.py` — scraper Python (iTunes API + Google Play)
- `.github/workflows/` — automatisation GitHub Actions

## Déploiement
1. Push sur GitHub
2. Settings → Pages → Source: **GitHub Actions**
3. Actions → Scrape → **Run workflow** (premier scraping)

Site dispo sur : `https://TON_USERNAME.github.io/mobile-games-calendar/`

## Mise à jour automatique
Le scraper tourne **chaque lundi à 06h UTC** et commit les nouvelles données automatiquement.
