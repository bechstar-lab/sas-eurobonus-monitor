"""
Lokal web-server for dashboardet med refresh-knapp.

  .venv/bin/python serve.py        # http://localhost:5151
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime

from flask import Flask, jsonify, send_file

import config
from monitor import run_check
from dashboard import render

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
log = logging.getLogger("serve")

app = Flask(__name__)

# Delt state for /refresh + /status
_state = {
    "running": False,
    "started": None,
    "finished": None,
    "error": None,
    "last_total": None,
    "last_pairs": None,
}
_lock = threading.Lock()


def _do_check():
    with _lock:
        _state["running"] = True
        _state["started"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        _state["error"] = None
    try:
        result = run_check()
        render(result)
        with _lock:
            _state["finished"] = result["finished"]
            _state["last_total"] = result["total"]
            _state["last_pairs"] = sum(len(v) for v in result["trip_pairs"].values())
        log.info("refresh ferdig: total=%d pairs=%d",
                 _state["last_total"], _state["last_pairs"])
    except Exception as e:
        log.exception("refresh feilet")
        with _lock:
            _state["error"] = str(e)
    finally:
        with _lock:
            _state["running"] = False


@app.route("/")
def index():
    if not config.DASHBOARD_PATH.exists():
        render()
    return send_file(str(config.DASHBOARD_PATH))


@app.route("/hotels")
def hotels():
    from hotels_page import render as render_hotels
    path = render_hotels()
    return send_file(path)


@app.route("/refresh", methods=["POST"])
def refresh():
    with _lock:
        if _state["running"]:
            return jsonify({"running": True, "started": _state["started"]}), 202
    threading.Thread(target=_do_check, daemon=True).start()
    return jsonify({"started": True}), 202


@app.route("/status")
def status():
    with _lock:
        return jsonify(dict(_state))


if __name__ == "__main__":
    print(" Dashboard:  http://localhost:5151/")
    print(" Refresh:    POST http://localhost:5151/refresh")
    print(" Status:     http://localhost:5151/status")
    app.run(host="127.0.0.1", port=5151, debug=False, use_reloader=False)
