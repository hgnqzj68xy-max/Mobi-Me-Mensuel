#!/usr/bin/env python3
"""
Mobile Games Release Scraper
- iOS                    : iTunes Search API
- Android                : corrélation bundleId iOS → Google Play (scraping direct)
- Upcoming iOS/Android   : PocketGamer Agenda
- Upcoming Android       : Google Play Pre-registration (détecté lors du scraping)
"""

import json, os, time, re
from datetime import datetime, timedelta
from pathlib import Path

try:
    import requests
except ImportError:
    os.system("pip install requests --break-system-packages -q")
    import requests

try:
    from bs4 import BeautifulSoup
except ImportError:
    os.system("pip install beautifulsoup4 --break-system-packages -q")
    from bs4 import BeautifulSoup

# ── Config ────────────────────────────────────────────────────────────────────
DATA_FILE      = Path(__file__).parent.parent / "data" / "games.json"
LOOKBACK_DAYS  = 30
LOOKAHEAD_DAYS = 90

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

HEADERS_MOBILE = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Mobile Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

HEADERS_DESKTOP = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
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
    raw = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', raw)

    for fmt in (
        "%B %d, %Y", "%b %d, %Y",
        "%d %B %Y",  "%d %b %Y",
        "%Y-%m-%d",  "%d/%m/%Y",  "%m/%d/%Y",
        "%B %Y",     "%b %Y",
    ):
        try:
            return datetime.strptime(raw.strip(), fmt)
        except ValueError:
            pass

    # Trimestre Q1/Q2/Q3/Q4
    q_match = re.match(r'Q([1-4])\s+(\d{4})', raw.strip())
    if q_match:
        q, year = int(q_match.group(1)), int(q_match.group(2))
        return datetime(year, (q - 1) * 3 + 1, 1)

    # Fallback année + mois texte
    match = re.search(r'(\d{4})', raw)
    if match:
        year = int(match.group(1))
        months_en   = ["january","february","march","april","may","june",
                       "july","august","september","october","november","december"]
        months_abbr = ["jan","feb","mar","apr","may","jun",
                       "jul","aug","sep","oct","nov","dec"]
        raw_lower = raw.lower()
        for i, (full, abbr) in enumerate(zip(months_en, months_abbr), 1):
            if full in raw_lower or abbr in raw_lower:
                day_match = re.search(r'\b(\d{1,2})\b', raw)
                day = int(day_match.group(1)) if day_match else 1
                try:
                    return datetime(year, i, min(day, 28))
                except Exception:
                    return datetime(year, i, 1)
        return datetime(year, 1, 1)
    return None

def is_upcoming(date_str: str) -> bool:
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date() > datetime.utcnow().date()
    except Exception:
        return False

# ── iOS ───────────────────────────────────────────────────────────────────────
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

                artwork_raw = item.get("artworkUrl100", "")
                games.append({
                    "id":          f"ios_{app_id}",
                    "title":       item.get("trackName", ""),
                    "platform":    ["ios"],
                    "releaseDate": release_dt.strftime("%Y-%m-%d"),
                    "genre":       genre_label,
                    "developer":   item.get("artistName", ""),
                    "icon":        ios_artwork_hd(artwork_raw, 100),
                    "headerImage": ios_artwork_hd(artwork_raw, 1024),
                    "storeUrl":    item.get("trackViewUrl", ""),
                    "price":       format_price(item.get("price", 0)),
                    "rating":      round(item.get("averageUserRating", 0), 1) or None,
                    "bundleId":    item.get("bundleId", ""),
                    "status":      "released",
                    "source":      "itunes",
                })
            time.sleep(0.5)
        except Exception as e:
            print(f"⚠️  iOS fetch error for '{term}': {e}")

    print(f"📱 iOS: {len(games)} jeux trouvés")
    return games

