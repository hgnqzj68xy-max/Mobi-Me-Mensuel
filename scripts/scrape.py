#!/usr/bin/env python3
"""
Mobile Games Release Scraper
- iOS     : iTunes Search API + artwork haute résolution
- Android : corrélation depuis iOS (bundleId/titre) + headerImage natif Google Play
"""

import json, os, time, hashlib, re
from datetime import datetime, timedelta
from pathlib import Path

try:
    import requests
except ImportError:
    os.system("pip install requests --break-system-packages -q")
    import requests

try:
    from google_play_scraper import search as gplay_search, app as gplay_app
except ImportError:
    os.system("pip install google-play-scraper --break-system-packages -q")
    from google_play_scraper import search as gplay_search, app as gplay_app

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
    """
    iTunes retourne une URL de type :
      https://is1-ssl.mzstatic.com/image/thumb/Purple116/.../100x100bb.jpg
    On remplace la résolution à la fin pour avoir une image HD.
    """
    if not url:
        return url
    # Remplace NNNxNNNbb.jpg (ou .png) par {size}x{size}bb.jpg
    hd = re.sub(r'\d+x\d+bb\.(jpg|png|webp)', f'{size}x{size}bb.jpg', url)
    return hd

def ios_header_from_artwork(url: str) -> str:
    """
    Pour la bannière hero on utilise une image encore plus large (1024px).
    iTunes n'a pas de vrai header promo, donc on prend l'artwork en 1024.
    """
    return ios_artwork_hd(url, size=1024)

def parse_gplay_date(raw: str):
    if not raw:
        return None
    raw = raw.strip()
    for fmt in (
        "%b %d, %Y", "%B %d, %Y", "%d %b %Y", "%d %B %Y",
        "%Y-%m-%d",  "%d/%m/%Y",  "%m/%d/%Y",  "%d-%m-%Y",
    ):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            pass
    match = re.search(r'(\d{4})', raw)
    if match:
        year = int(match.group(1))
        nums = re.findall(r'\d+', raw)
        if len(nums) >= 3:
            try:
                candidates = [int(n) for n in nums if len(n) <= 4]
                year_idx   = candidates.index(year)
                rest       = [c for i, c in enumerate(candidates) if i != year_idx]
                if rest[0] <= 12:
                    return datetime(year, rest[0], min(rest[1], 31) if len(rest) > 1 else 1)
            except Exception:
                pass
        return datetime(year, 1, 1)
    return None

