"""ntfy(無料プッシュ通知アプリ)へ通知を送る。環境変数 NTFY_TOPIC が無ければ何もしない。"""
import os

import requests


def send(title: str, message: str, click: str | None = None) -> None:
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        print("[info] NTFY_TOPIC not set; skip notification")
        return
    body = {"topic": topic, "title": title, "message": message, "tags": ["chart_with_upwards_trend"]}
    if click:
        body["click"] = click
    try:
        requests.post("https://ntfy.sh/", json=body, timeout=20).raise_for_status()
    except Exception as e:  # noqa: BLE001
        print(f"[warn] ntfy failed: {e}")
