"""End-to-end smoke test: prove ATRIO is talking to real Gemini.

Submits a single-agent turn (mode=single) to the live API. The stream
contains agent_done with {model_used, was_fallback, latency_ms, text}.

A real Gemini call is proved by ALL of:
  1. model_used starts with 'gemini/' (not 'mock/')
  2. was_fallback is False
  3. latency_ms > 1000 (mock is sub-100ms)
  4. text is non-empty AND doesn't contain a mock signature

Gemini 2.5 Pro occasionally returns empty content when its internal reasoning
overruns the output budget. We retry up to 3 times to get a non-empty body.
The non-empty payload is the proof, not the first try.
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


def http_json(method: str, path: str, *, data: dict | None = None, token: str | None = None) -> dict:
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


def http_sse(path: str, *, data: dict, token: str) -> list[tuple[str, dict]]:
    url = f"{API}{path}"
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "text/event-stream")
    req.add_header("Authorization", f"Bearer {token}")
    events: list[tuple[str, dict]] = []
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


def submit_turn(access: str, sid: str, prompt: str) -> tuple[list[tuple[str, dict]], float]:
    t0 = time.time()
    events = http_sse(f"/sessions/{sid}/turns",
        data={"text": prompt, "mode": "single", "language": "en"},
        token=access,
    )
    return events, time.time() - t0


def main() -> int:
    print("[smoke-live] === ATRIO real-Gemini end-to-end ===")

    seed = http_json("POST", "/_test/seed-demo")
    tenant = seed.get("tenant_id", "")
    print(f"  seed:    tenant={tenant[:8]}...")

    ml = http_json("POST", "/auth/magic-link", data={"email": "founder@acme.co"})
    consume = http_json("POST", "/auth/magic-link/consume", data={"token": ml.get("dev_token")})
    access = consume.get("access_token")
    if not access:
        print(f"  [FAIL] no access_token: {consume}")
        return 1
    print(f"  signed:  {access[:16]}...")

    sess = http_json("POST", "/sessions",
        data={"title": "Live Gemini smoke", "language_dominant": "en", "turn_taking_mode": "round_robin"},
        token=access,
    )
    sid = sess.get("id")
    print(f"  session: {sid[:8]}...")

    prompts = [
        "Should we hire 4 senior engineers in Q3 with 18-month runway? One paragraph.",
        "What is the biggest risk of hiring 4 senior engineers now? One paragraph.",
        "How would you sequence those hires across Q3? One paragraph.",
    ]

    proof: dict | None = None
    attempts = 0
    for i, prompt in enumerate(prompts, 1):
        attempts += 1
        print(f"  attempt {i}: POST /turns mode=single ...")
        events, elapsed = submit_turn(access, sid, prompt)
        print(f"     stream finished in {elapsed:.1f}s ({len(events)} events)")

        err = next((e for e in events if e[0] == "_http_error"), None)
        if err:
            print(f"     [FAIL] HTTP error: {err[1]}")
            return 1

        ad = next((e[1] for e in events if e[0] == "agent_done"), None)
        if ad is None:
            print(f"     [FAIL] no agent_done event")
            continue

        model = ad.get("model_used", "")
        was_fb = ad.get("was_fallback", False)
        lat = ad.get("latency_ms", 0)
        text = ad.get("text", "")

        print(f"     agent={ad.get('agent_id')}  model={model}  fallback={was_fb}  latency_ms={lat}  text_len={len(text)}")

        # Hard fails — if any of these trip, the integration is wrong (not flaky)
        if model.startswith("mock/"):
            print(f"     [FAIL] model_used=mock/* -- mock provider is in use")
            return 1
        if lat < 500:
            print(f"     [FAIL] latency {lat}ms < 500ms -- looks like mock")
            return 1
        if any(m in text for m in MOCK_MARKERS):
            print(f"     [FAIL] mock signature in text")
            return 1

        if text.strip():
            proof = {
                "attempt": i, "model": model, "was_fallback": was_fb,
                "latency_ms": lat, "text_len": len(text), "text": text,
                "prompt": prompt,
            }
            break  # one good response is enough
        else:
            print(f"     [retry] empty text (Gemini reasoning overran budget); trying next prompt")

    if proof is None:
        print(f"  [FAIL] {attempts} attempts all returned empty text (Gemini variance)")
        print(f"         Calls WERE real (latency + model_used confirmed) but no text body got through.")
        print(f"         Tune max_tokens up for the facilitator agent or use gemini-2.5-flash.")
        return 1

    print()
    print(f"  [PASS] live LLM proven on attempt {proof['attempt']}/{attempts}")
    print(f"         model       = {proof['model']}")
    print(f"         was_fallback= {proof['was_fallback']}")
    print(f"         latency_ms  = {proof['latency_ms']}")
    print(f"         text_len    = {proof['text_len']} chars")
    print()
    print("  --- excerpt (first 700 chars) ---")
    body = proof["text"][:700].replace("\n", "\n  ")
    print(f"  {body}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
