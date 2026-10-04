import os
from flask import Flask, jsonify, render_template, request

from ai_advisor import explain
from risk_engine import HAZARD_LABELS, RoadNetwork

BASE = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)
net = RoadNetwork(os.path.join(BASE, "data", "road_network.json"))


def _clean(route):
    return {k: v for k, v in route.items() if not k.startswith("_")}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/network")
def network():
    edges = [{"a": e["a"], "b": e["b"], "name": e["name"], "km": e["km"],
              "hazards": e["hazards"]} for e in net.edges.values()]
    return jsonify({"city": net.city, "nodes": net.nodes, "edges": edges,
                    "hazard_types": HAZARD_LABELS})


@app.route("/api/routes")
def routes():
    try:
        result = net.find_routes(
            request.args.get("src", ""), request.args.get("dst", ""),
            night=request.args.get("night") == "1", rain=request.args.get("rain") == "1",
            safety_weight=float(request.args.get("safety", 0.7)))
    except (ValueError, KeyError) as exc:
        return jsonify({"error": str(exc)}), 400
    night, rain = request.args.get("night") == "1", request.args.get("rain") == "1"
    result["advice"] = explain(result, night, rain)
    result["routes"] = [_clean(r) for r in result["routes"]]
    return jsonify(result)


@app.route("/api/report", methods=["POST"])
def report():
    d = request.get_json(force=True, silent=True) or {}
    try:
        net.add_hazard(d["a"], d["b"], d["type"], d.get("severity", 3), d.get("note", ""))
    except (KeyError, ValueError):
        return jsonify({"error": "Invalid report"}), 400
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
