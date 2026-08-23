from mitmproxy import http
import json
import os
from datetime import datetime

CAPTURE_DIR = os.path.join(os.path.dirname(__file__), "..", "docs", "cn-traffic")

def save_capture(flow: http.HTTPFlow, direction: str):
    os.makedirs(CAPTURE_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    safe_host = flow.request.pretty_host.replace(".", "_")
    safe_path = flow.request.path.replace("/", "_").replace("?", "_")[:80]
    filename = f"{ts}_{direction}_{safe_host}{safe_path}.json"

    record = {
        "host": flow.request.pretty_host,
        "method": flow.request.method,
        "path": flow.request.path,
        "request_headers": dict(flow.request.headers),
        "request_body": flow.request.text or "",
    }

    if flow.response:
        record["status_code"] = flow.response.status_code
        record["response_headers"] = dict(flow.response.headers)
        record["response_body"] = flow.response.text or ""

    with open(os.path.join(CAPTURE_DIR, filename), "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)
    print(f"[CAPTURE] Saved: {filename}")

def request(flow: http.HTTPFlow):
    save_capture(flow, "req")

def response(flow: http.HTTPFlow):
    save_capture(flow, "res")
