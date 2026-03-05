/**
 * collect.js — Collecte mensuelle des sorties jeux mobiles
 * Sources : GamingOnPhone · TouchArcade · iTunes API
 * Sortie  : data/YYYY-MM.json
 */

import fetch  from 'node-fetch';
import * as cheerio from 'cheerio';
import fs     from 'fs';
import path   from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT      = path.resolve(__dirname, '..', '..');

// ── Mois cible (arg CLI ou variable d'env ou mois prochain) ──────────────────
function targetMonth() {
  const raw = process.env.TARGET_MONTH || process.argv[2];
  if (raw && /^\d{4}-\d{2}$/.test(raw)) return raw;
  const d = new Date();
  d.setMonth(d.getMonth() + 1);
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}`;
}

const MONTH = targetMonth();
const [YEAR, MON] = MONTH.split('-').map(Number);
const MON_PAD = String(MON).padStart(2,'0');

console.log(`\n🗓️  Collecte pour : ${MONTH}\n${'─'.repeat(50)}`);

// ── Helpers ──────────────────────────────────────────────────────────────────
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function safeFetch(url, opts = {}) {
  try {
    const res = await fetch(url, {
      ...opts,
      headers: {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8',
        ...opts.headers,
      },
      signal: AbortSignal.timeout(12000),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res;
  } catch (e) {
    console.warn(`  ⚠️  Fetch failed: ${url} — ${e.message}`);
    return null;
  }
}

// ── SOURCE 1 : GamingOnPhone ─────────────────────────────────────────────────
async function scrapeGamingOnPhone() {
  console.log('\n📰 GamingOnPhone — scraping…');
  const games = [];

  // Page "upcoming games" + news du mois
  const urls = [
    'https://gamingonphone.com/upcoming-mobile-games/',
    `https://gamingonphone.com/?s=${YEAR}+mobile+games+${MON_PAD}`,
  ];

  for (const url of urls) {
    const res = await safeFetch(url);
    if (!res) continue;
    const html = await res.text();
    const $ = cheerio.load(html);

    // Cherche les articles qui mentionnent une date de ce mois
    $('article, .post, .entry').each((_, el) => {
      const title = $(el).find('h2, h3, .entry-title').first().text().trim();
      const link  = $(el).find('a').first().attr('href') || '';
      const text  = $(el).text();

      if (!title) return;

      // Détecte les mois FR + EN
      const monthNames = {
        'january':1,'february':2,'march':3,'april':4,'may':5,'june':6,
        'july':7,'august':8,'september':9,'october':10,'november':11,'december':12,
        'janvier':1,'février':2,'mars':3,'avril':4,'mai':5,'juin':6,
        'juillet':7,'août':8,'septembre':9,'octobre':10,'novembre':11,'décembre':12,
      };

      // Cherche une date dans le texte — deux formats : "March 15" et "15 mars"
      // Regex séparés pour éviter le faux positif "March 2026" → "March 20"
      const RX_MD = /\b(january|february|march|april|may|june|july|august|september|october|november|december|janvier|f\u00e9vrier|mars|avril|mai|juin|juillet|ao\u00fbt|septembre|octobre|novembre|d\u00e9cembre)\s+(\d{1,2})\b(?!\d)/gi;
      const RX_DM = /\b(\d{1,2})\b(?!\d)\s+(january|february|march|april|may|june|july|august|september|october|november|december|janvier|f\u00e9vrier|mars|avril|mai|juin|juillet|ao\u00fbt|septembre|octobre|novembre|d\u00e9cembre)\b/gi;
      let match;
      let foundDate = null;

      RX_MD.lastIndex = 0;
      while ((match = RX_MD.exec(text)) !== null) {
        const monNum = monthNames[match[1].toLowerCase()];
        const day    = parseInt(match[2]);
        if (monNum === MON && day >= 1 && day <= 31) {
          foundDate = `${YEAR}-${MON_PAD}-${String(day).padStart(2,'0')}`;
          break;
        }
      }
      if (!foundDate) {
        RX_DM.lastIndex = 0;
        while ((match = RX_DM.exec(text)) !== null) {
          const day    = parseInt(match[1]);
          const monNum = monthNames[match[2].toLowerCase()];
          if (monNum === MON && day >= 1 && day <= 31) {
            foundDate = `${YEAR}-${MON_PAD}-${String(day).padStart(2,'0')}`;
            break;
          }
        }
      }

      // Aussi cherche "March 2026" dans le titre pour les previews du mois entier
      if (!foundDate) {
        const monthMatch = title.match(/([a-zéû]+)\s+2026/i);
        if (monthMatch) {
          const mn = monthNames[monthMatch[1].toLowerCase()];
          if (mn === MON) foundDate = `${YEAR}-${MON_PAD}-01`; // date approximative
        }
      }

      if (foundDate && title.length > 5 && title.length < 120) {
        // Extrait le nom du jeu depuis le titre de l'article
        const gameName = extractGameName(title);
        if (gameName) {
          games.push({
            name: gameName,
            date: foundDate,
            source: 'GamingOnPhone',
            sourceUrl: link,
            confidence: 60,
          });
        }
      }
    });

    await sleep(1500);
  }

  console.log(`  ✅ ${games.length} entrées trouvées`);
  return games;
}

