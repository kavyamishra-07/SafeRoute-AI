"""SafeRoute AI - risk scoring and route evaluation engine.

Pipeline: road-risk data -> severity/context weighting -> per-route safety
risk score (0-100) -> multi-objective ranking (safety vs. time).
"""
import json
import math
import os

# Base weight (risk points at severity 5) per hazard type
HAZARD_WEIGHTS = {
    "accident_zone": 10.0,
    "waterlogging": 6.0,
    "poor_lighting": 5.0,
    "reported_hazard": 5.0,
    "pothole": 4.0,
    "congestion": 3.0,
}

HAZARD_LABELS = {
    "accident_zone": "Accident-prone zone",
    "waterlogging": "Waterlogging",
    "poor_lighting": "Poor lighting",
    "reported_hazard": "Reported hazard",
    "pothole": "Potholes",
    "congestion": "Traffic congestion",
}

# Contextual multipliers: (night, rain)
NIGHT_MULT = {"poor_lighting": 2.0, "accident_zone": 1.3, "reported_hazard": 1.2}
DAY_MULT = {"poor_lighting": 0.2}
RAIN_MULT = {"waterlogging": 1.6, "pothole": 1.4, "accident_zone": 1.25, "congestion": 1.1}

# Hazards that spread along the whole segment (scale with length)
LINEAR_HAZARDS = {"poor_lighting", "congestion"}

AVG_SPEED_KMPH = 30.0
SCORE_SCALE = 35.0  # larger -> score saturates more slowly


def risk_level(score):
    if score < 25:
        return "Low"
    if score < 50:
        return "Moderate"
    if score < 75:
        return "High"
    return "Very High"


def _key(a, b):
    return tuple(sorted((a, b)))


class RoadNetwork:
    def __init__(self, path):
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        self.city = raw.get("city", "City")
        self.nodes = raw["nodes"]
        self.edges = {}
        self.adj = {n: [] for n in self.nodes}
        for e in raw["edges"]:
            k = _key(e["a"], e["b"])
            self.edges[k] = {"a": e["a"], "b": e["b"], "km": e["km"],
                             "name": e["name"], "hazards": list(e["hazards"])}
            self.adj[e["a"]].append(e["b"])
            self.adj[e["b"]].append(e["a"])

    # ---------- data ----------
    def edge(self, a, b):
        return self.edges[_key(a, b)]

    def add_hazard(self, a, b, htype, severity, note="Crowdsourced report"):
        if htype not in HAZARD_WEIGHTS:
            raise ValueError("Unknown hazard type")
        severity = max(1, min(5, int(severity)))
        self.edge(a, b)["hazards"].append(
            {"type": htype, "severity": severity, "note": note or "Crowdsourced report",
             "crowdsourced": True})

    # ---------- scoring ----------
    def segment_metrics(self, a, b, night=False, rain=False):
        e = self.edge(a, b)
        points, hazards, congestion = 0.0, [], 0
        for h in e["hazards"]:
            t, sev = h["type"], h["severity"]
            p = HAZARD_WEIGHTS[t] * sev / 5.0
            if night:
                p *= NIGHT_MULT.get(t, 1.0)
            else:
                p *= DAY_MULT.get(t, 1.0)
            if rain:
                p *= RAIN_MULT.get(t, 1.0)
            if t in LINEAR_HAZARDS:
                p *= min(e["km"] / 3.0, 1.5)
            if t == "congestion":
                congestion = max(congestion, sev)
            points += p
            hazards.append({"type": t, "label": HAZARD_LABELS[t], "severity": sev,
                            "points": round(p, 2), "road": e["name"],
                            "note": h.get("note", ""),
                            "crowdsourced": bool(h.get("crowdsourced"))})
        minutes = e["km"] / AVG_SPEED_KMPH * 60.0 * (1 + 0.15 * congestion)
        if rain:
            minutes *= 1.10
        return {"km": e["km"], "minutes": minutes, "points": points,
                "hazards": hazards, "road": e["name"]}

    def evaluate(self, path, night=False, rain=False):
        km = minutes = points = 0.0
        hazards, segments = [], []
        for a, b in zip(path, path[1:]):
            m = self.segment_metrics(a, b, night, rain)
            km += m["km"]; minutes += m["minutes"]; points += m["points"]
            hazards.extend(m["hazards"])
            segments.append({"from": a, "to": b, "road": m["road"],
                             "points": round(m["points"], 2)})
        score = round(100 * (1 - math.exp(-points / SCORE_SCALE)), 1)
        hazards.sort(key=lambda h: h["points"], reverse=True)
        counts = {}
        for h in hazards:
            counts[h["label"]] = counts.get(h["label"], 0) + 1
        return {
            "path": path,
            "names": [self.nodes[n]["name"] for n in path],
            "km": round(km, 1),
            "minutes": round(minutes),
            "_minutes_exact": minutes,
            "risk_points": round(points, 1),
            "risk_score": score,
            "risk_level": risk_level(score),
            "hazard_counts": counts,
            "hazards": hazards,
            "top_hazards": hazards[:4],
            "segments": segments,
        }

    # ---------- routing ----------
    def all_paths(self, src, dst, max_nodes=7):
        out = []
        def dfs(cur, path):
            if len(path) > max_nodes:
                return
            if cur == dst:
                out.append(list(path)); return
            for nxt in self.adj[cur]:
                if nxt not in path:
                    path.append(nxt); dfs(nxt, path); path.pop()
        dfs(src, [src])
        return out

    def find_routes(self, src, dst, night=False, rain=False, safety_weight=0.7, limit=4):
        if src == dst or src not in self.nodes or dst not in self.nodes:
            raise ValueError("Choose two different valid locations")
        routes = [self.evaluate(p, night, rain) for p in self.all_paths(src, dst)]
        if not routes:
            raise ValueError("No route found")
        min_km = min(r["km"] for r in routes)
        routes = [r for r in routes if r["km"] <= 1.8 * min_km]
        fastest = min(routes, key=lambda r: r["_minutes_exact"])
        min_time = fastest["_minutes_exact"]
        w = max(0.0, min(1.0, safety_weight))
        for r in routes:
            extra = r["_minutes_exact"] - min_time
            r["cost"] = round(w * r["risk_score"] + (1 - w) * extra * 2, 2)
        recommended = min(routes, key=lambda r: r["cost"])
        safest = min(routes, key=lambda r: (r["risk_score"], r["_minutes_exact"]))
        routes.sort(key=lambda r: r["cost"])
        routes = routes[:limit]
        for r in (fastest, recommended, safest):
            if r not in routes:
                routes.append(r)
        for i, r in enumerate(routes):
            r["id"] = i
            r["tags"] = []
        for r, tag in ((fastest, "Fastest"), (safest, "Safest"), (recommended, "Recommended")):
            r["tags"].append(tag)
        for r in routes:
            r["extra_minutes"] = round(r["_minutes_exact"] - min_time)
            r["extra_km"] = round(r["km"] - fastest["km"], 1)
            r["risk_reduction_pct"] = (
                round(100 * (fastest["risk_score"] - r["risk_score"]) / fastest["risk_score"])
                if fastest["risk_score"] else 0)
        return {"routes": routes, "recommended_id": recommended["id"],
                "fastest_id": fastest["id"], "safest_id": safest["id"]}
