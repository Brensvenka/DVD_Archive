#!/usr/bin/env python3
"""Arkadaş ortalamalarını (friends_ratings ile) ve yeni watchlist filmlerinin
Letterboxd ortalamasını günceller; kendi bilgisayarımda günde bir kez çalışır.
"""
import subprocess
import sys
import time
from pathlib import Path

import friends_ratings as fr
import update_films as u

ROOT = Path(__file__).parent
GAP = 5


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, check=False)


def main():
    git("pull", "-q", "--rebase", "--autostash")
    _, _, wl = fr.run()
    lb_done = 0
    for w in [w for w in wl if "lb" not in w][:30]:
        try:
            w["lb"], imdb_id = u.page_ratings(w["slug"])
            if imdb_id:
                w["imdbId"] = imdb_id
            lb_done += 1
        except Exception as e:  # noqa: BLE001
            print(f"! {w['slug']}: {e}", file=sys.stderr)
        time.sleep(GAP)
    print(f"Letterboxd ortalaması alınan: {lb_done}")
    if lb_done:
        fr.save_watchlist(wl)
    git("add", "watchlist-data.js", "films-data.js", "friends-cache.json")
    if git("diff", "--cached", "--quiet").returncode == 0:
        return
    git("commit", "-q", "-m", "Arkadaş puanları")
    git("pull", "-q", "--rebase")
    git("push", "-q")


if __name__ == "__main__":
    main()
