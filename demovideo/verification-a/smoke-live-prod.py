"""Live LLM debate smoke against the PRODUCTION Vultr deployment.

Identical to smoke-live-debate.py but targets the public URL. This is the
final proof for lablab.ai judges: a real 5-agent debate, on a real public
URL, with real Gemini calls -- no mocks, no localhost.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

API = "http://45.77.52.54:8000/api/v1"  # production Vultr deployment

MOCK_MARKERS = (
    "Mock signature:",
    "[FACILITATOR] Considering",
    "[CFO] Considering",
    "[CTO] Considering",
    "[CMO] Considering",
    "[COO] Considering",
    "[COUNSEL] Considering",
)


def http_json(method, path, *, data=None, token=None):
    url = f"{API}{path}"
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return {"_status": e.code, "_body": e.read().decode()[:500]}


def http_sse(path, *, data, token):
    url = f"{API}{path}"
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "text/event-stream")
    req.add_header("Authorization", f"Bearer {token}")
    events = []
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            current = None
            for raw in resp:
                line = raw.decode("utf-8", errors="replace").rstrip()
                if not line:
                    current = None
                    continue
                if line.startswith("event:"):
                    current = line[6:].strip()
                elif line.startswith("data:"):
                    payload = line[5:].strip()
                    if not payload or current is None:
                        continue
                    try:
                        events.append((current, json.loads(payload)))
                    except json.JSONDecodeError:
                        continue
                    if current == "stream_complete":
                        return events
    except urllib.error.HTTPError as e:
        events.append(("_http_error", {"code": e.code, "body": e.read().decode()[:500]}))
    return events


def main():
    print(f"[smoke-prod] === ATRIO live debate against PRODUCTION ({API}) ===")
    print()

    seed = http_json("POST", "/_test/seed-demo")
    print(f"  seed:    tenant={seed.get('tenant_id','?')[:8]}...")

    ml = http_json("POST", "/auth/magic-link", data={"email": "founder@acme.co"})
    consume = http_json("POST", "/auth/magic-link/consume", data={"token": ml.get("dev_token")})
    access = consume.get("access_token")
    print(f"  signed:  {access[:16]}...")

    sess = http_json("POST", "/sessions",
        data={"title": "Production smoke", "language_dominant": "en", "turn_taking_mode": "round_robin"},
        token=access,
    )
    sid = sess.get("id")
    print(f"  session: {sid[:8]}...")

    print()
    print("  POST /turns mode=debate -- firing 5 specialists against real Gemini")
    t0 = time.time()
    events = http_sse(f"/sessions/{sid}/turns",
        data={
            "text": "Should we hire 4 senior engineers in Q3 given 18-month runway? Keep each answer to 3 sentences.",
            "mode": "debate",
            "language": "en",
        },
        token=access,
    )
    elapsed = time.time() - t0
    print(f"  stream finished in {elapsed:.1f}s ({len(events)} events)")
    print()

    agent_dones = [e[1] for e in events if e[0] == "agent_done"]
    consensus = next((e[1] for e in events if e[0] == "consensus"), None)

    if not agent_dones:
        print("  [FAIL] no agent_done events")
        for e in events:
            print(f"    {e}")
        return 1

    print(f"  {'#':<3} {'agent':<14} {'model':<32} {'fb':<6} {'lat_ms':<8} {'len':<6}")
    print(f"  {'-'*3} {'-'*14} {'-'*32} {'-'*6} {'-'*8} {'-'*6}")
    failures = []
    for i, ad in enumerate(agent_dones, 1):
        model = ad.get("model_used", "")
        was_fb = ad.get("was_fallback", False)
        lat = ad.get("latency_ms", 0)
        text = ad.get("text", "")
        agent = ad.get("agent_id", "?")
        print(f"  {i:<3} {agent:<14} {model:<32} {str(was_fb):<6} {lat:<8} {len(text):<6}")
        if model.startswith("mock/"):
            failures.append(f"#{i}: model=mock")
        if lat < 500:
            failures.append(f"#{i}: lat<500 (mock)")
        if any(m in text for m in MOCK_MARKERS):
            failures.append(f"#{i}: mock signature in text")

    print()
    if failures:
        for f in failures:
            print(f"  [FAIL] {f}")
        return 1

    print(f"  [PASS] {len(agent_dones)} live agents from {API}")
    print(f"         total elapsed: {elapsed:.1f}s")
    print(f"         consensus:     {'present (' + consensus.get('kind','?') + ')' if consensus else 'MISSING'}")
    print()
    print("  --- one agent excerpt (Counsel) ---")
    counsel = next((ad for ad in agent_dones if ad.get("agent_id") == "counsel"), agent_dones[-1])
    txt = counsel.get("text", "")[:400].replace("\n", "\n  ")
    print(f"  agent: {counsel.get('agent_id', '?')}  model: {counsel.get('model_used', '?')}")
    print(f"  {txt}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
