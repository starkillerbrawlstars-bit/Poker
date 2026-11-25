#!/usr/bin/env python3
"""Fairness-Auswertung des Hand-Protokolls (Firestore-Sammlung 'hands').

Aufruf:  python3 tools/auswertung.py [spieler-id]   (Standard: silence)

Pro Spieler:
  - Hände, durchschnittliche Starthand-Stärke (Chen-Formel), Anteil Premium-Hände
  - Stärke, wenn der Spieler SELBST gemischt/ausgeteilt hat ('Nächste Runde' geklickt)
  - Showdown-Gewinnquote, Gewinn in €
  - Auffälligkeiten: doppelte/fehlende Karten (ok=false), Handkarten nach dem Austeilen verändert
"""
import json, sys, math, urllib.request
from collections import defaultdict

KEY = "AIzaSyA92pxNNy2tuRjz5ApFTK2hupYIqxRB3WA"
BASE = "https://firestore.googleapis.com/v1/projects/poker-34e6f/databases/(default)/documents"
FOCUS = (sys.argv[1] if len(sys.argv) > 1 else "silence").lower()


def val(x):
    k, v = next(iter(x.items()))
    if k == "mapValue":
        return {a: val(b) for a, b in v.get("fields", {}).items()}
    if k == "arrayValue":
        return [val(b) for b in v.get("values", [])]
    if k == "integerValue":
        return int(v)
    if k == "doubleValue":
        return float(v)
    return v


def load():
    out, tok = [], ""
    while True:
        u = f"{BASE}/hands?pageSize=300&key={KEY}" + (f"&pageToken={tok}" if tok else "")
        d = json.load(urllib.request.urlopen(u))
        out += [{a: val(b) for a, b in x["fields"].items()} | {"id": x["name"].split("/")[-1]} for x in d.get("documents", [])]
        tok = d.get("nextPageToken")
        if not tok:
            return out


RN = {11: "B", 12: "D", 13: "K", 14: "A"}
card = lambda c: f"{RN.get(c % 13 + 2, c % 13 + 2)}{'♠♥♦♣'[c // 13]}"


def chen(h):
    """Chen-Formel: grobe Stärke einer Starthand (-1 … 20)."""
    r = sorted((c % 13 + 2 for c in h), reverse=True)
    pts = {14: 10, 13: 8, 12: 7, 11: 6}.get(r[0], r[0] / 2)
    if r[0] == r[1]:
        return max(5, pts * 2)
    if h[0] // 13 == h[1] // 13:
        pts += 2
    gap = r[0] - r[1] - 1
    pts -= [0, 1, 2, 4][gap] if gap < 4 else 5
    if gap <= 1 and r[0] < 12:
        pts += 1
    return math.ceil(pts)


premium = lambda h: chen(h) >= 10  # z. B. TT+, AK, AQs, KQs


def main():
    H = [h for h in load() if h.get("st")]
    if not H:
        print("Noch keine protokollierten Hände.")
        return
    S = defaultdict(lambda: defaultdict(float))
    alerts = []
    for h in H:
        end = {p["u"]: p for p in h.get("p", [])}
        if h.get("p") and not h.get("ok", True):
            alerts.append(f"{h['id']}: Karten doppelt/fehlend (Deck manipuliert?)")
        for u, cs in h["st"].items():
            s = S[u]
            c = chen(cs)
            s["n"] += 1; s["chen"] += c; s["prem"] += premium(cs)
            if h.get("by") == u:
                s["sn"] += 1; s["schen"] += c; s["sprem"] += premium(cs)
            if u in end:
                p = end[u]
                if sorted(p["h"]) != sorted(cs):
                    alerts.append(f"{h['id']}: {u} hatte {' '.join(map(card, cs))}, am Ende {' '.join(map(card, p['h']))}")
                s["net"] += p["w"] - p["tot"]
                if h.get("rv") and not p["f"]:
                    s["sd"] += 1; s["sdw"] += p["w"] > 0
        if h.get("by"):
            S[h["by"]]["dealt"] += 1

    n_all = sum(s["n"] for s in S.values())
    avg_all = sum(s["chen"] for s in S.values()) / n_all
    print(f"{len(H)} Hände protokolliert · Ø Starthand aller Spieler (Chen): {avg_all:.2f}\n")
    print(f"{'Spieler':14} {'Hände':>5} {'ØChen':>6} {'Premium':>8} {'selbst gemischt':>16} {'ØChen dabei':>11} {'Showdown-Siege':>15} {'Netto':>9}")
    for u, s in sorted(S.items(), key=lambda kv: -kv[1]["n"]):
        if not s["n"]:
            continue
        sd = f"{int(s['sdw'])}/{int(s['sd'])}" if s["sd"] else "-"
        sch = f"{s['schen'] / s['sn']:.2f}" if s["sn"] else "-"
        mark = "  ◀" if u == FOCUS else ""
        print(f"{u:14} {int(s['n']):5} {s['chen'] / s['n']:6.2f} {s['prem'] / s['n']:7.0%} {int(s['dealt']):16} {sch:>11} {sd:>15} {s['net'] / 100:+8.2f}€{mark}")

    f = S.get(FOCUS)
    if f and f["n"]:
        # Abweichung des Ø-Chen-Werts in Standardfehlern (Chen-Streuung zufälliger Hände ≈ 3,1)
        z = (f["chen"] / f["n"] - avg_all) / (3.1 / math.sqrt(f["n"]))
        print(f"\n{FOCUS}: Starthände {z:+.1f} Standardabweichungen vom Schnitt "
              f"({'auffällig' if abs(z) >= 3 else 'unauffällig'}; ab ±3 wird es verdächtig, aussagekräftig erst ab ~200 Händen)")
    print("\nAuffälligkeiten:" if alerts else "\nKeine Manipulationsspuren gefunden.")
    for a in alerts:
        print("  " + a)


if __name__ == "__main__":
    main()
