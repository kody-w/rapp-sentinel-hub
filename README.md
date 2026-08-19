# RAPP Sentinel Hub

**Post useful rapp sentinels the way RAR posts `agent.py`s.** One file each. Browse, install,
grow your own watchdog.

> A [rapp-sentinel](https://github.com/kody-w/rapp-sentinel) is a watchdog that can't quietly
> lie to you. This hub is where the checks it runs get shared: single-file sentinels that
> follow one contract (`rapp-sentinel/1.0`), prove themselves before they publish, and drop
> into any running sentinel's `hub/` directory without a restart.

**[Browse the hub](https://kody-w.github.io/rapp-sentinel-hub/)** · [registry.json](https://kody-w.github.io/rapp-sentinel-hub/registry.json) · [the contract](SPEC-rapp-sentinel-1.md) · [contribute](CONTRIBUTING.md)

## Use one (three commands)

```bash
curl -O https://raw.githubusercontent.com/kody-w/rapp-sentinel-hub/main/sentinel_sdk.py
python3 sentinel_sdk.py list                                    # what's on the hub
python3 sentinel_sdk.py install @kody-w/output_moving_sentinel  # -> <your sentinel HOME>/hub/
```

`install` verifies the fetched bytes against the registry hash, re-runs the file's own
`prove()`, and writes it to your sentinel's `hub/` directory (`--home DIR`, `$SENTINEL_HOME`,
`~/rapp-sentinel`, or `~/.rapp/sentinel/instance`). The next `health.py` tick loads it —
its check ids join the required set, so it can never silently stop running. That is a **molt**: the
running organism keeps its state and chains and grows a new check — never a transplant. Override
defaults in `config.json`:

```json
"hub": {"config": {"output_moving_sentinel": {"url": "https://you.github.io/x/state.json", "field": "built", "max_age_h": 6}},
        "critical_allowed": ["output_moving_sentinel"]}
```

Every sentinel also runs alone: `python3 output_moving_sentinel.py` (one shot) · `--prove` (its proof).

## Publish one

```bash
python3 sentinel_sdk.py new @you/thing_sentinel      # scaffold from the template
python3 sentinel_sdk.py validate sentinels/@you/thing_sentinel.py
python3 sentinel_sdk.py submit   sentinels/@you/thing_sentinel.py   # opens the Issue → CI → PR
```

## The contract in one breath

`__manifest__` (a literal: name, version, checks `{id: {domain, kind}}`, config defaults, vantage)
· `run(config, ctx) -> [{id, ok, severity, detail}]` — every declared id every tick, a failed read is
a *warn* ("blind is not broken") · `prove() -> True` — break/control pairs, no network.
Full text: [SPEC-rapp-sentinel-1.md](SPEC-rapp-sentinel-1.md).

Three rules every sentinel is held to: **R1** receipts aren't evidence · **R2** ran isn't worked ·
**R3** require known-good, never enumerate known-bad. The frames a sentinel emits and verifies are
[RAPP rev-5](https://kody-w.github.io/rapp-1/guide/) frames — read the visual guide for the protocol.

## What's here today

| sentinel | kind | vantage | claims |
|---|---|---|---|
| `@kody-w/sites_up_sentinel` | reachability | outsider | every named URL answers 200; partial outages named |
| `@kody-w/github_status_sentinel` | reachability | outsider | GitHub's outage is never mistaken for yours (warn) |
| `@kody-w/json_serves_sentinel` | consistency | outsider | served JSON parses and carries the keys you require |
| `@kody-w/output_moving_sentinel` | output-freshness | outsider | the timestamp *inside the output* is younger than the bar (R2) |
| `@kody-w/peer_head_moving_sentinel` | output-freshness | outsider | a neighbor's `rapp-sentinel-head/1.0` keeps advancing; never backwards |
| `@kody-w/workflows_starved_sentinel` | run-status | credentialed (`gh`) | a workflow with N verdicts and no explicit success (R3) |
| `@kody-w/hello_world_sentinel` | example | outsider | the contract, in 60 lines |

Positive by design, like RAR: no automated reviews, no downvotes. Human review at merge; useful
sentinels rise by being installed.

MIT. Stdlib only. Runs on Python 3.9+.