# ── Android via bundleId ──────────────────────────────────────────────────────
def scrape_gplay_page(bundle_id: str) -> dict | None:
    url = f"https://play.google.com/store/apps/details?id={bundle_id}&hl=fr&gl=fr"
    try:
        resp = requests.get(url, headers=HEADERS_MOBILE, timeout=15)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
    except Exception as e:
        print(f"    ↳ ⚠️  {bundle_id}: {e}")
        return None

    raw = resp.text
    if "Nous n'avons pas pu trouver" in raw or "not found" in raw.lower():
        return None

    soup = BeautifulSoup(raw, "html.parser")

    # Titre
    title = ""
    og = soup.find("meta", property="og:title")
    if og:
        title = og.get("content", "").split(" - ")[0].strip()
    if not title:
        m = re.search(r'"name"\s*:\s*"([^"]{2,100})"', raw)
        if m:
            title = m.group(1)
    if not title:
        return None

    # ── Statut pre-registration ──
    status = "released"
    if any(kw in raw.lower() for kw in ["pre-register","préinscription","preregister","pre_register"]):
        status = "upcoming"

    # Icon & header
    icon = ""
    m = re.search(r'"(https://play-lh\.googleusercontent\.com/[^"]{20,})"', raw)
    if m:
        icon = m.group(1)
    img_urls = list(dict.fromkeys(
        re.findall(r'https://play-lh\.googleusercontent\.com/[^\s"\'\\]{20,}', raw)
    ))
    header_img = img_urls[1] if len(img_urls) >= 2 else icon

    # Prix
    price = "Free"
    pm = re.search(r'"price"\s*:\s*"([^"]*)"', raw)
    if pm:
        p = pm.group(1).strip()
        price = "Free" if p in ("0","","Free","Gratuit") else p

    # Note
    rating = None
    for pat in (r'"starRating"\s*:\s*"?([\d.]+)"?', r'(\d\.\d)\s*sur\s*5'):
        m = re.search(pat, raw)
        if m:
            try:
                rating = round(float(m.group(1)), 1)
                break
            except Exception:
                pass

    # Date
    release_dt = None
    for pattern in (
        r'"releaseDate"\s*:\s*"([^"]+)"',
        r'"datePublished"\s*:\s*"([^"]+)"',
        r'(\d{1,2}\s+\w+\s+\d{4})',
        r'(\w+\s+\d{1,2},\s+\d{4})',
    ):
        m = re.search(pattern, raw)
        if m:
            release_dt = parse_date_flexible(m.group(1))
            if release_dt:
                break
    if not release_dt:
        schema = soup.find("script", type="application/ld+json")
        if schema:
            try:
                sd = json.loads(schema.string)
                release_dt = parse_date_flexible(sd.get("datePublished") or sd.get("dateModified",""))
            except Exception:
                pass
    if not release_dt:
        return None

    developer = ""
    for pat in (r'"developerName"\s*:\s*"([^"]+)"', r'"author"[^}]*"name"\s*:\s*"([^"]+)"'):
        m = re.search(pat, raw)
        if m:
            developer = m.group(1)
            break

    genre = "Games"
    m = re.search(r'"genre"\s*:\s*"([^"]+)"', raw)
    if m:
        genre = m.group(1)

    return {
        "id":          f"android_{bundle_id.replace('.','_')}",
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
        "status":      status,
        "source":      "gplay",
    }

def fetch_android_from_ios(ios_games: list[dict]) -> list[dict]:
    android_games = []
    seen_ids      = set()
    cutoff        = datetime.utcnow() - timedelta(days=LOOKBACK_DAYS)

    print(f"🔍 Vérification Android pour {len(ios_games)} jeux iOS...")

    for i, ios_game in enumerate(ios_games):
        bundle_id = ios_game.get("bundleId","")
        title     = ios_game.get("title","")
        if not bundle_id:
            continue

        print(f"  [{i+1}/{len(ios_games)}] {title}")
        android = scrape_gplay_page(bundle_id)

        if android is None:
            print(f"    ↳ ❌ Pas de version Android")
            time.sleep(0.3)
            continue
        if android["id"] in seen_ids:
            continue
        seen_ids.add(android["id"])

        try:
            dt = datetime.strptime(android["releaseDate"], "%Y-%m-%d")
            if dt < cutoff:
                print(f"    ↳ ⏭️  Trop ancien ({android['releaseDate']})")
                time.sleep(0.3)
                continue
        except Exception:
            pass

        if not android.get("icon"):
            android["icon"] = ios_game.get("icon","")
        if not android.get("headerImage") or android["headerImage"] == android["icon"]:
            android["headerImage"] = ios_game.get("headerImage","")

        status_label = "🔔 upcoming" if android["status"] == "upcoming" else "✅ released"
        print(f"    ↳ {status_label} ({android['releaseDate']}) — {android['price']}")
        android_games.append(android)
        time.sleep(1.0)

    print(f"\n🤖 Android: {len(android_games)} jeux trouvés")
    return android_games

