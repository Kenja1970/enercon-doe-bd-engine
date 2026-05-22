import os
import subprocess
from pathlib import Path

from flask import Flask, jsonify, request


app = Flask(__name__)

PROJECT_ROOT = Path(__file__).parent
STATUS_FILE = PROJECT_ROOT / "reports" / "daily_run_status.md"


@app.route("/", methods=["GET"])
def health_check():
    return jsonify({"status": "ok", "service": "sam-ae-opportunity-engine"})


@app.route("/run", methods=["POST"])
def run_engine():
    auth_header = request.headers.get("Authorization", "")
    expected_token = os.getenv("RUN_TOKEN", "")

    if not expected_token:
        return jsonify({"error": "RUN_TOKEN is not configured"}), 500

    if auth_header != f"Bearer {expected_token}":
        return jsonify({"error": "Unauthorized"}), 401

    command = [
        "uv",
        "run",
        "python",
        "src/run_daily_until_quota.py",
    ]

    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=900,
    )

    status_text = ""

    if STATUS_FILE.exists():
        status_text = STATUS_FILE.read_text(encoding="utf-8")

    return jsonify(
        {
            "returncode": result.returncode,
            "stdout": result.stdout[-5000:],
            "stderr": result.stderr[-5000:],
            "status_markdown": status_text,
            "success": result.returncode == 0,
        }
    ), 200 if result.returncode == 0 else 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)