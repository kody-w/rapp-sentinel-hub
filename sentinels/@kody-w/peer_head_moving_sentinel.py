#!/usr/bin/env python3
"""peer_head_moving_sentinel — a neighbor's published head is still advancing.

Neighborhood membership is whoever joins: a sentinel publishes its head
(rapp-sentinel-head/1.0), you fetch it, and either side can tell if the other
stopped moving. Nobody grants access; nobody can revoke it. You can catch a
peer that STALLED; you cannot catch a peer that LIED - build only on the
first (JOINING.md).

This sentinel remembers the last head it saw for each peer (a small state
file the host hands it, or a local one) and fails when:
  * the head document is older than max_age_h            (the peer stopped publishing)
  * a watcher's seq did not advance since the last look   (published, but no work - R2)
  * a watcher's seq went BACKWARDS                        (rewritten history)
"""

__manifest__ = {
    "schema": "rapp-sentinel/1.0",
    "name": "@kody-w/peer_head_moving_sentinel",
    "version": "1.0.0",
    "description": "Watches another rapp-sentinel's published head (rapp-sentinel-head/1.0): fails when it goes stale, when a watcher's seq stops advancing between looks, or when it moves backwards.",
    "category": "output-freshness",
    "checks": {
        "peer_head_moving": {"domain": "neighborhood", "kind": "output-freshness"},
    },
    "config": {
        "peers": {
            "kody-w/rappter-neighborhood-watch":
                "https://gist.githubusercontent.com/kody-w/f3e0fcb63b4c5a2351572b7c5266bce7/raw/sentinel-head.json"
        },
        "max_age_h": 2.0,
        "min_gap_h": 1.0,
        "state_file": "peer_heads_seen.json",
        "timeout_s": 25,
    },
    "requires": [],
    "tags": ["neighborhood", "peers", "rapp-sentinel-head", "R2", "outsider"],
    "author": "kody-w",
    "license": "MIT",
    "vantage": "outsider",
}


def run(config=None, ctx=None):
    import json
    cfg = dict(__manifest__["config"], **(config or {}))
    c = _ctx(ctx)
    peers = cfg.get("peers") or {}
    if not isinstance(peers, dict) or not peers:
        return [c["fail"]("peer_head_moving", "no peers configured", critical=False)]
    seen = c["state_read"](cfg["state_file"]) or {}
    problems, blind, fine = [], [], []
    now_iso = c["now_iso"]()
    for name, url in sorted(peers.items()):
        try:
            status, body = c["http_get"](url, timeout=cfg.get("timeout_s", 25))
            if status != 200:
                raise RuntimeError(f"HTTP {status}")
            head = json.loads(body.decode("utf-8"))
        except Exception as e:
            blind.append(f"{name} ({type(e).__name__}: {str(e)[:40]})")
            continue
        age = c["hours_since"](head.get("utc"))
        if age is None:
            problems.append(f"{name}: head carries no readable utc")
            continue
        if age >= float(cfg.get("max_age_h", 2.0)):
            problems.append(f"{name}: head stale {age:.1f}h (bar {cfg.get('max_age_h')}h)")
            continue
        heads = head.get("heads") or {}
        seqs = {w: h.get("seq") for w, h in heads.items() if isinstance(h, dict)}
        prev = seen.get(name) or {}
        prev_seqs, prev_utc = prev.get("seqs") or {}, prev.get("utc")
        gap = c["hours_since"](prev_utc)
        stuck, backwards = [], []
        for w, s in seqs.items():
            p = prev_seqs.get(w)
            if p is None or s is None:
                continue
            if s < p:
                backwards.append(f"{w} {p}->{s}")
            elif s == p and gap is not None and gap >= float(cfg.get("min_gap_h", 1.0)):
                stuck.append(f"{w}@{s} for {gap:.1f}h")
        seen[name] = {"utc": now_iso, "seqs": seqs} if (not prev_seqs or seqs != prev_seqs
                                                         or gap is None) else prev
        if backwards:
            problems.append(f"{name}: seq went backwards ({', '.join(backwards)})")
        elif stuck:
            problems.append(f"{name}: no watcher advanced ({', '.join(stuck)})")
        else:
            fine.append(f"{name} {age:.1f}h/{len(seqs)}w")
    c["state_write"](cfg["state_file"], seen)
    if problems:
        return [c["fail"]("peer_head_moving", "; ".join(problems))]
    if blind:
        return [c["fail"]("peer_head_moving", f"{len(fine)} peer(s) fine; cannot read " + ", ".join(blind),
                          critical=False)]
    return [c["ok"]("peer_head_moving", ", ".join(fine))]


def prove():
    import json
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    iso = lambda dt: dt.isoformat().replace("+00:00", "Z")
    store = {}
    def state_read(name):
        return json.loads(json.dumps(store.get(name)))
    def state_write(name, doc):
        store[name] = doc
    def head(utc, seqs):
        return lambda u, timeout=0: (200, json.dumps({"utc": utc, "heads": {w: {"seq": s} for w, s in seqs.items()}}).encode())
    peers = {"p": "https://p.example/head.json"}
    ctx = {"state_read": state_read, "state_write": state_write}
    # control: fresh head, first sight — fine
    r = run({"peers": peers}, dict(ctx, http_get=head(iso(now), {"a": 10})))[0]; assert r["ok"], r
    # stale head
    r = run({"peers": peers}, dict(ctx, http_get=head(iso(now - timedelta(hours=5)), {"a": 11})))[0]; assert not r["ok"] and "stale" in r["detail"], r
    # published fresh but seq stuck for > min_gap_h (pretend we first saw it 2h ago)
    store["peer_heads_seen.json"] = {"p": {"utc": iso(now - timedelta(hours=2)), "seqs": {"a": 10}}}
    r = run({"peers": peers}, dict(ctx, http_get=head(iso(now), {"a": 10})))[0]; assert not r["ok"] and "no watcher advanced" in r["detail"], r
    # advanced -> fine, and state moves forward
    r = run({"peers": peers}, dict(ctx, http_get=head(iso(now), {"a": 12})))[0]; assert r["ok"], r
    assert store["peer_heads_seen.json"]["p"]["seqs"] == {"a": 12}, store
    # backwards
    r = run({"peers": peers}, dict(ctx, http_get=head(iso(now), {"a": 3})))[0]; assert not r["ok"] and "backwards" in r["detail"], r
    # blind
    def blind(u, timeout=0):
        raise OSError("dns")
    r = run({"peers": peers}, dict(ctx, http_get=blind))[0]; assert not r["ok"] and r["severity"] == "warn", r
    return True


# ── stdlib fallbacks ─────────────────────────────────────────────────────────

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


def _now_iso():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _state_dir():
    import os
    from pathlib import Path
    root = os.environ.get("SENTINEL_HOME") or os.path.join(os.path.expanduser("~"), ".rapp", "sentinel", "instance")
    p = Path(root) / "state" / "hub"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _state_read(name):
    import json
    p = _state_dir() / name
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _state_write(name, doc):
    import json
    p = _state_dir() / name
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(p)


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
        "now_iso": _now_iso,
        "state_read": _state_read,
        "state_write": _state_write,
    }
    base.update(ctx or {})
    return base


if __name__ == "__main__":
    import json, sys
    if "--prove" in sys.argv:
        sys.exit(0 if prove() else 1)
    print(json.dumps(run(), indent=2))