# ── PocketGamer Upcoming ──────────────────────────────────────────────────────
def fetch_pocketgamer_upcoming() -> list[dict]:
    print("📡 PocketGamer: scraping upcoming...")
    games = []
    now   = datetime.utcnow()

    try:
        resp = requests.get(
            "https://www.pocketgamer.com/upcoming-games/",
            headers=HEADERS_DESKTOP,
            timeout=15
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"  ⚠️  PocketGamer inaccessible: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")

    rows = (
        soup.find_all(class_=re.compile(r"upcoming|game.?item|release|article", re.I)) or
        soup.find_all("article") or
        soup.find_all("li", class_=re.compile(r"game|item", re.I))
    )

    seen_titles = set()

    for row in rows[:80]:
        try:
            title_el = row.find(["h2","h3","h4","strong"])
            if not title_el:
                a = row.find("a")
                title_el = a
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if not title or len(title) < 3:
                continue
            key = title.lower().strip()
            if key in seen_titles:
                continue
            seen_titles.add(key)

            # Date
            text = row.get_text(" ", strip=True)
            release_dt = None

            # Chercher date dans attribut time
            time_el = row.find("time")
            if time_el:
                release_dt = parse_date_flexible(
                    time_el.get("datetime","") or time_el.get_text(strip=True)
                )

            # Chercher dans le texte
            if not release_dt:
                candidates = re.findall(
                    r'(Q[1-4]\s+\d{4}|\d{1,2}\s+\w+\s+\d{4}|\w+\s+\d{1,2},?\s+\d{4}|\d{4}-\d{2}-\d{2})',
                    text
                )
                for c in candidates:
                    release_dt = parse_date_flexible(c)
                    if release_dt:
                        break

            if not release_dt:
                continue

            # Fenêtre : passé récent + futur
            future_limit = now + timedelta(days=LOOKAHEAD_DAYS)
            if release_dt < now - timedelta(days=7) or release_dt > future_limit:
                continue

            # Plateforme
            text_lower = text.lower()
            platform = []
            if any(kw in text_lower for kw in ["ios","iphone","ipad","apple"]):
                platform.append("ios")
            if any(kw in text_lower for kw in ["android","google play"]):
                platform.append("android")
            if not platform:
                platform = ["ios","android"]

            # Image
            icon = ""
            img = row.find("img")
            if img:
                icon = (img.get("src","") or img.get("data-src","") or
                        img.get("data-lazy-src",""))
                if icon.startswith("//"):
                    icon = "https:" + icon

            # Store URL
            store_url = ""
            for a in row.find_all("a", href=True):
                href = a["href"]
                if "play.google.com" in href or "apps.apple.com" in href:
                    store_url = href
                    break
            if not store_url:
                a = row.find("a", href=True)
                if a:
                    href = a["href"]
                    store_url = href if href.startswith("http") else f"https://www.pocketgamer.com{href}"

            status = "upcoming" if release_dt.date() > now.date() else "released"
            game_id = f"pg_{re.sub(r'[^a-z0-9]','_', key)[:40]}"

            games.append({
                "id":          game_id,
                "title":       title,
                "platform":    platform,
                "releaseDate": release_dt.strftime("%Y-%m-%d"),
                "genre":       "Games",
                "developer":   "",
                "icon":        icon,
                "headerImage": icon,
                "storeUrl":    store_url,
                "price":       "Free",
                "rating":      None,
                "bundleId":    "",
                "status":      status,
                "source":      "pocketgamer",
            })

        except Exception:
            continue

    print(f"  📡 PocketGamer: {len(games)} jeux trouvés")
    return games

# ── Merge ─────────────────────────────────────────────────────────────────────
def merge_games(existing, *new_lists) -> list[dict]:
    all_games = {g["id"]: g for g in existing}

    for game_list in new_lists:
        for game in game_list:
            existing_entry = all_games.get(game["id"], {})
            # Préserver headerImage existant
            if existing_entry.get("headerImage") and not game.get("headerImage"):
                game["headerImage"] = existing_entry["headerImage"]
            # Ne pas rétrograder released → upcoming
            if existing_entry.get("status") == "released":
                game["status"] = "released"
            all_games[game["id"]] = game

    # Fusion par titre (PocketGamer peut dupliquer un jeu iTunes)
    source_priority = {"itunes": 0, "gplay": 1, "pocketgamer": 2}
    by_title: dict[str, list] = {}
    for g in all_games.values():
        by_title.setdefault(g["title"].lower().strip(), []).append(g)

    merged_final = {}
    for group in by_title.values():
        group.sort(key=lambda g: source_priority.get(g.get("source",""), 9))
        primary = group[0]
        for secondary in group[1:]:
            for p in secondary.get("platform", []):
                if p not in primary["platform"]:
                    primary["platform"].append(p)
            if not primary.get("icon") and secondary.get("icon"):
                primary["icon"] = secondary["icon"]
            if not primary.get("headerImage") and secondary.get("headerImage"):
                primary["headerImage"] = secondary["headerImage"]
            if not primary.get("storeUrl") and secondary.get("storeUrl"):
                primary["storeUrl"] = secondary["storeUrl"]
        merged_final[primary["id"]] = primary

    # Pruning
    cutoff       = datetime.utcnow() - timedelta(days=90)
    future_limit = datetime.utcnow() + timedelta(days=LOOKAHEAD_DAYS)
    pruned = []
    for game in merged_final.values():
        try:
            dt = datetime.strptime(game["releaseDate"], "%Y-%m-%d")
            if cutoff <= dt <= future_limit:
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
    pg_games      = fetch_pocketgamer_upcoming()

    merged = merge_games(existing_games, ios_games, android_games, pg_games)

    ios_c      = sum(1 for g in merged if "ios"     in g.get("platform",[]))
    android_c  = sum(1 for g in merged if "android" in g.get("platform",[]))
    upcoming_c = sum(1 for g in merged if g.get("status") == "upcoming")
    free_c     = sum(1 for g in merged if g.get("price") == "Free")

    print(f"\n📊 Résultat :")
    print(f"   Total       : {len(merged)}")
    print(f"   iOS         : {ios_c}")
    print(f"   Android     : {android_c}")
    print(f"   🔔 Upcoming  : {upcoming_c}")
    print(f"   Gratuits    : {free_c}")
    for src in ("itunes","gplay","pocketgamer"):
        n = sum(1 for g in merged if g.get("source") == src)
        print(f"   [{src}]  : {n}")

    save_data({"games": merged})

if __name__ == "__main__":
    main()
