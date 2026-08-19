#!/usr/bin/env python3
"""process_issue.py — turn a `[sentinel] @pub/slug@ver` Issue into a validated PR.

Runs in CI (process-issues.yml). Reads the issue body from ISSUE_BODY (or a file),
extracts the ```python block, validates it with the SDK, writes it to
sentinels/@pub/slug.py on a branch, opens a PR bound to the sha256-lf-v1 hash the
submitter posted, and comments back on the issue. Any failure -> comment + exit 0
(the workflow itself must not go red for a bad submission; the verdict is the comment).
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import sentinel_sdk as sdk  # noqa: E402

REPO = os.environ.get("GITHUB_REPOSITORY", sdk.HUB_REPO)
NUMBER = os.environ.get("ISSUE_NUMBER", "")
TITLE = os.environ.get("ISSUE_TITLE", "")
AUTHOR = os.environ.get("ISSUE_AUTHOR", "")
BODY = os.environ.get("ISSUE_BODY") or (Path(sys.argv[1]).read_text(encoding="utf-8") if len(sys.argv) > 1 else "")


def sh(*args, check=True, **kw):
    r = subprocess.run(list(args), capture_output=True, text=True, **kw)
    if check and r.returncode != 0:
        raise RuntimeError(f"{' '.join(args)}\n{r.stderr}")
    return r.stdout.strip()


def comment(text):
    if NUMBER and os.environ.get("GITHUB_TOKEN"):
        subprocess.run(["gh", "issue", "comment", NUMBER, "-R", REPO, "--body", text])
    else:
        print("[comment]", text)


def main():
    m = re.match(r"^\[sentinel\]\s+(@\S+?)(?:@(\d+\.\d+\.\d+))?\s*$", TITLE.strip())
    if not m:
        return 0                     # not a submission; nothing to do
    name = m.group(1)
    block = re.search(r"```python\n(.*?)\n```", BODY, re.S)
    if not block:
        comment("❌ No ```python block found in the issue body. Use `python3 sentinel_sdk.py submit path.py`.")
        return 0
    text = block.group(1).replace("\r\n", "\n") + "\n"
    posted = re.search(r"sha256-lf-v1:\s*`?([0-9a-f]{64})", BODY)
    digest = sdk.sha256_lf(text)
    if posted and posted.group(1) != digest:
        comment(f"❌ The posted hash `{posted.group(1)}` does not match the file in the body (`{digest}`). Re-run submit.")
        return 0
    mo = sdk.NAME_RE.match(name)
    if not mo:
        comment(f"❌ `{name}` is not a valid sentinel name (@publisher/slug_sentinel).")
        return 0
    pub, slug = mo.groups()
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / f"{slug}.py"
        p.write_text(text, encoding="utf-8")
        errors, warns, man = sdk.validate_file(p, expect_path=True)
    if not errors and man.get("name") != name:
        errors.append(f"issue title names {name} but the manifest says {man.get('name')}")
    if not errors and AUTHOR and pub.lower() != AUTHOR.lower():
        errors.append(f"publisher @{pub} must match the submitting GitHub account @{AUTHOR}")
    if errors:
        comment("❌ **Validation failed** for `" + name + "`:\n\n" + "\n".join(f"- {e}" for e in errors)
                + "\n\nFix locally with `python3 sentinel_sdk.py validate` and submit again.")
        return 0
    dest = ROOT / "sentinels" / f"@{pub}" / f"{slug}.py"
    dest.parent.mkdir(parents=True, exist_ok=True)
    existing = dest.exists()
    dest.write_text(text, encoding="utf-8")
    branch = f"submit/{pub}-{slug}-{NUMBER or 'local'}"
    sh("git", "config", "user.name", "sentinel-hub-bot")
    sh("git", "config", "user.email", "sentinel-hub-bot@users.noreply.github.com")
    sh("git", "checkout", "-B", branch)
    sh("git", "add", str(dest))
    subprocess.run(["python3", "build_registry.py"], cwd=ROOT)
    sh("git", "add", "registry.json")
    verb = "update" if existing else "add"
    sh("git", "commit", "-m", f"{verb} {name}@{man['version']} (issue #{NUMBER})\n\nsha256-lf-v1 {digest}\nsubmitted-by @{AUTHOR}")
    sh("git", "push", "-f", "origin", branch)
    body = (f"Closes #{NUMBER}\n\n**{verb}** `{name}` v{man['version']} — {man['description']}\n\n"
            f"- sha256-lf-v1: `{digest}`\n- category `{man['category']}` · vantage `{man['vantage']}` · checks `{', '.join(man['checks'])}`\n"
            f"- validated by process_issue.py: manifest ✔ prove() ✔ blind-ctx contract ✔\n\n"
            "A maintainer reads the file and merges. Nothing on the hub is automated past this point on purpose.")
    pr = sh("gh", "pr", "create", "-R", REPO, "--head", branch, "--base", "main",
            "--title", f"[sentinel] {verb} {name}@{man['version']}", "--body", body,
            "--label", "sentinel-submission", check=False) or "(pr create failed — see workflow log)"
    comment(f"✅ `{name}` v{man['version']} validated (`{digest}`). Pull request: {pr}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
