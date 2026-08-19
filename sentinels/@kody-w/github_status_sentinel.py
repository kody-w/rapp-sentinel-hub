#!/usr/bin/env python3
"""github_status_sentinel — is it us, or is it GitHub?

2026-08-06 18:10Z a sentinel went critical with two TRUE positives: state had
not merged in 3h and a validation gate was failing 5/10. Both real. Neither
ours - Actions and Pages were in major outage. A repair arm that spends money
was about to be aimed at a problem that did not exist here.

This check exists to appear in the SAME report as the reds it explains. It
is warn-level on purpose: it must never wake anyone, and it must never be
missing when the other checks go red. Fail closed: "status page unreadable"
is a warn, never "all operational".
"""

__manifest__ = {
    "schema": "rapp-sentinel/1.0",
    "name": "@kody-w/github_status_sentinel",
    "version": "1.0.0",
    "description": "Reads githubstatus.com and reports degraded components (Actions, Pages, API...) at warn so GitHub's outage is never mistaken for yours.",
    "category": "reachability",
    "checks": {
        "github_status": {"domain": "github", "kind": "reachability"},
    },
    "config": {
        "components": ["Actions", "Pages", "API Requests", "Webhooks", "Git Operations"],
        "url": "https://www.githubstatus.com/api/v2/components.json",
        "timeout_s": 25,
    },
    "requires": [],
    "tags": ["github", "outage", "attribution", "outsider"],
    "author": "kody-w",
    "license": "MIT",
    "vantage": "outsider",
}


def run(config=None, ctx=None):
    import json
    cfg = dict(__manifest__["config"], **(config or {}))
    c = _ctx(ctx)
    watched = set(cfg.get("components") or [])
    try:
        status, body = c["http_get"](cfg["url"], timeout=cfg.get("timeout_s", 25))
        if status != 200:
            raise RuntimeError(f"HTTP {status}")
        comps = json.loads(body.decode("utf-8")).get("components", [])
    except Exception as e:
        return [c["fail"]("github_status",
                          f"cannot read GitHub status ({type(e).__name__}: {str(e)[:60]})",
                          critical=False)]
    seen = {x.get("name"): x.get("status") for x in comps if x.get("name") in watched}
    if not seen:
        return [c["fail"]("github_status", "status page listed none of the watched components",
                          critical=False)]
    bad = {n: s for n, s in seen.items() if s != "operational"}
    if bad:
        return [c["fail"]("github_status", "GitHub degraded: "
                          + ", ".join(f"{n} {s}" for n, s in sorted(bad.items()))
                          + " - external, not ours", critical=False)]
    return [c["ok"]("github_status", f"{len(seen)} components operational")]


def prove():
    import json
    def page(rows):
        return lambda u, timeout=0: (200, json.dumps({"components": rows}).encode())
    good = page([{"name": "Actions", "status": "operational"}, {"name": "Pages", "status": "operational"}])
    degraded = page([{"name": "Actions", "status": "major_outage"}, {"name": "Pages", "status": "operational"}])
    empty = page([{"name": "Copilot", "status": "operational"}])
    def blind(u, timeout=0):
        raise OSError("dns")
    r = run(None, {"http_get": good})[0];      assert r["ok"], r
    r = run(None, {"http_get": degraded})[0];  assert not r["ok"] and r["severity"] == "warn" and "Actions major_outage" in r["detail"], r
    r = run(None, {"http_get": empty})[0];     assert not r["ok"] and r["severity"] == "warn", r
    r = run(None, {"http_get": blind})[0];     assert not r["ok"] and r["severity"] == "warn", r
    return True


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
