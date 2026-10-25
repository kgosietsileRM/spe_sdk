"""Flask app that turns media + a JSON template into a quick report."""

from __future__ import annotations

import json
from typing import Any

import analysis
import core
from flask import (
    Flask,
    Response,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

app = Flask(__name__)
app.secret_key = "spe-template-demo"
app.config["MAX_CONTENT_LENGTH"] = 512 * 1024 * 1024


def form_settings() -> dict[str, Any]:
    values = request.values
    return {
        "source": values.get("source", "hd"),
        "preset_name": values.get("preset", "highway"),
        "mode": values.get("mode", "local"),
        "frames": int(values.get("frames", 60)),
        "fps": float(values.get("fps", 5)),
        "url": values.get("url", "http://127.0.0.1:5000"),
        "model": values.get("model", "model-a"),
        "confidence": float(values.get("confidence", 0.4)),
    }


def run_from_request() -> dict[str, Any]:
    upload = request.files.get("media")
    return analysis.analyze_request(upload=upload, **form_settings())


def index_context() -> dict[str, Any]:
    presets = analysis.load_presets()
    return {
        "sources": core.load_links(),
        "presets": presets,
        "last_report": analysis.latest_report_path() is not None,
        "last_frame": analysis.latest_frame_path() is not None,
    }


@app.get("/")
def index() -> str:
    return render_template("index.html", **index_context())


@app.post("/analyze")
def analyze() -> Any:
    try:
        report = run_from_request()
    except Exception as error:
        flash(str(error), "error")
        return redirect(url_for("index"))
    return render_template(
        "result.html",
        report=report,
        settings=form_settings(),
        presets=analysis.load_presets(),
        report_json=analysis.latest_report_path() is not None,
        frame_json=analysis.latest_frame_path() is not None,
    )


@app.route("/api/analyze", methods=["GET", "POST"])
def api_analyze() -> Response:
    try:
        report = run_from_request()
    except Exception as error:
        return Response(
            json.dumps({"error": str(error)}),
            status=400,
            mimetype="application/json",
        )
    payload = render_template("report.json.j2", report=report)
    return Response(payload, mimetype="application/json")


@app.get("/last-frame")
def last_frame() -> Any:
    path = analysis.latest_frame_path()
    if path is None:
        return Response("No frame yet.", status=404)
    return send_file(path, mimetype="image/jpeg")


@app.get("/download")
def download() -> Any:
    path = analysis.latest_report_path()
    if path is None:
        return Response("No report yet.", status=404)
    return send_file(path, as_attachment=True, download_name="spe-report.json")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=False)
