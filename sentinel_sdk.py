#!/usr/bin/env python3
"""sentinel_sdk.py — zero-dependency SDK for the RAPP Sentinel Hub.

    python3 sentinel_sdk.py new @you/my_thing_sentinel      scaffold from the template
    python3 sentinel_sdk.py validate path.py                 manifest + contract + proof
    python3 sentinel_sdk.py test path.py                     alias of validate (runs prove())
    python3 sentinel_sdk.py run path.py [--config JSON]      run it once, print results
    python3 sentinel_sdk.py submit path.py                   open the submission Issue (needs gh)
    python3 sentinel_sdk.py list [query]                     browse the hub registry
    python3 sentinel_sdk.py install @pub/slug [--home DIR]   drop it into a sentinel's hub/ dir
    python3 sentinel_sdk.py installed [--home DIR]           what a sentinel has grown
    python3 sentinel_sdk.py uninstall @pub/slug [--home DIR]

Every command supports --json. Stdlib only.

THE CONTRACT (SPEC-rapp-sentinel-1.md, short form)
  A hub sentinel is ONE .py file with:
    __manifest__   a dict LITERAL: schema, name (@pub/slug), version, description,
                   category, checks {id: {domain, kind}}, config (defaults),
                   requires ([] or ["gh"]), tags, author, license, vantage
    run(config, ctx) -> [ {id, ok, severity, detail}, ... ]
                   one result per declared id, ALWAYS - a read that failed is a
                   warn "cannot read", never a missing id and never a critical
    prove() -> True  break/control pairs proving the sentinel can tell a broken
                   world from a healthy one without touching the network
  The file must run standalone (`python3 file.py`, `--prove`); the host may
  override any helper through ctx (http_get, gh, moving, state_read...).
"""

import ast
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

