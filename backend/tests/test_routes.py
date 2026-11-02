from __future__ import annotations

from app.scanner import build_fact_sheet


def test_route_extractor_covers_flask_fastapi_and_express_patterns():
    fact_sheet = build_fact_sheet({
        "flask_app.py": "from flask import Flask\napp = Flask(__name__)\n@app.route('/ping', methods=['GET', 'POST'])\ndef ping(): pass\n",
        "fastapi_app.py": "from fastapi import FastAPI\napp = FastAPI()\n@app.post('/analyze')\ndef analyze(): pass\n",
        "server.js": "const app = require('express')()\napp.get('/health', (req, res) => res.send('ok'))\n",
    }, [], {"full_name": "demo/routes", "commit_sha": "abc123", "url": "https://github.com/demo/routes"}, 3)

    routes = {(item["framework"], item["method"], item["path"]) for item in fact_sheet["routes"]}
    assert ("Flask/FastAPI", "GET,POST", "/ping") in routes
    assert ("Flask/FastAPI", "POST", "/analyze") in routes
    assert ("Express", "GET", "/health") in routes
    assert all(item["evidence_ids"] for item in fact_sheet["routes"])
