#!/usr/bin/env python3
"""
Mobile Games Release Scraper
- iOS     : iTunes Search API
- Android : vérification bundleId iOS sur Google Play (pas d'API tierce)
"""

import json, os, time, re
from datetime import datetime, timedelta
from pathlib import Path

try:
    import requests
except ImportError:
    os.system("pip install requests --break-system-packages -q")
    import requests

from bs4 import BeautifulSoup

# ── Config ────────────────────────────────────────────────────────────────────
DATA_FILE     = Path(__file__).parent.parent / "data" / "games.json"
LOOKBACK_DAYS = 30

IOS_SEARCH_TERMS = [
    "new game", "rpg", "action game", "puzzle", "strategy",
    "adventure", "simulation", "card game", "casual game", "platformer"
]

GENRES = {
    "6014":"Games",    "7001":"Action",       "7002":"Adventure",
    "7003":"Arcade",   "7004":"Board",         "7005":"Card",
    "7006":"Casino",   "7007":"Dice",          "7008":"Educational",
    "7009":"Family",   "7010":"Kids",          "7011":"Music",
    "7012":"Puzzle",   "7013":"Racing",        "7014":"Role Playing",
    "7015":"Simulation","7016":"Sports",        "7017":"Strategy",
    "7018":"Trivia",   "7019":"Word",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Mobile Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}

# ── Helpers ───────────────────────────────────────────────────────────────────
def load_existing():
    if DATA_FILE.exists():
        with open(DATA_FILE) as f:
            return json.load(f)
    return {"lastUpdated": "", "games": []}

def save_data(data):
    data["lastUpdated"] = datetime.utcnow().isoformat() + "Z"
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"✅ Saved {len(data['games'])} games to {DATA_FILE}")

def ios_artwork_hd(url: str, size: int = 512) -> str:
    if not url:
        return url
    return re.sub(r'\d+x\d+bb\.(jpg|png|webp)', f'{size}x{size}bb.jpg', url)

def format_price(price_val) -> str:
    try:
        if float(price_val) == 0:
            return "Free"
        return f"{float(price_val):.2f}€"
    except (TypeError, ValueError):
        if str(price_val).strip() in ("0", "0.0", "", "None"):
            return "Free"
        return str(price_val) if price_val else "Free"

def parse_date_flexible(raw: str):
    if not raw:
        return None
    raw = raw.strip()
    for fmt in (
        "%d %b %Y", "%b %d, %Y", "%B %d, %Y", "%d %B %Y",
        "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y",
    ):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            pass
    match = re.search(r'(\d{4})', raw)
    if match:
        return datetime(int(match.group(1)), 1, 1)
    return None

# ── iOS scraping ──────────────────────────────────────────────────────────────
def fetch_ios_games() -> list[dict]:
    games    = []
    seen_ids = set()
    cutoff   = datetime.utcnow() - timedelta(days=LOOKBACK_DAYS)

    for term in IOS_SEARCH_TERMS:
        try:
            params = {
                "term": term, "country": "fr", "media": "software",
                "entity": "software", "genreId": "6014",
                "limit": 50, "lang": "fr_fr",
            }
            resp = requests.get(
                "https://itunes.apple.com/search",
                params=params, timeout=15
            )
            resp.raise_for_status()

            for item in resp.json().get("results", []):
                release_raw = item.get("releaseDate", "")
                try:
                    release_dt = datetime.fromisoformat(release_raw.replace("Z", ""))
                except Exception:
                    continue
                if release_dt < cutoff:
                    continue

                app_id = str(item.get("trackId", ""))
                if app_id in seen_ids:
                    continue
                seen_ids.add(app_id)

                genre_label = "Games"
                for gid in item.get("genreIds", []):
                    if gid in GENRES and gid != "6014":
                        genre_label = GENRES[gid]
                        break

                artwork_raw = item.get("artworkUrl100", "")
                icon        = ios_artwork_hd(artwork_raw, 100)
                header_img  = ios_artwork_hd(artwork_raw, 1024)

                games.append({
                    "id":          f"ios_{app_id}",
                    "title":       item.get("trackName", ""),
                    "platform":    ["ios"],
                    "releaseDate": release_dt.strftime("%Y-%m-%d"),
                    "genre":       genre_label,
                    "developer":   item.get("artistName", ""),
                    "icon":        icon,
                    "headerImage": header_img,
                    "storeUrl":    item.get("trackViewUrl", ""),
                    "price":       format_price(item.get("price", 0)),
                    "rating":      round(item.get("averageUserRating", 0), 1) or None,
                    "bundleId":    item.get("bundleId", ""),
                })

            time.sleep(0.5)

        except Exception as e:
            print(f"⚠️  iOS fetch error for '{term}': {e}")

    print(f"📱 iOS: {len(games)} jeux trouvés")
    return games

