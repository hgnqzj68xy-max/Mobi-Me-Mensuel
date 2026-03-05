#!/usr/bin/env python3
import json, os, re, time, hashlib
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

DATA_FILE = Path(__file__).parent.parent / "data" / "games.json"
LOOKBACK_DAYS = 30
IOS_SEARCH_TERMS = ["new game","rpg","action game","puzzle","strategy","adventure","simulation","sports game","card game","casual game"]
ANDROID_SEARCH_TERMS = ["new game 2025","rpg mobile","action game","puzzle game","strategy mobile","adventure game","card game mobile"]
GENRES = {"6014":"Games","7001":"Action","7002":"Adventure","7003":"Arcade","7004":"Board","7005":"Card","7006":"Casino","7007":"Dice","7008":"Educational","7009":"Family","7010":"Kids","7011":"Music","7012":"Puzzle","7013":"Racing","7014":"Role Playing","7015":"Simulation","7016":"Sports","7017":"Strategy","7018":"Trivia","7019":"Word"}

def make_id(platform, title, date):
    raw = f"{platform}_{title}_{date}"
    return f"{platform}_{hashlib.md5(raw.encode()).hexdigest()[:8]}"

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

def fetch_ios_games():
    games = []
    seen_ids = set()
    cutoff = datetime.utcnow() - timedelta(days=LOOKBACK_DAYS)
    for term in IOS_SEARCH_TERMS:
        try:
            params = {"term": term, "country": "fr", "media": "software", "entity": "software", "genreId": "6014", "limit": 50, "lang": "fr_fr"}
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
                genre_ids = item.get("genreIds", [])
                genre_label = "Games"
                for gid in genre_ids:
                    if gid in GENRES and gid != "6014":
                        genre_label = GENRES[gid]
                        break
                price = item.get("formattedPrice", "Free")
                if price in ("Free", "Gratuit", "Gratis"):
                    price = "Free"
                games.append({"id": f"ios_{app_id}", "title": item.get("trackName", ""), "platform": ["ios"], "releaseDate": release_dt.strftime("%Y-%m-%d"), "genre": genre_label, "developer": item.get("artistName", ""), "icon": item.get("artworkUrl100", ""), "storeUrl": item.get("trackViewUrl", ""), "price": price, "rating": round(item.get("averageUserRating", 0), 1) or None, "bundleId": item.get("bundleId", "")})
            time.sleep(0.5)
        except Exception as e:
            print(f"⚠️  iOS fetch error for '{term}': {e}")
    print(f"📱 iOS: fetched {len(games)} games")
    return games

def fetch_android_games():
    games = []
    seen_ids = set()
    cutoff = datetime.utcnow() - timedelta(days=LOOKBACK_DAYS)
    for term in ANDROID_SEARCH_TERMS:
        try:
            results = gplay_search(term, lang="fr", country="fr", n_hits=30)
            for item in results:
                pkg = item.get("appId", "")
                if pkg in seen_ids:
                    continue
                seen_ids.add(pkg)
                try:
                    detail = gplay_app(pkg, lang="fr", country="fr")
                    released_raw = detail.get("released", "")
                    release_dt = None
                    for fmt in ("%b %d, %Y", "%d %b. %Y", "%d/%m/%Y", "%Y-%m-%d"):
                        try:
                            release_dt = datetime.strptime(released_raw, fmt)
                            break
                        except Exception:
                            pass
                    if release_dt is None or release_dt < cutoff:
                        continue
                    price_val = detail.get("price", 0)
                    price = "Free" if price_val == 0 else f"{price_val:.2f}€"
                    score = detail.get("score", None)
                    games.append({"id": f"android_{pkg.replace('.', '_')}", "title": detail.get("title", item.get("title", "")), "platform": ["android"], "releaseDate": release_dt.strftime("%Y-%m-%d"), "genre": detail.get("genre", "Games"), "developer": detail.get("developer", ""), "icon": detail.get("icon", item.get("icon", "")), "storeUrl": f"https://play.google.com/store/apps/details?id={pkg}", "price": price, "rating": round(score, 1) if score else None, "bundleId": pkg})
                    time.sleep(0.3)
                except Exception as e:
                    print(f"  ⚠️  detail error for {pkg}: {e}")
        except Exception as e:
            print(f"⚠️  Android fetch error for '{term}': {e}")
    print(f"🤖 Android: fetched {len(games)} games")
    return games

def merge_games(existing, new_ios, new_android):
    all_games = {g["id"]: g for g in existing}
    for game in new_ios + new_android:
        all_games[game["id"]] = game
    cutoff = datetime.utcnow() - timedelta(days=90)
    today = datetime.utcnow().date()
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

def main():
    print("🎮 Mobile Games Release Scraper")
    existing_data = load_existing()
    existing_games = existing_data.get("games", [])
    print(f"📂 Existing games: {len(existing_games)}")
    ios_games = fetch_ios_games()
    android_games = fetch_android_games()
    merged = merge_games(existing_games, ios_games, android_games)
    print(f"📊 Total after merge: {len(merged)} games")
    save_data({"games": merged})

if __name__ == "__main__":
    main()
