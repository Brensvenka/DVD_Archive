#!/usr/bin/env python3
"""Letterboxd RSS akışından films-data.js dosyasını günceller.

GitHub Actions her gün çalıştırır. Ek paket gerekmez.
"""
import html
import json
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

USER = "brensvenka"
RSS_URL = f"https://letterboxd.com/{USER}/rss/"
DATA_FILE = Path(__file__).with_name("films-data.js")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
POSTER_RE = re.compile(r"^https://a\.ltrbxd\.com/[A-Za-z0-9/._~%=&?-]+$")
NS = {"letterboxd": "https://letterboxd.com", "tmdb": "https://themoviedb.org"}


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def load_data():
    text = DATA_FILE.read_text(encoding="utf-8")
    start, end = text.index("window.LETTERBOXD_FILMS"), None
    start = text.index("[", start)
    end = text.rindex("]") + 1
    return json.loads(text[start:end])


def save_data(films, updated_at):
    body = json.dumps(films, ensure_ascii=False, separators=(",", ":"))
    DATA_FILE.write_text(
        f'window.LETTERBOXD_UPDATED_AT = "{updated_at}";\n'
        f"window.LETTERBOXD_FILMS = {body};\n",
        encoding="utf-8",
    )


def path_slug(url):
    m = re.search(r"/film/([^/]+)/", url or "")
    return m.group(1) if m else None


def simple_slug(title):
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return s or "film"


def parse_description(desc):
    """RSS açıklamasından afiş adresini ve inceleme metnini çıkarır."""
    poster = None
    m = re.search(r'<img src="([^"]+)"', desc or "")
    if m:
        cand = html.unescape(m.group(1))
        if POSTER_RE.match(cand):
            poster = cand
    paras = []
    for p in re.findall(r"<p>(.*?)</p>", desc or "", flags=re.S):
        if "<img" in p:
            continue
        t = re.sub(r"<br\s*/?>", "\n", p)
        t = html.unescape(re.sub(r"<[^>]+>", "", t)).strip()
        if not t or re.match(r"^(Re)?[Ww]atched on ", t) or t == "This review may contain spoilers.":
            continue
        paras.append(t)
    return poster, "\n\n".join(paras)


def film_details(slug):
    """Film sayfasından yönetmen, IMDb kimliği ve kısa bağlantıyı alır (en iyi çaba)."""
    info = {"director": "", "imdbId": None, "letterboxdUri": None}
    try:
        page = fetch(f"https://letterboxd.com/film/{slug}/")
    except Exception as e:  # noqa: BLE001
        print(f"  ! {slug} sayfası alınamadı: {e}", file=sys.stderr)
        return info
    m = re.search(r'name="twitter:data1" content="([^"]+)"', page)
    if m:
        info["director"] = html.unescape(m.group(1))
    m = re.search(r"imdb\.com/title/(tt\d+)", page)
    if m:
        info["imdbId"] = m.group(1)
    m = re.search(r"https://boxd\.it/\w+", page)
    if m:
        info["letterboxdUri"] = m.group(0)
    return info


def main():
    films = load_data()
    by_slug = {path_slug(f.get("letterboxdPath")): f for f in films}

    root = ET.fromstring(fetch(RSS_URL))
    items = root.findall("./channel/item")
    entries = []
    for it in items:
        date = it.findtext("letterboxd:watchedDate", namespaces=NS)
        title = it.findtext("letterboxd:filmTitle", namespaces=NS)
        if not date or not title:
            continue  # liste vb. kayıtlar
        rating = it.findtext("letterboxd:memberRating", namespaces=NS)
        poster, review = parse_description(it.findtext("description"))
        entries.append({
            "slug": path_slug(it.findtext("link")),
            "title": title,
            "year": int(it.findtext("letterboxd:filmYear", namespaces=NS) or 0) or None,
            "date": date,
            "rating": round(float(rating) * 2) if rating else None,
            "poster": poster,
            "review": review,
        })

    entries.sort(key=lambda e: e["date"])  # eskiden yeniye
    added = changed = 0
    for e in entries:
        if not e["slug"]:
            continue
        f = by_slug.get(e["slug"])
        if f is None:
            print(f"+ Yeni film: {e['title']} ({e['date']})")
            d = film_details(e["slug"])
            time.sleep(1)
            f = {
                "title": e["title"],
                "year": e["year"],
                "slug": simple_slug(e["title"]),
                "letterboxdUri": d["letterboxdUri"] or f"https://letterboxd.com/film/{e['slug']}/",
                "letterboxdPath": f"https://letterboxd.com/film/{e['slug']}/",
                "poster": e["poster"] or "",
                "director": d["director"],
                "imdb": None,
                "rating": e["rating"],
                "favorite": False,
                "review": e["review"],
                "watchDates": [e["date"]],
                "watched": e["date"],
                "art": e["title"],
                "imdbId": d["imdbId"],
            }
            films.append(f)
            by_slug[e["slug"]] = f
            added += 1
            continue

        before = json.dumps(f, sort_keys=True)
        dates = f.get("watchDates") or []
        if e["date"] not in dates:
            dates = sorted(dates + [e["date"]])
        f["watchDates"] = dates
        f["watched"] = max(dates)
        if e["rating"] is not None:
            f["rating"] = e["rating"]
        if e["review"]:
            f["review"] = e["review"]
        if not f.get("poster") and e["poster"]:
            f["poster"] = e["poster"]
        if json.dumps(f, sort_keys=True) != before:
            changed += 1

    updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    save_data(films, updated_at)
    print(f"Bitti: {added} yeni film, {changed} güncellenen film, toplam {len(films)}.")


if __name__ == "__main__":
    main()