# ── Android : scraping page Google Play via bundleId iOS ─────────────────────
def scrape_gplay_page(bundle_id: str) -> dict | None:
    """
    Charge la fiche Google Play d'un bundleId et extrait :
    title, icon, headerImage, releaseDate, price, rating, developer, genre.
    Utilise le même bundleId que l'app iOS (très souvent identique).
    """
    url = f"https://play.google.com/store/apps/details?id={bundle_id}&hl=fr&gl=fr"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        # 404 = pas d'app Android avec ce bundleId
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
    except Exception as e:
        print(f"    ↳ ⚠️  Erreur réseau pour {bundle_id}: {e}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    # ── Vérification que la page est bien une app ──
    if "Nous n'avons pas pu trouver" in resp.text or "not found" in resp.text.lower():
        return None

    # ── Extraction JSON embarqué dans la page ──────────────────────────────
    # Google Play embarque les données dans des blocs AF_initDataCallback
    raw_text = resp.text

    # Titre
    title = ""
    t_match = re.search(r'"name"\s*:\s*"([^"]{2,100})"', raw_text)
    if t_match:
        title = t_match.group(1)
    if not title:
        og = soup.find("meta", property="og:title")
        title = og["content"].split(" - ")[0] if og else ""

    if not title:
        return None

    # Icon
    icon = ""
    icon_match = re.search(r'"(https://play-lh\.googleusercontent\.com/[^"]{20,})"', raw_text)
    if icon_match:
        icon = icon_match.group(1)

    # Header image (feature graphic — plus large)
    header_img = icon  # fallback
    # Les images header sont souvent plus larges dans la page
    img_urls = re.findall(r'https://play-lh\.googleusercontent\.com/[^\s"\'\\]{20,}', raw_text)
    # Trier par longueur d'URL (les images HD ont souvent des URLs plus longues)
    img_urls = list(dict.fromkeys(img_urls))  # dédupliquer
    if len(img_urls) >= 2:
        header_img = img_urls[1]  # La 2ème est souvent le feature graphic

    # Prix
    price = "Free"
    if '"price"' in raw_text:
        price_match = re.search(r'"price"\s*:\s*"([^"]*)"', raw_text)
        if price_match:
            p = price_match.group(1).strip()
            price = "Free" if p in ("0", "", "Free", "Gratuit") else p

    # Note
    rating = None
    rating_match = re.search(r'"starRating"\s*:\s*"?([\d.]+)"?', raw_text)
    if not rating_match:
        rating_match = re.search(r'(\d\.\d)\s*sur\s*5', raw_text)
    if rating_match:
        try:
            rating = round(float(rating_match.group(1)), 1)
        except Exception:
            pass

    # Date de sortie
    release_dt = None
    # Chercher un pattern date dans le JSON embarqué
    date_patterns = [
        r'"releaseDate"\s*:\s*"([^"]+)"',
        r'"datePublished"\s*:\s*"([^"]+)"',
        r'(\d{1,2}\s+\w+\s+\d{4})',   # ex: "15 mars 2026"
        r'(\w+\s+\d{1,2},\s+\d{4})',  # ex: "Mar 5, 2026"
    ]
    for pattern in date_patterns:
        m = re.search(pattern, raw_text)
        if m:
            release_dt = parse_date_flexible(m.group(1))
            if release_dt:
                break

    # Fallback : date dans les métadonnées schema.org
    if not release_dt:
        schema = soup.find("script", type="application/ld+json")
        if schema:
            try:
                sd = json.loads(schema.string)
                raw_date = sd.get("datePublished") or sd.get("dateModified", "")
                release_dt = parse_date_flexible(raw_date)
            except Exception:
                pass

    if not release_dt:
        print(f"    ↳ ⚠️  Date introuvable pour {bundle_id}")
        return None

    # Développeur
    developer = ""
    dev_match = re.search(r'"developerName"\s*:\s*"([^"]+)"', raw_text)
    if not dev_match:
        dev_match = re.search(r'"author"\s*:\s*\{[^}]*"name"\s*:\s*"([^"]+)"', raw_text)
    if dev_match:
        developer = dev_match.group(1)

    # Genre
    genre = "Games"
    genre_match = re.search(r'"genre"\s*:\s*"([^"]+)"', raw_text)
    if genre_match:
        genre = genre_match.group(1)

    return {
        "id":          f"android_{bundle_id.replace('.', '_')}",
        "title":       title,
        "platform":    ["android"],
        "releaseDate": release_dt.strftime("%Y-%m-%d"),
        "genre":       genre,
        "developer":   developer,
        "icon":        icon,
        "headerImage": header_img,
        "storeUrl":    f"https://play.google.com/store/apps/details?id={bundle_id}",
        "price":       price,
        "rating":      rating,
        "bundleId":    bundle_id,
    }

def fetch_android_from_ios(ios_games: list[dict]) -> list[dict]:
    """
    Pour chaque jeu iOS, tente de trouver sa version Android
    en utilisant le même bundleId sur Google Play.
    """
    android_games = []
    seen_ids      = set()
    cutoff        = datetime.utcnow() - timedelta(days=LOOKBACK_DAYS)

    print(f"🔍 Vérification Android pour {len(ios_games)} jeux iOS (via bundleId)...")

    for i, ios_game in enumerate(ios_games):
        bundle_id = ios_game.get("bundleId", "")
        title     = ios_game.get("title", "")

        if not bundle_id:
            continue

        print(f"  [{i+1}/{len(ios_games)}] {title} ({bundle_id})")

        android = scrape_gplay_page(bundle_id)

        if android is None:
            print(f"    ↳ ❌ Pas de version Android")
            time.sleep(0.3)
            continue

        if android["id"] in seen_ids:
            continue
        seen_ids.add(android["id"])

        # Vérifier la fenêtre de date
        try:
            dt = datetime.strptime(android["releaseDate"], "%Y-%m-%d")
            if dt < cutoff:
                print(f"    ↳ ⏭️  Trop ancien ({android['releaseDate']})")
                time.sleep(0.3)
                continue
        except Exception:
            pass

        # Hériter de l'icon/header iOS si Google Play n'en a pas fourni
        if not android.get("icon"):
            android["icon"] = ios_game.get("icon", "")
        if not android.get("headerImage") or android["headerImage"] == android["icon"]:
            android["headerImage"] = ios_game.get("headerImage", "")

        print(f"    ↳ ✅ Trouvé ! ({android['releaseDate']}) — {android['price']}")
        android_games.append(android)

        # Pause polie pour ne pas se faire bannir
        time.sleep(1.0)

    print(f"\n🤖 Android: {len(android_games)} jeux trouvés")
    return android_games

# ── Merge ─────────────────────────────────────────────────────────────────────
def merge_games(existing, new_ios, new_android) -> list[dict]:
    all_games = {g["id"]: g for g in existing}

    for game in new_ios + new_android:
        existing_entry  = all_games.get(game["id"], {})
        existing_header = existing_entry.get("headerImage", "")
        if existing_header and not game.get("headerImage"):
            game["headerImage"] = existing_header
        all_games[game["id"]] = game

    cutoff = datetime.utcnow() - timedelta(days=90)
    today  = datetime.utcnow().date()
    pruned = []

    for game in all_games.values():
        try:
            dt = datetime.strptime(game["releaseDate"], "%Y-%m-%d")
            if dt.date() >= today or dt >= cutoff:
                pruned.append(game)
        except Exception:
            pruned.append(game)

    pruned.sort(key=lambda g: g["releaseDate"])
    return pruned

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("🎮 Mobile Games Release Scraper\n")

    existing_data  = load_existing()
    existing_games = existing_data.get("games", [])
    print(f"📂 Jeux existants : {len(existing_games)}\n")

    ios_games     = fetch_ios_games()
    android_games = fetch_android_from_ios(ios_games)
    merged        = merge_games(existing_games, ios_games, android_games)

    ios_c     = sum(1 for g in merged if 'ios'     in g.get('platform', []))
    android_c = sum(1 for g in merged if 'android' in g.get('platform', []))
    free_c    = sum(1 for g in merged if g.get('price') == 'Free')
    header_c  = sum(1 for g in merged if g.get('headerImage'))

    print(f"\n📊 Résultat :")
    print(f"   Total      : {len(merged)}")
    print(f"   iOS        : {ios_c}")
    print(f"   Android    : {android_c}")
    print(f"   Gratuits   : {free_c}")
    print(f"   Avec image : {header_c}")

    save_data({"games": merged})

if __name__ == "__main__":
    main()
