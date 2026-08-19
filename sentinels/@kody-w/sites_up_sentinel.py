#!/usr/bin/env python3
"""sites_up_sentinel — every URL you name answers 200, from the outside.

Reachability, nothing more. It does not claim the site is fresh or correct
(that is output_moving_sentinel / json_serves_sentinel); it claims a stranger
with no credentials can fetch the front door. One id, all URLs — a partial
outage is reported as the partial outage it is, never as "sites: ok" because
the first URL happened to answer.

Blind is not broken: a network error on OUR side (no DNS, no route) is a
warn ("cannot read"), never a critical about the site.
"""

__manifest__ = {
    "schema": "rapp-sentinel/1.0",
    "name": "@kody-w/sites_up_sentinel",
    "version": "1.0.0",
    "description": "A named list of URLs must all answer HTTP 200 to an unauthenticated fetch; partial outages are named, not averaged away.",
    "category": "reachability",
    "checks": {
        "sites_up": {"domain": "sites", "kind": "reachability"},
    },
    "config": {
        "urls": ["https://kody-w.github.io/rapp-sentinel/"],
        "critical": True,
        "timeout_s": 25,
    },
    "requires": [],
    "tags": ["http", "pages", "reachability", "outsider"],
    "author": "kody-w",
    "license": "MIT",
    "vantage": "outsider",
}


def run(config=None, ctx=None):
    cfg = dict(__manifest__["config"], **(config or {}))
    c = _ctx(ctx)
    urls = [u for u in (cfg.get("urls") or []) if isinstance(u, str) and u]
    if not urls:
        return [c["fail"]("sites_up", "no urls configured", critical=False)]
    down, blind, up = [], [], 0
    for u in urls:
        try:
            status, _ = c["http_get"](u, timeout=cfg.get("timeout_s", 25))
        except Exception as e:                       # our read failed, not their site
            blind.append(f"{_short(u)} ({type(e).__name__})")
            continue
        if status == 200:
            up += 1
        else:
            down.append(f"{_short(u)} HTTP {status}")
    if down:
        return [c["fail"]("sites_up", f"{len(down)}/{len(urls)} down: " + ", ".join(down),
                          critical=bool(cfg.get("critical", True)))]
    if blind:
        return [c["fail"]("sites_up", f"{up}/{len(urls)} up; cannot read " + ", ".join(blind),
                          critical=False)]
    return [c["ok"]("sites_up", f"{up}/{len(urls)} up")]


def prove():
    urls = ["https://a.example/", "https://b.example/"]
    ok_all = lambda u, timeout=0: (200, b"")
    one_down = lambda u, timeout=0: ((503, b"") if "b." in u else (200, b""))
    def blind(u, timeout=0):
        raise OSError("no route")
    r = run({"urls": urls}, {"http_get": ok_all})[0]
    assert r["ok"], r
    r = run({"urls": urls}, {"http_get": one_down})[0]
    assert not r["ok"] and r["severity"] == "critical" and "b.example HTTP 503" in r["detail"], r
    r = run({"urls": urls}, {"http_get": blind})[0]
    assert not r["ok"] and r["severity"] == "warn", r          # blind is not broken
    r = run({"urls": []})[0]
    assert not r["ok"] and r["severity"] == "warn", r
    return True


# ── stdlib fallbacks ─────────────────────────────────────────────────────────

def _short(u):
    return u.split("://", 1)[-1].split("/", 1)[0]


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
    }
    base.update(ctx or {})
    return base


if __name__ == "__main__":
    import json, sys
    if "--prove" in sys.argv:
        sys.exit(0 if prove() else 1)
    print(json.dumps(run(), indent=2))
