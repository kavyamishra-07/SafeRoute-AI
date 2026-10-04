# SafeRoute AI

AI-powered navigation that ranks routes by **road safety**, not just distance and time.

## Features
- Road-risk dataset: accident zones, potholes, waterlogging, congestion, poor lighting, reported hazards (severity 1-5)
- Context-aware risk scoring (night and rain change hazard weights)
- Multi-objective route ranking (safety vs. extra travel time, adjustable slider)
- AI advisor that explains the recommendation, hazards avoided, remaining risks and safety tips
- Crowdsourced hazard reporting that updates scores instantly
- Interactive map UI (SVG), no external map keys needed

## Run
```bash
pip install -r requirements.txt
python app.py          # open http://localhost:5000
python -m pytest tests # optional
```

## Optional: Claude-written explanations
```bash
export ANTHROPIC_API_KEY=your_key   # Windows: set ANTHROPIC_API_KEY=your_key
python app.py
```
Without a key the app uses a built-in rule-based explainer (works offline).

## How scoring works
`segment points = base_weight(type) x severity/5 x context multiplier`
`route score = 100 x (1 - exp(-total points / 35))` -> Low <25, Moderate <50, High <75, Very High
`cost = w x risk_score + (1-w) x 2 x extra_minutes` -> lowest cost is recommended.

## Structure
- `app.py` Flask server and API (`/api/network`, `/api/routes`, `/api/report`)
- `risk_engine.py` risk scoring and route ranking
- `ai_advisor.py` AI decision layer (rule-based, optional Claude)
- `data/road_network.json` demo road-risk data (edit to use your own city)
- `templates/index.html` web interface

## Future work
Live traffic, weather, accident APIs, real map tiles/OSM routing, verified crowdsourcing, authority dashboard.