// ── SOURCE 2 : TouchArcade ───────────────────────────────────────────────────
async function scrapeTouchArcade() {
  console.log('\n🎮 TouchArcade — scraping…');
  const games = [];
  // TouchArcade publie des "New Game Releases" hebdomadaires
  const searchUrl = `https://toucharcade.com/?s=new+releases+${YEAR}`;
  const res = await safeFetch(searchUrl);
  if (!res) return games;

  const html = await res.text();
  const $ = cheerio.load(html);

  $('article').each((_, el) => {
    const title = $(el).find('h2, h3').first().text().trim();
    const link  = $(el).find('a').first().attr('href') || '';
    const date  = $(el).find('time').attr('datetime') || '';

    if (!title || !date) return;

    // Ne garde que les articles du bon mois
    if (!date.startsWith(MONTH)) return;

    const gameName = extractGameName(title);
    if (gameName) {
      games.push({
        name: gameName,
        date: date.slice(0,10),
        source: 'TouchArcade',
        sourceUrl: link,
        confidence: 65,
      });
    }
  });

  console.log(`  ✅ ${games.length} entrées trouvées`);
  return games;
}

// ── Extrait un nom de jeu depuis un titre d'article ──────────────────────────
function extractGameName(title) {
  // Supprime les patterns courants de titres d'articles
  const cleaned = title
    .replace(/launches?|releases?|coming|arrives?|available|mobile|ios|android|global|soft.?launch/gi, '')
    .replace(/\b(on|to|for|in|at|this|the|a|an)\b/gi, '')
    .replace(/march|april|may|june|july|august|september|october|november|december|janvier|février|mars|avril|mai|juin|juillet|août/gi, '')
    .replace(/\d{4}|\d{1,2}(st|nd|rd|th)/gi, '')
    .replace(/[,;:.!?–—]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

  // Prend les premiers mots significatifs (le nom du jeu est généralement au début)
  const words = cleaned.split(' ').filter(w => w.length > 1);
  if (words.length === 0) return null;
  return words.slice(0, 5).join(' ').trim();
}

// ── VÉRIFICATION iTunes API ───────────────────────────────────────────────────
async function verifyWithItunes(games) {
  console.log('\n🍎 Vérification iTunes API…');
  const verified = [];

  for (const g of games) {
    // Recherche par nom sur l'iTunes Search API
    const query = encodeURIComponent(g.name);
    const url   = `https://itunes.apple.com/search?term=${query}&entity=software&country=fr&limit=3&media=software`;
    const res   = await safeFetch(url);

    if (res) {
      const data = await res.json();
      const result = data.results?.[0];

      if (result) {
        const releaseDate = result.releaseDate?.slice(0,10) || null;
        const storeDate   = releaseDate;

        // Calcul du score de confiance
        let confidence = g.confidence;
        if (storeDate) {
          const diff = Math.abs(daysDiff(g.date, storeDate));
          if (diff === 0)       confidence = Math.min(100, confidence + 30);
          else if (diff <= 3)   confidence = Math.min(100, confidence + 15);
          else if (diff <= 7)   confidence = Math.min(100, confidence + 5);
          else                  confidence = Math.max(20,  confidence - 20);
        }

        verified.push({
          ...g,
          appStoreId:   String(result.trackId),
          appStoreName: result.trackName,
          appStoreDate: storeDate,
          icon:         result.artworkUrl100 || null,
          genre:        result.primaryGenreName || null,
          confidence,
          // Si les dates divergent fortement → signale le conflit
          dateConflict: storeDate && Math.abs(daysDiff(g.date, storeDate)) > 7,
        });

        console.log(`  ${confidence >= 80 ? '✅' : confidence >= 50 ? '🟡' : '⚠️'} ${g.name} — conf: ${confidence}%`);
      } else {
        verified.push({ ...g, appStoreId: null });
        console.log(`  ❓ ${g.name} — introuvable sur iTunes`);
      }
    } else {
      verified.push({ ...g, appStoreId: null });
    }

    await sleep(300); // respect rate-limit Apple
  }

  return verified;
}

function daysDiff(a, b) {
  return Math.round((new Date(b) - new Date(a)) / 86400000);
}

// ── DÉDOUBLONNAGE ────────────────────────────────────────────────────────────
function deduplicate(games) {
  const seen  = new Map();
  const result = [];

  for (const g of games) {
    // Clé de dédup : nom normalisé (lowercase, sans poncutation)
    const key = g.name.toLowerCase().replace(/[^a-z0-9]/g, '');

    if (seen.has(key)) {
      // Garde la version avec la meilleure confiance
      const existing = seen.get(key);
      if (g.confidence > existing.confidence) {
        result[result.indexOf(existing)] = g;
        seen.set(key, g);
      }
    } else {
      seen.set(key, g);
      result.push(g);
    }
  }

  return result.sort((a, b) => a.date.localeCompare(b.date));
}

// ── GÉNÈRE LE JSON FINAL ──────────────────────────────────────────────────────
function buildOutput(games) {
  return {
    month:       MONTH,
    generatedAt: new Date().toISOString(),
    sources:     ['GamingOnPhone', 'TouchArcade', 'iTunes API'],
    stats: {
      total:     games.length,
      confirmed: games.filter(g => g.confidence >= 80).length,
      probable:  games.filter(g => g.confidence >= 50 && g.confidence < 80).length,
      uncertain: games.filter(g => g.confidence < 50).length,
      conflicts: games.filter(g => g.dateConflict).length,
    },
    games: games.map(g => ({
      // Champs pour l'admin.html
      d:          g.date.slice(8,10),           // "01" à "31"
      date:       g.date,                       // "2026-04-01"
      w:          dayOfWeek(g.date),
      n:          g.appStoreName || g.name,     // nom App Store prioritaire
      nameRaw:    g.name,                       // nom extrait du scraping
      t:          g.genre ? [g.genre] : [],
      i:          g.appStoreId  || '',
      a:          '',                           // Google Play — à compléter manuellement
      hot:        false,                        // à cocher dans l'admin
      confidence: g.confidence,
      dateConflict: !!g.dateConflict,
      sources:    [g.source],
      appStoreDate: g.appStoreDate || null,
      icon:       g.icon || null,
    })),
  };
}

function dayOfWeek(iso) {
  const days = ['Dim','Lun','Mar','Mer','Jeu','Ven','Sam'];
  return days[new Date(iso + 'T12:00:00Z').getDay()];
}

// ── MAIN ─────────────────────────────────────────────────────────────────────
async function main() {
  try {
    // 1. Scrape les sources
    const gopGames = await scrapeGamingOnPhone();
    const taGames  = await scrapeTouchArcade();

    // 2. Fusionne et dédoublonne
    const allGames = deduplicate([...gopGames, ...taGames]);
    console.log(`\n🔀 Après fusion : ${allGames.length} jeux uniques`);

    // 3. Vérifie avec iTunes
    const verified = await verifyWithItunes(allGames);

    // 4. Construit le JSON
    const output = buildOutput(verified);

    // 5. Écrit le fichier
    const outPath = path.join(ROOT, 'data', `${MONTH}.json`);
    fs.mkdirSync(path.dirname(outPath), { recursive: true });
    fs.writeFileSync(outPath, JSON.stringify(output, null, 2), 'utf-8');

    // 6. Résumé
    console.log(`\n${'═'.repeat(50)}`);
    console.log(`✅ Collecte terminée — ${output.stats.total} jeux`);
    console.log(`   ✅ Confirmés  : ${output.stats.confirmed}`);
    console.log(`   🟡 Probables  : ${output.stats.probable}`);
    console.log(`   ⚠️  Incertains : ${output.stats.uncertain}`);
    console.log(`   🔴 Conflits   : ${output.stats.conflicts}`);
    console.log(`   📄 Fichier    : data/${MONTH}.json`);
    console.log(`${'═'.repeat(50)}\n`);

  } catch (err) {
    console.error('❌ Erreur fatale :', err);
    process.exit(1);
  }
}

main();
