#!/usr/bin/env python3
"""İzleme listesindeki filmler için arkadaş ortalamasını yavaşça çeker.

Letterboxd bu sayfayı sık engellediği için kendi bilgisayarımda günde bir kez çalışır,
her seferinde az sayıda film dener ve art arda engellenirse durur.
"""
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import update_films as u

ROOT = Path(__file__).parent
PER_RUN = 60
GAP = 5


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, check=False)


def main():
    git("pull", "-q", "--rebase", "--autostash")
    wl = u.load_watchlist()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    stale = (datetime.now(timezone.utc) - timedelta(days=14)).strftime("%Y-%m-%d")
    todo = [w for w in wl if (w.get("checked") or "") <= stale]
    todo.sort(key=lambda w: w.get("checked") or "")
    done = fails = 0
    for w in todo[:PER_RUN]:
        try:
            w["friends"], w["friendsN"] = u.friends_rating(w["slug"])
            w["checked"] = today
            done += 1
            fails = 0
        except Exception as e:  # noqa: BLE001
            fails += 1
            print(f"! {w['slug']}: {e}", file=sys.stderr)
            if fails >= 5:
                print("Art arda engellendi, yarın devam.", file=sys.stderr)
                break
        time.sleep(GAP)
    print(f"Arkadaş puanı alınan: {done}")
    if not done:
        return
    body = json.dumps(wl, ensure_ascii=False, separators=(",", ":"))
    u.WATCHLIST_FILE.write_text(f"window.LETTERBOXD_WATCHLIST = {body};\n", encoding="utf-8")
    git("add", "watchlist-data.js")
    git("commit", "-q", "-m", "Arkadaş puanları")
    git("pull", "-q", "--rebase")
    git("push", "-q")


if __name__ == "__main__":
    main()