HUB_REPO = "kody-w/rapp-sentinel-hub"
REGISTRY_URL = f"https://raw.githubusercontent.com/{HUB_REPO}/main/registry.json"
RAW_BASE = f"https://raw.githubusercontent.com/{HUB_REPO}/main/"
SCHEMA = "rapp-sentinel/1.0"
CATEGORIES = ("reachability", "output-freshness", "run-status", "consistency", "watcher", "example")
KINDS = ("reachability", "output-freshness", "run-status", "consistency", "watcher")
VANTAGES = ("outsider", "credentialed")
NAME_RE = re.compile(r"^@([A-Za-z0-9][A-Za-z0-9-]{0,38})/([a-z][a-z0-9_]{1,60}_sentinel)$")
ID_RE = re.compile(r"^[a-z][a-z0-9_]{2,40}$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
HERE = Path(__file__).resolve().parent

# things a read-only sentinel has no business doing
DENY_PATTERNS = (
    (r"\beval\s*\(", "eval()"),
    (r"\bexec\s*\(", "exec()"),
    (r"os\.system\s*\(", "os.system"),
    (r"shutil\.rmtree", "shutil.rmtree"),
    (r"os\.remove|os\.unlink|os\.rmdir", "file deletion"),
    (r"__import__\s*\(", "__import__"),
    (r"base64\.b64decode", "obfuscated payload"),
    (r"\bsocket\.", "raw sockets"),
    (r"git\s+push|gh\s+pr\s+create|gh\s+repo\s+delete", "write to GitHub"),
)


# ── hashing / manifest ─────────────────────────────────────────────────────

def sha256_lf(text):
    """sha256-lf-v1: UTF-8, CRLF -> LF, nothing else normalised (same as RAR)."""
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def read_manifest(path):
    """Return the __manifest__ dict LITERAL without importing the file."""
    tree = ast.parse(Path(path).read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "__manifest__" for t in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError("no top-level __manifest__ = {...} literal")


def load_module(path):
    spec = importlib.util.spec_from_file_location("hub_sentinel_" + hashlib.md5(str(path).encode()).hexdigest()[:8], path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def blind_ctx():
    """The world where every read fails. A sentinel must answer warn, not raise."""
    def http_get(url, timeout=0):
        raise OSError("blind: no network in the contract test")
    return {"http_get": http_get,
            "gh": lambda args, timeout=0: None,
            "state_read": lambda name: None,
            "state_write": lambda name, doc: None}


# ── validation ─────────────────────────────────────────────────────────────

def validate_file(path, expect_path=True):
    """Return (errors, warnings, manifest). Empty errors == publishable."""
    errors, warns = [], []
    path = Path(path)
    if not path.exists():
        return [f"{path}: no such file"], warns, None
    text = path.read_text(encoding="utf-8")
    try:
        compile(text, str(path), "exec")
    except SyntaxError as e:
        return [f"syntax error: {e}"], warns, None
    try:
        m = read_manifest(path)
    except Exception as e:
        return [f"manifest: {e}"], warns, None
    if not isinstance(m, dict):
        return ["manifest: not a dict"], warns, None

    if m.get("schema") != SCHEMA:
        errors.append(f"schema must be {SCHEMA!r}")
    name = m.get("name", "")
    mo = NAME_RE.match(str(name))
    if not mo:
        errors.append("name must look like @publisher/slug_sentinel")
    elif expect_path:
        pub, slug = mo.groups()
        if path.name != f"{slug}.py":
            errors.append(f"file must be named {slug}.py (is {path.name})")
        if path.parent.name != f"@{pub}" and expect_path == "strict":
            errors.append(f"file must live under sentinels/@{pub}/")
    if not SEMVER_RE.match(str(m.get("version", ""))):
        errors.append("version must be semver x.y.z")
    d = m.get("description", "")
    if not isinstance(d, str) or not (20 <= len(d) <= 300):
        errors.append("description must be 20-300 chars")
    if m.get("category") not in CATEGORIES:
        errors.append(f"category must be one of {CATEGORIES}")
    checks = m.get("checks")
    if not isinstance(checks, dict) or not checks:
        errors.append("checks must be a non-empty dict of id -> {domain, kind}")
        checks = {}
    for cid, meta in checks.items():
        if not ID_RE.match(str(cid)):
            errors.append(f"check id {cid!r} must match {ID_RE.pattern}")
        if not isinstance(meta, dict) or not meta.get("domain") or meta.get("kind") not in KINDS:
            errors.append(f"check {cid!r} needs domain and kind in {KINDS}")
    if not isinstance(m.get("config", {}), dict):
        errors.append("config must be a dict of defaults")
    if not isinstance(m.get("requires", []), list):
        errors.append("requires must be a list")
    if m.get("vantage") not in VANTAGES:
        errors.append(f"vantage must be one of {VANTAGES}")
    if not m.get("license"):
        errors.append("license is required (MIT recommended)")
    if not m.get("author"):
        warns.append("author missing")
    for pat, why in DENY_PATTERNS:
        if re.search(pat, text):
            errors.append(f"forbidden for a read-only sentinel: {why}")
    if errors:
        return errors, warns, m

    # dynamic contract
    try:
        mod = load_module(path)
    except Exception as e:
        return [f"import failed: {type(e).__name__}: {e}"], warns, m
    for fn in ("run", "prove"):
        if not callable(getattr(mod, fn, None)):
            errors.append(f"missing callable {fn}()")
    if errors:
        return errors, warns, m
    try:
        if mod.prove() is not True:
            errors.append("prove() must return True")
    except Exception as e:
        errors.append(f"prove() failed: {type(e).__name__}: {e}")
    try:
        results = mod.run(None, blind_ctx())
    except Exception as e:
        return errors + [f"run() raised under a blind ctx (must return warn 'cannot read'): {type(e).__name__}: {e}"], warns, m
    if not isinstance(results, list):
        return errors + ["run() must return a list of results"], warns, m
    seen = set()
    for r in results:
        if not isinstance(r, dict) or not {"id", "ok", "severity", "detail"} <= set(r):
            errors.append(f"malformed result {r!r}")
            continue
        if r["severity"] not in ("warn", "critical"):
            errors.append(f"result {r['id']}: severity must be warn|critical")
        if r["id"] not in checks:
            errors.append(f"run() emitted undeclared id {r['id']!r}")
        if r["id"] in seen:
            errors.append(f"run() emitted id {r['id']!r} twice")
        seen.add(r["id"])
        if not r["ok"] and r["severity"] == "critical":
            errors.append(f"result {r['id']}: critical under a BLIND ctx - blind is not broken; answer warn 'cannot read'")
    for cid in checks:
        if cid not in seen:
            errors.append(f"declared id {cid!r} not emitted by run() - every id must report every tick")
    return errors, warns, m


# ── registry ───────────────────────────────────────────────────────────────

def fetch_registry(url=REGISTRY_URL):
    local = HERE / "registry.json"
    if os.environ.get("SENTINEL_HUB_LOCAL") and local.exists():
        return json.loads(local.read_text(encoding="utf-8"))
    req = urllib.request.Request(url, headers={"User-Agent": "sentinel-sdk"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode("utf-8"))


def find_entry(reg, name):
    for e in reg.get("sentinels", []):
        if e.get("name") == name:
            return e
    return None


# ── home resolution ────────────────────────────────────────────────────────

def resolve_home(explicit=None):
    if explicit:
        return Path(explicit).expanduser()
    env = os.environ.get("SENTINEL_HOME", "").strip()
    if env:
        return Path(env).expanduser()
    live = Path.home() / "rapp-sentinel"
    if (live / "health.py").exists():
        return live
    return Path.home() / ".rapp" / "sentinel" / "instance"


# ── commands ───────────────────────────────────────────────────────────────

def cmd_new(args):
    name = args[0] if args else ""
    mo = NAME_RE.match(name)
    if not mo:
        sys.exit("usage: new @publisher/slug_sentinel  (slug must end in _sentinel)")
    pub, slug = mo.groups()
    dest = HERE / "sentinels" / f"@{pub}" / f"{slug}.py"
    if dest.exists():
        sys.exit(f"{dest} exists")
    tmpl = (HERE / "template_sentinel.py").read_text(encoding="utf-8")
    body = (tmpl.replace("@kody-w/template_sentinel", name)
                .replace("template_sentinel", slug)
                .replace('"author": "kody-w"', f'"author": "{pub}"'))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(body, encoding="utf-8")
    print(f"created {dest.relative_to(HERE)}\nnext: edit it, then  python3 sentinel_sdk.py validate {dest.relative_to(HERE)}")


def cmd_validate(args, as_json=False):
    if not args:
        sys.exit("usage: validate path.py")
    errors, warns, m = validate_file(args[0], expect_path=True)
    if as_json:
        print(json.dumps({"ok": not errors, "errors": errors, "warnings": warns,
                          "name": (m or {}).get("name"), "sha256": sha256_lf(Path(args[0]).read_text(encoding="utf-8"))}, indent=2))
    else:
        for w in warns:
            print(f"  warn: {w}")
        for e in errors:
            print(f"  FAIL: {e}")
        print(("PASS " if not errors else "FAIL ") + str((m or {}).get("name") or args[0]))
    sys.exit(0 if not errors else 1)


def cmd_run(args, as_json=False):
    if not args:
        sys.exit("usage: run path.py [--config JSON]")
    cfg = None
    if "--config" in args:
        cfg = json.loads(args[args.index("--config") + 1])
    mod = load_module(args[0])
    print(json.dumps(mod.run(cfg), indent=2))


def cmd_submit(args, as_json=False):
    if not args:
        sys.exit("usage: submit path.py")
    path = Path(args[0])
    errors, warns, m = validate_file(path, expect_path=True)
    if errors:
        print("\n".join("  FAIL: " + e for e in errors))
        sys.exit("fix validation errors before submitting")
    text = path.read_text(encoding="utf-8")
    digest = sha256_lf(text)
    title = f"[sentinel] {m['name']}@{m['version']}"
    body = "\n".join([
        f"**Sentinel submission** — `{m['name']}` v{m['version']}",
        "",
        f"- sha256-lf-v1: `{digest}`",
        f"- category: `{m['category']}` · vantage: `{m['vantage']}` · checks: `{', '.join(m['checks'])}`",
        f"- description: {m['description']}",
        "",
        "The hub's process-issues workflow validates this file, stages it on a branch,",
        "and opens a pull request bound to the hash above. A maintainer merges it.",
        "",
        "```python",
        text.rstrip("\n"),
        "```",
    ])
    r = subprocess.run(["gh", "issue", "create", "-R", HUB_REPO, "--title", title,
                        "--body", body, "--label", "sentinel-submission"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        # label may not exist for a fresh fork of the hub; retry unlabeled
        r = subprocess.run(["gh", "issue", "create", "-R", HUB_REPO, "--title", title, "--body", body],
                           capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("gh issue create failed:\n" + r.stderr)
    url = r.stdout.strip()
    print(json.dumps({"issue": url, "sha256": digest}) if as_json else f"submitted: {url}\nsha256-lf-v1 {digest}")


def cmd_list(args, as_json=False):
    reg = fetch_registry()
    q = " ".join(a for a in args if not a.startswith("--")).lower()
    rows = [e for e in reg.get("sentinels", [])
            if not q or q in json.dumps(e).lower()]
    if as_json:
        print(json.dumps(rows, indent=2))
        return
    for e in rows:
        print(f"{e['name']:<44} v{e['version']:<7} {e['category']:<16} {e['vantage']:<12} {', '.join(e['checks'])}")
        print(f"    {e['description']}")
    print(f"{len(rows)} sentinel(s)" + (f" matching {q!r}" if q else ""))


def cmd_install(args, as_json=False):
    if not args:
        sys.exit("usage: install @pub/slug [--home DIR]")
    name = args[0]
    home = resolve_home(args[args.index("--home") + 1] if "--home" in args else None)
    reg = fetch_registry()
    e = find_entry(reg, name)
    if not e:
        sys.exit(f"{name} is not in the hub registry")
    req = urllib.request.Request(RAW_BASE + e["path"], headers={"User-Agent": "sentinel-sdk"})
    with urllib.request.urlopen(req, timeout=25) as r:
        text = r.read().decode("utf-8")
    if sha256_lf(text) != e["sha256"]:
        sys.exit(f"refusing: fetched bytes do not match the registry hash for {name}")
    errors, _, _ = validate_file(_tmpfile(text, e["slug"]), expect_path=False)
    if errors:
        sys.exit("refusing: fetched sentinel fails the contract:\n" + "\n".join("  " + x for x in errors))
    hub = home / "hub"
    hub.mkdir(parents=True, exist_ok=True)
    dest = hub / f"{e['slug']}.py"
    dest.write_text(text, encoding="utf-8")
    missing = [b for b in e.get("requires", []) if not _which(b)]
    out = {"installed": name, "version": e["version"], "path": str(dest), "home": str(home),
           "checks": e["checks"], "missing_binaries": missing}
    if as_json:
        print(json.dumps(out, indent=2))
    else:
        print(f"installed {name} v{e['version']} -> {dest}")
        print(f"checks: {', '.join(e['checks'])}  (the host reports them under produced_by=hub:{name})")
        if missing:
            print(f"WARNING: needs {', '.join(missing)} on PATH")
        print("override defaults in config.json:  \"hub\": {\"config\": {\"%s\": {...}}}" % e["slug"])


def cmd_installed(args, as_json=False):
    home = resolve_home(args[args.index("--home") + 1] if "--home" in args else None)
    hub = home / "hub"
    rows = []
    for p in sorted(hub.glob("*.py")) if hub.exists() else []:
        try:
            m = read_manifest(p)
            rows.append({"name": m.get("name"), "version": m.get("version"), "path": str(p),
                         "checks": list((m.get("checks") or {}).keys())})
        except Exception as e:
            rows.append({"name": p.stem, "error": str(e), "path": str(p)})
    if as_json:
        print(json.dumps({"home": str(home), "sentinels": rows}, indent=2))
    else:
        print(f"home: {home}")
        for r in rows:
            print(f"  {r.get('name')} v{r.get('version', '?')}  {', '.join(r.get('checks', []))}" + (f"  ERROR {r['error']}" if 'error' in r else ""))
        if not rows:
            print("  (nothing installed)")


def cmd_uninstall(args, as_json=False):
    if not args:
        sys.exit("usage: uninstall @pub/slug [--home DIR]")
    home = resolve_home(args[args.index("--home") + 1] if "--home" in args else None)
    mo = NAME_RE.match(args[0])
    if not mo:
        sys.exit("name must look like @pub/slug_sentinel")
    dest = home / "hub" / f"{mo.group(2)}.py"
    if not dest.exists():
        sys.exit(f"{dest} not installed")
    dest.rename(dest.with_suffix(".py.removed"))
    print(f"removed {args[0]} (kept as {dest.name}.removed; delete when you are sure)")


def _tmpfile(text, slug):
    import tempfile
    d = Path(tempfile.mkdtemp(prefix="sentinel-hub-"))
    p = d / f"{slug}.py"
    p.write_text(text, encoding="utf-8")
    return p


def _which(binary):
    from shutil import which
    return which(binary)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    as_json = "--json" in argv
    argv = [a for a in argv if a != "--json"]
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    table = {"new": lambda: cmd_new(rest), "validate": lambda: cmd_validate(rest, as_json),
             "test": lambda: cmd_validate(rest, as_json), "run": lambda: cmd_run(rest, as_json),
             "submit": lambda: cmd_submit(rest, as_json), "list": lambda: cmd_list(rest, as_json),
             "search": lambda: cmd_list(rest, as_json), "install": lambda: cmd_install(rest, as_json),
             "installed": lambda: cmd_installed(rest, as_json), "uninstall": lambda: cmd_uninstall(rest, as_json)}
    if cmd not in table:
        print(__doc__)
        return 2
    table[cmd]()
    return 0


if __name__ == "__main__":
    sys.exit(main())
