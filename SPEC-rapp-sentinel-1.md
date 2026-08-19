# `rapp-sentinel/1.0` — the single-file sentinel

A hub sentinel is **one Python file**. Stdlib only. It runs alone
(`python3 file.py`, `python3 file.py --prove`) and it runs inside a host
sentinel (rapp-sentinel's `hub.py` loads it from `HOME/hub/`).

## 1. `__manifest__` — a dict LITERAL at module top level

| key | required | rule |
|---|---|---|
| `schema` | yes | `"rapp-sentinel/1.0"` |
| `name` | yes | `@publisher/slug_sentinel`; the file is `sentinels/@publisher/slug_sentinel.py`; publisher = the submitting GitHub login |
| `version` | yes | semver `x.y.z`; bump to update |
| `description` | yes | 20–300 chars, one honest sentence: what world it refuses to call healthy |
| `category` | yes | `reachability` · `output-freshness` · `run-status` · `consistency` · `watcher` · `example` |
| `checks` | yes | `{id: {"domain": str, "kind": one of the five kinds}}` — ids `^[a-z][a-z0-9_]{2,40}$`, unique across the hub, never renamed once published (hosts key state on them) |
| `config` | yes | defaults; the host merges `config.json → hub.config.<slug>` on top |
| `requires` | yes | binaries needed on PATH, e.g. `["gh"]`; `[]` for pure-stdlib |
| `vantage` | yes | `outsider` (no credentials touched) or `credentialed` |
| `tags`, `author`, `license` | license yes | MIT recommended |

The manifest is read with `ast.literal_eval` — no code runs to publish, browse, or install.

## 2. `run(config=None, ctx=None) -> list[result]`

`result = {"id": <declared id>, "ok": bool, "severity": "warn"|"critical", "detail": str}`

* **Every declared id, every tick.** A read that failed is `ok=False, severity=warn,
  detail="cannot read …"`, never a missing id, never a critical. *Blind is not broken.*
* `config` = manifest defaults merged with the host's overrides.
* `ctx` = dict of host helpers. Fallbacks live in the file, the host may override any:
  `ok`, `fail(cid, detail, critical=True)`, `http_get(url, timeout) -> (status, bytes)`
  (raises on transport failure), `gh(args) -> parsed JSON or None`, `hours_since(iso)`,
  `moving(cid, stamp_fn, max_age_h, what)`, `now_iso()`, `state_read(name)`, `state_write(name, doc)`.
* Read-only. No `eval/exec/os.system`, no deletion, no sockets, no `git push`/`gh pr create`
  (the validator refuses these).

## 3. `prove() -> True`

Break/control pairs with fake `ctx` helpers — no network. Prove the sentinel **fires on the
broken world and stays quiet on the healthy one**, and that a blind read yields warn.
The hub runs `prove()` at submit, at registry build, and again at install.

## 4. The three rules (TRIFECTA §6d, inherited from rapp-sentinel)

* **R1** receipts are not evidence — judge the output, not the log line that says it ran.
* **R2** ran is not worked — freshness of OUTPUT, never of a heartbeat the producer could stamp.
* **R3** require known-good — an explicit success; never enumerate the colours of failure.

## 5. In the host

`hub.py` merges each installed sentinel's declared ids into the required set (a hub sentinel that
stops emitting an id fails `w_checks_complete`) and its `kinds` into the R2 pairing map. Results
carry `produced_by = "hub:@pub/slug"` and `hub_version`. Trust is a dial: `hub.critical_allowed`
lists the slugs whose *critical* is honoured; everything else is demoted to warn with the reason in
`detail`. Missing config → nothing changes (growth path).
