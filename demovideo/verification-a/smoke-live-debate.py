"""End-to-end smoke test: full multi-agent DEBATE through real Gemini/Featherless.

Submits mode=debate. Expects multiple agent_done events (one per persona),
each with real text from real model invocations, ending in a consensus event.

Success criteria:
  1. >= 2 agent_done events
  2. Each agent_done has non-empty text + non-mock model_used
  3. consensus event present with text
  4. total stream time > 4s (live LLMs aren't free)
  5. No agent shows fallback=True (or, if shown, it's still a real provider)
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

API = "http://localhost:8000/api/v1"

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
        with urllib.request.urlopen(req, timeout=180) as resp:
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
    events: list[tuple[str, dict]] = []
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
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


def main() -> int:
    print("[smoke-debate] === ATRIO full multi-agent debate (live LLMs) ===")

    seed = http_json("POST", "/_test/seed-demo")
    print(f"  seed:    tenant={seed.get('tenant_id','???')[:8]}...")

    ml = http_json("POST", "/auth/magic-link", data={"email": "founder@acme.co"})
    consume = http_json("POST", "/auth/magic-link/consume", data={"token": ml.get("dev_token")})
    access = consume.get("access_token")
    print(f"  signed:  {access[:16]}...")

    sess = http_json("POST", "/sessions",
        data={"title": "Live debate smoke", "language_dominant": "en", "turn_taking_mode": "round_robin"},
        token=access,
    )
    sid = sess.get("id")
    print(f"  session: {sid[:8]}...")

    print()
    print("  POST /turns mode=debate -- this fires every agent in sequence")
    t0 = time.time()
    events = http_sse(f"/sessions/{sid}/turns",
        data={
            "text": "Should we hire 4 senior engineers in Q3 given 18-month runway and a tight product roadmap? Each agent: keep your answer to 3 sentences.",
            "mode": "debate",
            "language": "en",
        },
        token=access,
    )
    elapsed = time.time() - t0
    print(f"  stream finished in {elapsed:.1f}s ({len(events)} events)")
    print()

    err = next((e for e in events if e[0] == "_http_error"), None)
    if err:
        print(f"  [FAIL] HTTP error: {err[1]}")
        return 1

    agent_dones = [e[1] for e in events if e[0] == "agent_done"]
    consensus = next((e[1] for e in events if e[0] == "consensus"), None)
    complete = next((e[1] for e in events if e[0] == "stream_complete"), None)

    print(f"  agent_done events: {len(agent_dones)}")
    print(f"  consensus event:   {'present' if consensus else 'MISSING'}")
    print(f"  stream_complete:   {'present' if complete else 'MISSING'}")
    print()

    if len(agent_dones) < 2:
        print(f"  [FAIL] expected >= 2 agent_done events, got {len(agent_dones)}")
        return 1

    fails: list[str] = []
    print(f"  {'#':<3} {'agent':<14} {'model':<40} {'fb':<6} {'lat_ms':<8} {'len':<6}")
    print(f"  {'-'*3} {'-'*14} {'-'*40} {'-'*6} {'-'*8} {'-'*6}")
    for i, ad in enumerate(agent_dones, 1):
        model = ad.get("model_used", "")
        was_fb = ad.get("was_fallback", False)
        lat = ad.get("latency_ms", 0)
        text = ad.get("text", "")
        agent = ad.get("agent_id", "?")
        print(f"  {i:<3} {agent:<14} {model:<40} {str(was_fb):<6} {lat:<8} {len(text):<6}")
        if model.startswith("mock/"):
            fails.append(f"#{i} {agent}: model=mock/*")
        if lat < 500:
            fails.append(f"#{i} {agent}: latency {lat}ms < 500ms (looks mocked)")
        if any(m in text for m in MOCK_MARKERS):
            fails.append(f"#{i} {agent}: contains mock signature")
        if not text.strip():
            # empty text isn't a hard fail (Gemini variance) but flag it
            fails.append(f"#{i} {agent}: empty text (Gemini reasoning may have overrun)")

    if not consensus or not consensus.get("text"):
        fails.append("consensus event missing or empty")

    print()
    if fails:
        print("  [FAIL] " + str(len(fails)) + " issues:")
        for f in fails:
            print(f"    - {f}")
        return 1

    print(f"  [PASS] {len(agent_dones)} agents all returned real LLM responses")
    print(f"         total elapsed:  {elapsed:.1f}s")
    print(f"         dissent_rounds: {complete.get('dissent_rounds') if complete else '?'}")
    print()
    print("  --- excerpts from each agent ---")
    for i, ad in enumerate(agent_dones, 1):
        agent = ad.get("agent_id", "?").upper()
        text = ad.get("text", "")[:300].replace("\n", " ")
        model = ad.get("model_used", "")
        print(f"  [{i}] {agent:<12} ({model})")
        print(f"      {text}")
        print()

    if consensus and consensus.get("text"):
        c = consensus["text"][:500].replace("\n", "\n  ")
        print(f"  --- consensus ({consensus.get('kind', '?')}) ---")
        print(f"  {c}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