def format_price(price_val) -> str:
    try:
        if float(price_val) == 0:
            return "Free"
        return f"{float(price_val):.2f}€"
    except (TypeError, ValueError):
        if str(price_val).strip() in ("0", "0.0", "", "None"):
            return "Free"
        return str(price_val) if price_val else "Free"

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
            resp = requests.get("https://itunes.apple.com/search", params=params, timeout=15)
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

                # Artwork : icône normale + version HD pour headerImage
                artwork_raw = item.get("artworkUrl100", "")
                icon        = ios_artwork_hd(artwork_raw, size=100)   # taille originale propre
                header_img  = ios_header_from_artwork(artwork_raw)     # 1024px pour le hero

                games.append({
                    "id":          f"ios_{app_id}",
                    "title":       item.get("trackName", ""),
                    "platform":    ["ios"],
                    "releaseDate": release_dt.strftime("%Y-%m-%d"),
                    "genre":       genre_label,
                    "developer":   item.get("artistName", ""),
                    "icon":        icon,
                    "headerImage": header_img,   # ← NOUVEAU
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

# ── Android : corrélation depuis iOS ─────────────────────────────────────────
def find_android_by_bundle(bundle_id: str, title: str) -> dict | None:
    candidates = []

    # Stratégie 1 — bundle ID direct
    if bundle_id:
        try:
            detail = gplay_app(bundle_id, lang="en", country="us")
            if detail:
                candidates.append(detail)
        except Exception:
            pass
        time.sleep(0.2)

    # Stratégie 2 — recherche par titre
    if not candidates:
        try:
            results = gplay_search(title, lang="en", country="us", n_hits=5)
            for r in results:
                r_title = r.get("title", "").lower()
                if title.lower()[:10] in r_title or r_title[:10] in title.lower():
                    try:
                        detail = gplay_app(r["appId"], lang="en", country="us")
                        candidates.append(detail)
                        break
                    except Exception:
                        pass
            time.sleep(0.3)
        except Exception:
            pass

    if not candidates:
        return None

    detail = candidates[0]

    release_dt = parse_gplay_date(detail.get("released", ""))
    if not release_dt:
        updated = detail.get("updated")
        if updated:
            try:
                release_dt = datetime.fromtimestamp(updated)
            except Exception:
                pass
    if not release_dt:
        return None

    pkg   = detail.get("appId", bundle_id)
    price = format_price(detail.get("price", 0))
    score = detail.get("score", None)

    # ── headerImage : Google Play fournit headerImage nativement ──
    header_img = (
        detail.get("headerImage")        # champ natif google-play-scraper
        or detail.get("video")           # parfois un lien vidéo/image promo
        or detail.get("icon", "")        # fallback : icône
    )

    return {
        "id":          f"android_{pkg.replace('.', '_')}",
        "title":       detail.get("title", title),
        "platform":    ["android"],
        "releaseDate": release_dt.strftime("%Y-%m-%d"),
        "genre":       detail.get("genre", "Games"),
        "developer":   detail.get("developer", ""),
        "icon":        detail.get("icon", ""),
        "headerImage": header_img,        # ← NOUVEAU
        "storeUrl":    f"https://play.google.com/store/apps/details?id={pkg}",
        "price":       price,
        "rating":      round(score, 1) if score else None,
        "bundleId":    pkg,
    }

def fetch_android_from_ios(ios_games: list[dict]) -> list[dict]:
    android_games = []
    seen_ids      = set()
    cutoff        = datetime.utcnow() - timedelta(days=LOOKBACK_DAYS)

    print(f"🔍 Recherche Android pour {len(ios_games)} jeux iOS...")

    for i, ios_game in enumerate(ios_games):
        title     = ios_game.get("title", "")
        bundle_id = ios_game.get("bundleId", "")

        print(f"  [{i+1}/{len(ios_games)}] {title}")

        android = find_android_by_bundle(bundle_id, title)

        if android is None:
            print(f"    ↳ ❌ Pas de version Android trouvée")
            continue
        if android["id"] in seen_ids:
            continue
        seen_ids.add(android["id"])

        try:
            dt = datetime.strptime(android["releaseDate"], "%Y-%m-%d")
            if dt < cutoff:
                print(f"    ↳ ⏭️  Trop ancien ({android['releaseDate']})")
                continue
        except Exception:
            pass

        print(f"    ↳ ✅ {android['title']} ({android['releaseDate']}) — {android['price']}")
        android_games.append(android)

    print(f"🤖 Android: {len(android_games)} jeux trouvés via corrélation iOS")
    return android_games

# ── Merge ─────────────────────────────────────────────────────────────────────
def merge_games(existing: list[dict], new_ios: list[dict], new_android: list[dict]) -> list[dict]:
    all_games = {g["id"]: g for g in existing}

    # Les nouvelles entrées écrasent les anciennes
    # mais on préserve le headerImage s'il était déjà renseigné manuellement
    for game in new_ios + new_android:
        existing_entry = all_games.get(game["id"], {})
        existing_header = existing_entry.get("headerImage", "")
        # Garder l'ancien header s'il existe et que le nouveau est un fallback icône
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
    print(f"📂 Jeux existants en base : {len(existing_games)}\n")

    ios_games     = fetch_ios_games()
    android_games = fetch_android_from_ios(ios_games)
    merged        = merge_games(existing_games, ios_games, android_games)

    ios_count     = sum(1 for g in merged if 'ios'     in g.get('platform', []))
    android_count = sum(1 for g in merged if 'android' in g.get('platform', []))
    free_count    = sum(1 for g in merged if g.get('price') == 'Free')
    header_count  = sum(1 for g in merged if g.get('headerImage'))

    print(f"\n📊 Résultat final :")
    print(f"   Total      : {len(merged)}")
    print(f"   iOS        : {ios_count}")
    print(f"   Android    : {android_count}")
    print(f"   Gratuits   : {free_count}")
    print(f"   Avec image : {header_count}")

    save_data({"games": merged})

if __name__ == "__main__":
    main()
