#!/usr/bin/env python3
"""template_sentinel — the smallest honest sentinel.

A hub sentinel is one file. It declares what it checks (`__manifest__`),
does the checking (`run`), and carries its own proof that it can tell a
broken world from a healthy one (`prove`). Copy this file to start yours:

    python3 sentinel_sdk.py new @you/my_thing_sentinel

The three rules every sentinel on the hub is held to (TRIFECTA §6d):
  R1  receipts are not evidence      - look at the output, not the log line
  R2  ran is not worked              - freshness of OUTPUT, not of a heartbeat
  R3  require known-good             - never enumerate known-bad
"""

__manifest__ = {
    "schema": "rapp-sentinel/1.0",
    "name": "@kody-w/template_sentinel",
    "version": "1.0.0",
    "description": "Describe, in one honest sentence, what world this sentinel refuses to call healthy.",
    "category": "example",
    "checks": {
        "my_check": {"domain": "example", "kind": "consistency"},
    },
    "config": {"greeting": "hello"},
    "requires": [],
    "tags": ["example"],
    "author": "kody-w",
    "license": "MIT",
    "vantage": "outsider",
}


# ── contract ────────────────────────────────────────────────────────────────

def run(config=None, ctx=None):
    """Return a list of result dicts: {id, ok, severity, detail}.

    `config` is __manifest__["config"] merged with the host's overrides.
    `ctx` is a dict of host helpers (ok, fail, http_get, hours_since, gh...);
    every helper has a stdlib fallback below so the file runs alone.
    """
    cfg = dict(__manifest__["config"], **(config or {}))
    c = _ctx(ctx)
    if not isinstance(cfg.get("greeting"), str) or not cfg["greeting"]:
        return [c["fail"]("my_check", "greeting must be a non-empty string")]
    return [c["ok"]("my_check", f"{cfg['greeting']} - the contract holds")]


def prove():
    """Break/control pair. Exit non-zero (return False) if the sentinel is blind."""
    control = run({"greeting": "hi"})
    broken = run({"greeting": ""})
    assert control[0]["ok"] and control[0]["id"] == "my_check", control
    assert not broken[0]["ok"] and broken[0]["id"] == "my_check", broken
    return True


# ── stdlib fallbacks (the host may override any of these via ctx) ───────────

def _ctx(ctx):
    base = {
        "ok": lambda cid, detail="": {"id": cid, "ok": True, "severity": "warn", "detail": detail},
        "fail": lambda cid, detail="", critical=True: {
            "id": cid, "ok": False, "severity": "critical" if critical else "warn", "detail": detail},
    }
    base.update(ctx or {})
    return base


if __name__ == "__main__":
    import json, sys
    if "--prove" in sys.argv:
        sys.exit(0 if prove() else 1)
    print(json.dumps(run(), indent=2))
