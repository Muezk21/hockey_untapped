import json
from collections import Counter
from urllib.request import urlopen, Request

def get(url):
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept": "application/json",
    })
    with urlopen(req) as r:
        return json.load(r)

sched = get("https://api-web.nhle.com/v1/club-schedule-season/ANA/20262027")
done = [g for g in sched["games"] if g.get("gameState") in ("OFF", "FINAL")]
game = done[-1]
gid = game["id"]
print("Game:", gid, game.get("gameDate"))

pbp = get(f"https://api-web.nhle.com/v1/gamecenter/{gid}/play-by-play")
plays = pbp["plays"]

print("\nEvent types:")
for k, v in Counter(p["typeDescKey"] for p in plays).most_common():
    print(f"  {k}: {v}")

print("\nSituation codes (1551 = 5v5):")
for k, v in Counter(p.get("situationCode") for p in plays).most_common(6):
    print(f"  {k}: {v}")

print("\nSample takeaway/giveaway/shot:")
for t in ("takeaway", "giveaway", "shot-on-goal"):
    s = next((p for p in plays if p["typeDescKey"] == t), None)
    print(t, "->", json.dumps(s, indent=1) if s else "none")