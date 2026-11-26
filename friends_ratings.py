#!/usr/bin/env python3
"""Arkadaşlarımın film puanlarını kişi kişi okuyup her film için ortalamayı hesaplar.

Film başına arkadaş sayfası (letterboxd.com/USER/friends/film/SLUG/) engellendiği için
takip ettiğim herkesin puanladığı filmleri okur, friends-cache.json dosyasında saklar.

  python friends_ratings.py            # takip listesi + tam okuma (30 günde bir) + RSS
  python friends_ratings.py --rss-only # sadece RSS ile güncelle (GitHub Actions)

Letterboxd sayfalı adresleri sık sık Cloudflare doğrulamasına takıyor; engellenince
o kişide durur, okunabileni kaydeder ve eksik okumayı sonraki çalıştırmada tekrar dener.
"""
import json
import re
import sys
import time
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

import update_films as u

ROOT = Path(__file__).parent
CACHE_FILE = ROOT / "friends-cache.json"
GAP = 1.5
FULL_EVERY_DAYS = 30
MAX_PAGES = 200


def today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def get(url):
    """Sayfayı çeker ve ardından nazikçe bekler."""
    try:
        return u.fetch(url)
    finally:
        time.sleep(GAP)


def load_cache():
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"updated": None, "following": [], "friends": {}}


def save_cache(cache):
    cache["updated"] = today()
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                          encoding="utf-8")


# --- Takip listesi -------------------------------------------------------------

def get_following():
    """Takip ettiklerim; (liste, tamamı okundu mu)."""
    names, page = [], 1
    while page <= 50:
        url = f"https://letterboxd.com/{u.USER}/following/" + (f"page/{page}/" if page > 1 else "")
        try:
            text = get(url)
        except Exception as e:  # noqa: BLE001
            print(f"! Takip listesi sayfa {page} alınamadı: {e}", file=sys.stderr)
            return names, False
        found = re.findall(r'class="avatar -a40" href="/([^/"]+)/"', text)
        found = [n for n in found if n != u.USER]
        if not found:
            break
        names += [n for n in found if n not in names]
        if not re.search(rf'href="/{u.USER}/following/page/{page + 1}/"', text):
            break
        page += 1
    return names, True


# --- Bir arkadaşın puanları ----------------------------------------------------

def parse_grid(text):
    """Film ızgarasından {slug: puan(1-10)}; puansız filmler atlanır."""
    out = {}
    for chunk in text.split('<li class="griditem')[1:]:
        slug = re.search(r'data-(?:item|film)-slug="([^"]+)"', chunk)
        rating = re.search(r"\brated-(\d+)\b", chunk)
        if slug and rating and 1 <= int(rating.group(1)) <= 10:
            out[slug.group(1)] = int(rating.group(1))
    return out


def has_next(text, page):
    return re.search(rf'/page/{page + 1}/"', text) is not None


def full_read(friend):
    """Arkadaşın puanladığı tüm filmler; (puanlar, tamamı okundu mu)."""
    bases = [f"https://letterboxd.com/{friend}/films/rated/.5-5/",
             f"https://letterboxd.com/{friend}/films/"]
    ratings = {}
    for base in bases:
        page = 1
        while page <= MAX_PAGES:
            try:
                text = get(base + (f"page/{page}/" if page > 1 else ""))
            except urllib.error.HTTPError as e:
                if page == 1:
                    break  # bu adres kapalı, diğerini dene
                print(f"  ! {friend}: sayfa {page} alınamadı ({e.code})", file=sys.stderr)
                return ratings, False
            except Exception as e:  # noqa: BLE001
                print(f"  ! {friend}: {e}", file=sys.stderr)
                return ratings, False
            ratings.update(parse_grid(text))
            if not has_next(text, page):
                return ratings, True
            page += 1
        if page > 1:
            return ratings, True
    return ratings, False


