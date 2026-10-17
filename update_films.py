#!/usr/bin/env python3
"""Letterboxd RSS akışından films-data.js dosyasını günceller.

GitHub Actions her gün çalıştırır. Afiş renkleri için Pillow kullanır.
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


def fetch_bytes(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def poster_colors(url):
    """Afişin baskın rengini ve en canlı rengini (#rrggbb) döndürür."""
    import colorsys
    import io
    from PIL import Image
    img = Image.open(io.BytesIO(fetch_bytes(url))).convert("RGB")
    img.thumbnail((48, 72))
    pal = img.quantize(colors=6, method=Image.Quantize.MEDIANCUT)
    raw = pal.getpalette()[:18]
    counts = sorted(pal.getcolors(), reverse=True)
    cols = [tuple(raw[i * 3:i * 3 + 3]) for _, i in counts]
    hexc = lambda c: "#%02x%02x%02x" % c
    dominant = cols[0]

    def vivid(c):
        h, l, s = colorsys.rgb_to_hls(*[x / 255 for x in c])
        return s * (1 - abs(l - 0.5) * 2)

    accent = max(cols, key=vivid)
    h, l, s = colorsys.rgb_to_hls(*[x / 255 for x in accent])
    accent = tuple(round(x * 255) for x in colorsys.hls_to_rgb(h, min(max(l, 0.45), 0.7), max(s, 0.35)))
    return [hexc(dominant), hexc(accent)]


def add_colors(films, limit=800):
    try:
        import PIL  # noqa: F401
    except ImportError:
        print("Pillow yok, renkler atlandı.", file=sys.stderr)
        return 0
    done = 0
    for f in films:
        if done >= limit:
            break
        if f.get("colors") or not POSTER_RE.match(f.get("poster") or ""):
            continue
        try:
            f["colors"] = poster_colors(f["poster"].replace("-0-600-0-900-", "-0-460-0-690-"))
            done += 1
            time.sleep(0.15)
        except Exception as e:  # noqa: BLE001
            print(f"  ! renk alınamadı: {f.get('title')}: {e}", file=sys.stderr)
    return done


def make_og(films):
    """Paylaşım önizlemesi için son izlenen afişlerden 1200x630 og.png üretir."""
    try:
        import io
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return False
    W, H = 1200, 630
    img = Image.new("RGB", (W, H), "#12171d")
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        c = tuple(round(a + (b - a) * t) for a, b in zip((24, 32, 42), (15, 19, 24)))
        d.line([(0, y), (W, y)], fill=c)
    recent = sorted([f for f in films if f.get("watched") and POSTER_RE.match(f.get("poster") or "")],
                    key=lambda f: f["watched"], reverse=True)[:6]
    pw, ph, gap = 170, 255, 14
    x0 = (W - (6 * pw + 5 * gap)) // 2
    for i, f in enumerate(recent):
        try:
            p = Image.open(io.BytesIO(fetch_bytes(f["poster"].replace("-0-600-0-900-", "-0-460-0-690-")))).convert("RGB")
            p = p.resize((pw, ph), Image.LANCZOS)
        except Exception:  # noqa: BLE001
            p = Image.new("RGB", (pw, ph), (f.get("colors") or ["#1b232c"])[0])
        x = x0 + i * (pw + gap)
        sh = Image.new("RGB", (pw + 12, ph + 12), (8, 10, 13))
        img.paste(sh, (x - 2, 336), None)
        img.paste(p, (x, 330))
    def font(names, size):
        for n in names:
            try:
                return ImageFont.truetype(n, size)
            except OSError:
                pass
        return ImageFont.load_default(size=size)
    serif = font(["/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf", "DejaVuSerif.ttf"], 70)
    sans = font(["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "DejaVuSans.ttf"], 28)
    small = font(["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "DejaVuSans-Bold.ttf"], 18)
    d.text((x0, 70), "DVD Koleksiyonum", font=serif, fill="#eef2f6")
    rated = sum(1 for f in films if f.get("rating") is not None)
    d.text((x0, 172), f"brensvenka  ·  {len(films)} film  ·  {rated} puan", font=sans, fill="#8a96a4")
    d.text((x0, 238), "SON İZLEDİKLERİM", font=small, fill="#40bcf4")
    d.rectangle([x0, 268, x0 + 60, 271], fill="#40bcf4")
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    out = DATA_FILE.with_name("og.png")
    if out.exists() and out.read_bytes() == buf.getvalue():
        return False
    out.write_bytes(buf.getvalue())
    return True


def main():
    films = load_data()
    by_slug = {path_slug(f.get("letterboxdPath")): f for f in films}

    try:
        items = ET.fromstring(fetch(RSS_URL)).findall("./channel/item")
    except Exception as e:  # noqa: BLE001
        print(f"! RSS alınamadı: {e}", file=sys.stderr)
        items = []
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

    colored = add_colors(films)
    print(f"Renk hesaplanan afiş: {colored}")
    print("og.png güncellendi" if make_og(films) else "og.png aynı")
    updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    save_data(films, updated_at)
    print(f"Bitti: {added} yeni film, {changed} güncellenen film, toplam {len(films)}.")


if __name__ == "__main__":
    main()
