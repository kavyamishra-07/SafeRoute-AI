import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from risk_engine import RoadNetwork
from app import app

net = RoadNetwork(os.path.join(os.path.dirname(__file__), "..", "data", "road_network.json"))

def test_safest_not_riskier_than_fastest():
    r = net.find_routes("RS", "HO")
    routes = {x["id"]: x for x in r["routes"]}
    assert routes[r["recommended_id"]]["risk_score"] <= routes[r["fastest_id"]]["risk_score"]

def test_night_and_rain_raise_risk():
    p = ["RS", "RV", "OB"]
    assert net.evaluate(p, night=True)["risk_score"] > net.evaluate(p)["risk_score"]
    assert net.evaluate(p, rain=True)["risk_score"] > net.evaluate(p)["risk_score"]

def test_api():
    c = app.test_client()
    assert c.get("/api/routes?src=RS&dst=TP").status_code == 200
    assert c.get("/api/routes?src=RS&dst=RS").status_code == 400
