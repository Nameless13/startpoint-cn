from mitmproxy import http, dns
import ipaddress
import json
import os
from datetime import datetime

CN_API_HOST = "localhost"
CN_API_PORT = 8001
CN_API_SCHEME = "http"
DNS_TTL = 600

CAPTURE_DIR = os.path.join(os.path.dirname(__file__), "..", "docs", "cn-traffic")

cn_hosts = {
    "shijtswygamegf.leiting.com": "/api/index.php",
    "update.leiting.com": "",
}

def save_capture(flow: http.HTTPFlow):
    os.makedirs(CAPTURE_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    safe_path = flow.request.path.replace("/", "_").replace("?", "_")[:80]
    safe_host = flow.request.pretty_host.replace(".", "_")
    filename = f"{ts}_{safe_host}{safe_path}.json"
    record = {
        "host": flow.request.pretty_host,
        "method": flow.request.method,
        "path": flow.request.path,
        "request_headers": dict(flow.request.headers),
        "request_body": flow.request.text or "",
        "status_code": flow.response.status_code if flow.response else 0,
        "response_headers": dict(flow.response.headers) if flow.response else {},
        "response_body": flow.response.text if flow.response and flow.response.text else "",
    }
    with open(os.path.join(CAPTURE_DIR, filename), "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)
    print(f"[CAPTURE] Saved: {filename}")

def request(flow: http.HTTPFlow):
    save_capture(flow)
    host = flow.request.pretty_host
    if host in cn_hosts:
        prefix = cn_hosts[host]
        flow.request.host = CN_API_HOST
        flow.request.port = CN_API_PORT
        flow.request.scheme = CN_API_SCHEME
        if prefix:
            flow.request.path = f"{prefix}{flow.request.path}"

def dns_request(flow: dns.DNSFlow):
    if not flow.request.query or flow.request.questions is None:
        return
    for q in flow.request.questions:
        if q.name in cn_hosts:
            print(f"[DNS] Redirecting {q.name} -> {CN_API_HOST}:{CN_API_PORT}")
            domain_redirect = f"{q.name}.mitm.it"
            a_rec = dns.ResourceRecord.A(domain_redirect, ipaddress.IPv4Address("127.0.0.1"), ttl=DNS_TTL)
            flow.response.answers.append(a_rec)
