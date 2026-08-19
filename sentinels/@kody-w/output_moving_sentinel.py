#!/usr/bin/env python3
"""output_moving_sentinel — the OUTPUT moved, not the heartbeat (R2).

A platform froze for nineteen days with every surface metric green: first
paint fast, no JS errors, no failed requests. Underneath, nothing had been
written since July 13th. "Ran" is not "worked". This sentinel fetches a
served JSON document, reads a timestamp field OUT OF THE OUTPUT (never a run
receipt, never a heartbeat the producer could stamp without doing work), and
fails when it is older than the bar.

Three different sentences for three different claims:
  read failed        -> warn      blind, not broken (no repair budget on a read we could not make)
  stamp absent       -> critical  we READ the output and it cannot testify to its own freshness
  stamp stale        -> critical  the outage this exists for
"""

__manifest__ = {
    "schema": "rapp-sentinel/1.0",
    "name": "@kody-w/output_moving_sentinel",
    "version": "1.0.0",
    "description": "Fetches a served JSON document and fails when the timestamp inside the OUTPUT is older than max_age_h - freshness of work, not of heartbeats.",
    "category": "output-freshness",
    "checks": {
        "output_moving": {"domain": "output", "kind": "output-freshness"},
    },
    "config": {
        "url": "https://gist.githubusercontent.com/kody-w/f3e0fcb63b4c5a2351572b7c5266bce7/raw/sentinel-head.json",
        "field": "utc",
        "max_age_h": 2.0,
        "what": "sentinel head",
        "timeout_s": 25,
    },
    "requires": [],
    "tags": ["freshness", "R2", "json", "outsider"],
    "author": "kody-w",
    "license": "MIT",
    "vantage": "outsider",
}


def run(config=None, ctx=None):
    import json
    cfg = dict(__manifest__["config"], **(config or {}))
    c = _ctx(ctx)
    what = cfg.get("what") or cfg["url"]

    def newest_stamp():
        status, body = c["http_get"](cfg["url"], timeout=cfg.get("timeout_s", 25))
        if status != 200:
            raise RuntimeError(f"HTTP {status}")
        doc = json.loads(body.decode("utf-8"))
        return _dig(doc, cfg.get("field") or "utc")

    return [c["moving"]("output_moving", newest_stamp, float(cfg.get("max_age_h", 2.0)), what)]


def prove():
    import json
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    fresh = (now - timedelta(minutes=10)).isoformat()
    stale = (now - timedelta(hours=9)).isoformat()
    doc = lambda d: (lambda u, timeout=0: (200, json.dumps(d).encode()))
    def blind(u, timeout=0):
        raise OSError("dns")
    r = run({"field": "utc"}, {"http_get": doc({"utc": fresh})})[0];  assert r["ok"], r
    r = run({"field": "utc"}, {"http_get": doc({"utc": stale})})[0];  assert not r["ok"] and r["severity"] == "critical" and "stale" in r["detail"], r
    r = run({"field": "utc"}, {"http_get": doc({"other": 1})})[0];    assert not r["ok"] and r["severity"] == "critical" and "no timestamp" in r["detail"], r
    r = run({"field": "utc"}, {"http_get": blind})[0];               assert not r["ok"] and r["severity"] == "warn", r
    r = run({"field": "meta.built"}, {"http_get": doc({"meta": {"built": fresh}})})[0]; assert r["ok"], r
    return True


# ── stdlib fallbacks ─────────────────────────────────────────────────────────

def _dig(doc, path):
    cur = doc
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list) and part.isdigit():
            cur = cur[int(part)] if int(part) < len(cur) else None
        else:
            return None
    return cur


def _hours_since(iso):
    from datetime import datetime, timezone
    if not iso:
        return None
    try:
        d = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - d).total_seconds() / 3600
    except Exception:
        return None


def _moving(cid, timestamp_fn, max_age_h, what="output"):
    ok, fail = _ctx(None)["ok"], _ctx(None)["fail"]
    try:
        stamp = timestamp_fn()
    except Exception as e:
        return fail(cid, f"cannot read {what} timestamp ({type(e).__name__}: {str(e)[:60]})", critical=False)
    if stamp is None:
        return fail(cid, f"{what} carries no timestamp - cannot claim movement")
    age = _hours_since(stamp)
    if age is None:
        return fail(cid, f"{what} timestamp unreadable: {str(stamp)[:40]!r}")
    if age >= max_age_h:
        return fail(cid, f"{what} stale {age:.1f}h (bar {max_age_h}h)")
    return ok(cid, f"{what} {age:.1f}h old")


def _http_get(url, timeout=25):
    import urllib.request, urllib.error
    req = urllib.request.Request(url, headers={"User-Agent": "rapp-sentinel-hub"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""


def _ctx(ctx):
    base = {
        "ok": lambda cid, detail="": {"id": cid, "ok": True, "severity": "warn", "detail": detail},
        "fail": lambda cid, detail="", critical=True: {
            "id": cid, "ok": False, "severity": "critical" if critical else "warn", "detail": detail},
        "http_get": _http_get,
        "hours_since": _hours_since,
        "moving": _moving,
    }
    base.update(ctx or {})
    return base


if __name__ == "__main__":
    import json, sys
    if "--prove" in sys.argv:
        sys.exit(0 if prove() else 1)
    print(json.dumps(run(), indent=2))
