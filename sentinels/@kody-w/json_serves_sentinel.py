#!/usr/bin/env python3
"""json_serves_sentinel — the JSON you serve still parses and still has its keys.

A merge left git conflict markers inside a served state file. The site was
"up" (200), the file was "there", and every consumer that fetched it broke.
This sentinel fetches each named document, parses it, and requires the keys
you name to be present (R3: require known-good, never enumerate known-bad).

One id for all documents; the detail names exactly which one failed how.
Read failures on our side are warn, never critical (blind is not broken).
"""

__manifest__ = {
    "schema": "rapp-sentinel/1.0",
    "name": "@kody-w/json_serves_sentinel",
    "version": "1.0.0",
    "description": "Named served JSON documents must fetch 200, parse, and carry the keys you require - catches conflict markers, truncation, and schema drift.",
    "category": "consistency",
    "checks": {
        "json_serves": {"domain": "output", "kind": "consistency"},
    },
    "config": {
        "documents": [
            {"url": "https://gist.githubusercontent.com/kody-w/f3e0fcb63b4c5a2351572b7c5266bce7/raw/sentinel-head.json",
             "require": ["schema", "utc"]}
        ],
        "timeout_s": 25,
    },
    "requires": [],
    "tags": ["json", "schema", "consistency", "outsider"],
    "author": "kody-w",
    "license": "MIT",
    "vantage": "outsider",
}


def run(config=None, ctx=None):
    import json
    cfg = dict(__manifest__["config"], **(config or {}))
    c = _ctx(ctx)
    docs = [d for d in (cfg.get("documents") or []) if isinstance(d, dict) and d.get("url")]
    if not docs:
        return [c["fail"]("json_serves", "no documents configured", critical=False)]
    broken, blind, good = [], [], 0
    for d in docs:
        name = d["url"].rsplit("/", 1)[-1] or d["url"]
        try:
            status, body = c["http_get"](d["url"], timeout=cfg.get("timeout_s", 25))
        except Exception as e:
            blind.append(f"{name} ({type(e).__name__})")
            continue
        if status != 200:
            broken.append(f"{name} HTTP {status}")
            continue
        try:
            doc = json.loads(body.decode("utf-8"))
        except Exception as e:
            broken.append(f"{name} does not parse ({type(e).__name__})")
            continue
        missing = [k for k in (d.get("require") or []) if not _has(doc, k)]
        if missing:
            broken.append(f"{name} missing {', '.join(missing)}")
            continue
        good += 1
    if broken:
        return [c["fail"]("json_serves", f"{len(broken)}/{len(docs)} broken: " + "; ".join(broken))]
    if blind:
        return [c["fail"]("json_serves", f"{good}/{len(docs)} good; cannot read " + ", ".join(blind),
                          critical=False)]
    return [c["ok"]("json_serves", f"{good}/{len(docs)} parse with required keys")]


def prove():
    docs = [{"url": "https://x.example/state.json", "require": ["schema", "utc"]}]
    served = lambda b: (lambda u, timeout=0: (200, b))
    def blind(u, timeout=0):
        raise OSError("dns")
    r = run({"documents": docs}, {"http_get": served(b'{"schema":"s","utc":"t"}')})[0]; assert r["ok"], r
    r = run({"documents": docs}, {"http_get": served(b'<<<<<<< HEAD\n{"schema":1}')})[0]; assert not r["ok"] and "does not parse" in r["detail"] and r["severity"] == "critical", r
    r = run({"documents": docs}, {"http_get": served(b'{"schema":"s"}')})[0]; assert not r["ok"] and "missing utc" in r["detail"], r
    r = run({"documents": docs}, {"http_get": lambda u, timeout=0: (404, b"")})[0]; assert not r["ok"] and "HTTP 404" in r["detail"], r
    r = run({"documents": docs}, {"http_get": blind})[0]; assert not r["ok"] and r["severity"] == "warn", r
    return True


def _has(doc, path):
    cur = doc
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return False
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
