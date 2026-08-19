#!/usr/bin/env python3
"""workflows_starved_sentinel — a workflow that never succeeds any more (R3).

`fail == total` missed static-api cancelled 3/3. `cancelled > 0` would miss
an all-skipped workflow. So this judges run history by POSITIVE evidence
only: a workflow is healthy when at least one recent run concluded
"success"; it is starved when >= min_runs runs concluded and none of them
did. Every other colour - cancelled, skipped, timed_out, action_required,
failure, colours nobody has enumerated yet - is equally not-success.

Thin evidence is a prompt to look, never a defect and never health:
  UNREADABLE  the read failed (gh error) -> warn "cannot read", blind not broken
  UNDECIDED   fewer than min_runs verdicts -> reported in detail, not failed

Credentialed vantage: rides `gh`'s token (needs `gh auth login`).
"""

__manifest__ = {
    "schema": "rapp-sentinel/1.0",
    "name": "@kody-w/workflows_starved_sentinel",
    "version": "1.0.0",
    "description": "For each repo, lists active workflows and fails when one has >= min_runs recent verdicts and not a single explicit success - colour-blind about failure (R3).",
    "category": "run-status",
    "checks": {
        "workflows_starved": {"domain": "github", "kind": "run-status"},
    },
    "config": {
        "repos": ["kody-w/rapp-sentinel"],
        "per_workflow_runs": 5,
        "min_runs": 3,
        "ignore": [],
        "timeout_s": 25,
    },
    "requires": ["gh"],
    "tags": ["github", "actions", "workflows", "R3", "credentialed"],
    "author": "kody-w",
    "license": "MIT",
    "vantage": "credentialed",
}

UNREADABLE, UNDECIDED = "UNREADABLE", "UNDECIDED"


def _require_success(conclusions, min_runs=3):
    if conclusions is None:
        return UNREADABLE
    decided = [c for c in conclusions if c]
    if any(c == "success" for c in decided):
        return "success"
    return "no-success" if len(decided) >= min_runs else UNDECIDED


def run(config=None, ctx=None):
    cfg = dict(__manifest__["config"], **(config or {}))
    c = _ctx(ctx)
    repos = [r for r in (cfg.get("repos") or []) if isinstance(r, str) and "/" in r]
    if not repos:
        return [c["fail"]("workflows_starved", "no repos configured", critical=False)]
    ignore = set(cfg.get("ignore") or [])
    n, min_runs = int(cfg.get("per_workflow_runs", 5)), int(cfg.get("min_runs", 3))
    starved, blind, thin, judged = [], [], [], 0
    for repo in repos:
        wfs = c["gh"](["api", f"repos/{repo}/actions/workflows", "--paginate", "-q",
                       '[.workflows[] | select(.state=="active") | {id, name, path}]'])
        if wfs is None:
            blind.append(f"{repo}: cannot list workflows")
            continue
        for wf in wfs:
            name = wf.get("name") or wf.get("path")
            if name in ignore or wf.get("path", "").rsplit("/", 1)[-1] in ignore:
                continue
            runs = c["gh"](["api", f"repos/{repo}/actions/workflows/{wf['id']}/runs?per_page={n}",
                            "-q", "[.workflow_runs[].conclusion]"])
            verdict = _require_success(runs, min_runs)
            if verdict is UNREADABLE:
                blind.append(f"{repo}/{name}: cannot read runs")
            elif verdict is UNDECIDED:
                thin.append(f"{repo}/{name}")
            elif verdict == "no-success":
                starved.append(f"{repo}/{name} 0/{len([x for x in runs if x])}")
            else:
                judged += 1
    if starved:
        return [c["fail"]("workflows_starved", f"{len(starved)} starved (no success in last {n}): "
                          + ", ".join(starved))]
    detail = f"{judged} workflow(s) with a recent success"
    if thin:
        detail += f"; {len(thin)} too thin to judge (<{min_runs} verdicts)"
    if blind:
        return [c["fail"]("workflows_starved", detail + "; cannot read " + ", ".join(blind), critical=False)]
    return [c["ok"]("workflows_starved", detail)]


def prove():
    def fake_gh(table):
        def gh(args):
            path = args[1]
            if path.endswith("/actions/workflows"):
                return table.get("workflows")
            wid = path.split("/workflows/")[1].split("/")[0]
            return table.get(wid)
        return gh
    wfs = [{"id": 1, "name": "ci", "path": ".github/workflows/ci.yml"},
           {"id": 2, "name": "pages", "path": ".github/workflows/pages.yml"}]
    healthy = fake_gh({"workflows": wfs, "1": ["failure", "success", "failure"], "2": ["success"] * 3})
    starved = fake_gh({"workflows": wfs, "1": ["cancelled", "cancelled", "cancelled"], "2": ["success"] * 3})
    skipped = fake_gh({"workflows": wfs, "1": ["skipped", "timed_out", None, "action_required"], "2": ["success"]})
    thin = fake_gh({"workflows": wfs, "1": ["failure", None], "2": ["success"]})
    blind = fake_gh({"workflows": None})
    blind_runs = fake_gh({"workflows": wfs, "1": None, "2": ["success"]})
    r = run(None, {"gh": healthy})[0];   assert r["ok"], r
    r = run(None, {"gh": starved})[0];   assert not r["ok"] and r["severity"] == "critical" and "ci 0/3" in r["detail"], r
    r = run(None, {"gh": skipped})[0];   assert not r["ok"] and r["severity"] == "critical", r      # colour-blind
    r = run(None, {"gh": thin})[0];      assert r["ok"] and "too thin" in r["detail"], r
    r = run(None, {"gh": blind})[0];     assert not r["ok"] and r["severity"] == "warn", r
    r = run(None, {"gh": blind_runs})[0]; assert not r["ok"] and r["severity"] == "warn" and "cannot read" in r["detail"], r
    return True


def _gh(args, timeout=25):
    import json, subprocess
    try:
        r = subprocess.run(["gh"] + list(args), capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0:
            return None
        return json.loads(r.stdout) if r.stdout.strip() else None
    except Exception:
        return None


def _ctx(ctx):
    base = {
        "ok": lambda cid, detail="": {"id": cid, "ok": True, "severity": "warn", "detail": detail},
        "fail": lambda cid, detail="", critical=True: {
            "id": cid, "ok": False, "severity": "critical" if critical else "warn", "detail": detail},
        "gh": _gh,
    }
    base.update(ctx or {})
    return base


if __name__ == "__main__":
    import json, sys
    if "--prove" in sys.argv:
        sys.exit(0 if prove() else 1)
    print(json.dumps(run(), indent=2))
