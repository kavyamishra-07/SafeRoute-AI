"""AI decision layer: turns route risk analysis into plain-language advice.

Default: transparent rule-based explainer (works offline, no API key).
Optional: set ANTHROPIC_API_KEY to have Claude write the explanation.
"""
import json
import os
import urllib.request

TIPS = {
    "Accident-prone zone": "Reduce speed and keep extra distance at the marked blackspots.",
    "Waterlogging": "Avoid submerged stretches; water depth is hard to judge, so slow down or wait.",
    "Poor lighting": "Use headlights/reflectors and stay alert on dark stretches.",
    "Potholes": "Watch the road surface; two-wheelers should slow down on rough patches.",
    "Traffic congestion": "Expect delays; keep a safe gap in stop-and-go traffic.",
    "Reported hazard": "Community-reported hazard ahead; stay alert for obstacles.",
}


def _hazard_set(route):
    return {(h["road"], h["label"]): h for h in route["hazards"]}


def rule_based(result, night, rain):
    routes = {r["id"]: r for r in result["routes"]}
    rec, fast = routes[result["recommended_id"]], routes[result["fastest_id"]]
    ctx = []
    if night: ctx.append("night-time")
    if rain: ctx.append("rainy")
    ctx_txt = f" under {' and '.join(ctx)} conditions" if ctx else ""

    if rec["id"] == fast["id"]:
        summary = (f"The fastest route is also the safest option{ctx_txt}. "
                   f"Its risk score is {rec['risk_score']}/100 ({rec['risk_level']}) "
                   f"over {rec['km']} km and about {rec['minutes']} min.")
        avoided = []
    else:
        fast_h, rec_h = _hazard_set(fast), _hazard_set(rec)
        avoided_items = sorted((h for k, h in fast_h.items() if k not in rec_h),
                               key=lambda h: h["points"], reverse=True)
        avoided = [f"{h['label']} on {h['road']} (severity {h['severity']}/5)"
                   for h in avoided_items[:4]]
        summary = (f"SafeRoute recommends the route via {', '.join(rec['names'][1:-1]) or 'a direct road'}"
                   f"{ctx_txt}. Its risk score is {rec['risk_score']}/100 versus "
                   f"{fast['risk_score']}/100 on the fastest route "
                   f"({rec['risk_reduction_pct']}% lower risk), for about "
                   f"{max(rec['extra_minutes'], 0)} extra min and {max(rec['extra_km'], 0)} extra km.")
    remaining = [f"{h['label']} on {h['road']} (severity {h['severity']}/5)"
                 for h in rec["top_hazards"][:3]]
    tips, seen = [], set()
    for h in rec["hazards"]:
        if h["label"] not in seen and h["label"] in TIPS:
            seen.add(h["label"]); tips.append(TIPS[h["label"]])
        if len(tips) == 3: break
    return {"summary": summary, "avoided": avoided, "remaining": remaining,
            "tips": tips, "source": "rule-based"}


def _claude(result, base, night, rain):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    routes = {r["id"]: r for r in result["routes"]}
    compact = {}
    for name, rid in (("recommended", result["recommended_id"]), ("fastest", result["fastest_id"])):
        r = routes[rid]
        compact[name] = {"via": r["names"], "km": r["km"], "minutes": r["minutes"],
                         "risk_score": r["risk_score"],
                         "top_hazards": [{"type": h["label"], "road": h["road"],
                                          "severity": h["severity"], "note": h["note"]}
                                         for h in r["top_hazards"]]}
    prompt = (
        "You are the explanation layer of SafeRoute AI, a road-safety navigation app. "
        "Using ONLY this analysis, write 3-4 friendly sentences telling the traveller which route "
        "is recommended, why, what trade-off it costs, and the main remaining risk. "
        f"Context: night={night}, rain={rain}.\n" + json.dumps(compact))
    body = json.dumps({"model": os.environ.get("SAFEROUTE_MODEL", "claude-sonnet-5-5"),
                       "max_tokens": 300,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=body,
        headers={"content-type": "application/json", "x-api-key": key,
                 "anthropic-version": "2023-06-01"})
    with urllib.request.urlopen(req, timeout=12) as resp:
        data = json.load(resp)
    return "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text").strip()


def explain(result, night=False, rain=False):
    out = rule_based(result, night, rain)
    try:
        text = _claude(result, out, night, rain)
        if text:
            out["summary"], out["source"] = text, "claude"
    except Exception:
        pass  # fall back silently to rule-based explanation
    return out
