import fetch from 'node-fetch';
import gplay from 'google-play-scraper';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '../');

// Mois cible (par défaut, le mois prochain)
function targetMonth() {
  const d = new Date();
  d.setMonth(d.getMonth() + 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

const MONTH = targetMonth();

// Récupère les jeux récents depuis l'App Store
async function fetchRecentAppleGames(limit = 200) {
  const url = `https://itunes.apple.com/fr/rss/newapplications/limit=${limit}/genre=6014/json`;
  const response = await fetch(url);
  const data = await response.json();
  return data.feed.entry
    .map((app) => ({
      name: app.title.label,
      date: new Date(app.updated.label).toISOString().split('T')[0],
      platform: 'iOS',
      url: app.link.attributes.href,
    }))
    .filter((app) => app.date.startsWith(MONTH));
}

// Récupère les jeux récents depuis le Play Store
async function fetchRecentGoogleGames(limit = 200) {
  const games = await gplay.list({
    category: gplay.category.GAME,
    collection: gplay.collection.TOP_FREE,
    num: limit,
  });
  return games
    .map((game) => ({
      name: game.title,
      date: game.released ? new Date(game.released * 1000).toISOString().split('T')[0] : null,
      platform: 'Android',
      url: game.url,
    }))
    .filter((game) => game.date && game.date.startsWith(MONTH));
}

// Fusionne et dédoublonne les résultats
async function fetchAllRecentGames() {
  const [appleGames, googleGames] = await Promise.all([
    fetchRecentAppleGames(),
    fetchRecentGoogleGames(),
  ]);

  const allGames = [...appleGames, ...googleGames];
  const uniqueGames = Array.from(
    new Map(allGames.map((game) => [game.name.toLowerCase(), game])).values()
  );

  return uniqueGames;
}

// Génère le fichier JSON
async function main() {
  const games = await fetchAllRecentGames();

  const output = {
    month: MONTH,
    generatedAt: new Date().toISOString(),
    games: games.map((game) => ({
      name: game.name,
      date: game.date,
      platform: [game.platform],
      url: game.url,
    })),
  };

  const outPath = path.join(ROOT, 'data', `${MONTH}.json`);
  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  fs.writeFileSync(outPath, JSON.stringify(output, null, 2), 'utf-8');

  console.log(`✅ Données mises à jour pour ${MONTH} (${games.length} jeux)`);
}

main().catch(console.error);a