def rss_ratings(friend):
    """RSS'teki son puanlar, eskiden yeniye {slug: puan}."""
    root = ET.fromstring(get(f"https://letterboxd.com/{friend}/rss/"))
    items = []
    for it in root.findall("./channel/item"):
        r = it.findtext("letterboxd:memberRating", namespaces=u.NS)
        m = re.search(r"/film/([^/]+)/", it.findtext("link") or "")
        if r and m:
            items.append((it.findtext("letterboxd:watchedDate", namespaces=u.NS) or "", m.group(1),
                          round(float(r) * 2)))
    items.sort()
    return {slug: val for _, slug, val in items if 1 <= val <= 10}


# --- Güncelleme ve hesaplama ---------------------------------------------------

def update_cache(cache, rss_only=False):
    friends = cache.setdefault("friends", {})
    if not rss_only:
        names, list_complete = get_following()
        if list_complete and names:
            cache["following"] = names
        else:
            cache["following"] = list(dict.fromkeys((cache.get("following") or []) + names))
        print(f"Takip edilen: {len(cache['following'])}" + ("" if list_complete else " (liste eksik okundu)"))
        limit = (datetime.now(timezone.utc) - timedelta(days=FULL_EVERY_DAYS)).strftime("%Y-%m-%d")
        for name in cache["following"]:
            f = friends.setdefault(name, {"ratings": {}, "fullRead": None})
            if f.get("fullRead") and f["fullRead"] > limit:
                continue
            if f.get("partialTried") == today():
                continue
            ratings, complete = full_read(name)
            if complete:
                f["ratings"] = ratings
                f["fullRead"] = today()
                f.pop("partialTried", None)
            else:
                f["ratings"] = {**f.get("ratings", {}), **ratings}
                f["partialTried"] = today()
            print(f"  {name}: {len(ratings)} puan" + ("" if complete else " (eksik)"))
        if list_complete:
            for gone in set(friends) - set(cache["following"]):
                del friends[gone]
    rss_n = 0
    for name in cache.get("following") or []:
        f = friends.setdefault(name, {"ratings": {}, "fullRead": None})
        try:
            new = rss_ratings(name)
        except Exception as e:  # noqa: BLE001
            print(f"  ! {name} RSS: {e}", file=sys.stderr)
            continue
        for slug, val in new.items():
            if f["ratings"].get(slug) != val:
                f["ratings"][slug] = val
                rss_n += 1
    print(f"RSS ile eklenen/değişen puan: {rss_n}")
    return cache


def apply(cache, films, watchlist):
    """Her filme friends (5 üzerinden ortalama) ve friendsN yazar."""
    by_slug = {}
    for name in cache.get("following") or []:
        for slug, val in (cache.get("friends", {}).get(name, {}).get("ratings") or {}).items():
            by_slug.setdefault(slug, []).append(val)

    def put(item, slug):
        vals = by_slug.get(slug) or []
        item["friends"] = round(sum(vals) / len(vals) / 2, 2) if vals else None
        item["friendsN"] = len(vals)

    for w in watchlist:
        put(w, w.get("slug"))
    for f in films:
        put(f, u.path_slug(f.get("letterboxdPath")))


def save_watchlist(wl):
    u.WATCHLIST_FILE.write_text("window.LETTERBOXD_WATCHLIST = "
                                + json.dumps(wl, ensure_ascii=False, separators=(",", ":")) + ";\n",
                                encoding="utf-8")


def current_updated_at():
    m = re.search(r'LETTERBOXD_UPDATED_AT = "([^"]*)"', u.DATA_FILE.read_text(encoding="utf-8"))
    return m.group(1) if m else datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run(rss_only=False):
    cache = update_cache(load_cache(), rss_only=rss_only)
    save_cache(cache)
    films, wl = u.load_data(), u.load_watchlist()
    apply(cache, films, wl)
    u.save_data(films, current_updated_at())
    if wl:
        save_watchlist(wl)
    total = sum(len(f.get("ratings") or {}) for f in cache["friends"].values())
    print(f"Arkadaş: {len(cache['following'])}, toplam puan: {total}, "
          f"ortalaması olan watchlist: {sum(1 for w in wl if w.get('friends') is not None)}, "
          f"izlenen: {sum(1 for f in films if f.get('friends') is not None)}")
    return cache, films, wl


if __name__ == "__main__":
    run(rss_only="--rss-only" in sys.argv)
