#!/usr/bin/env python3
"""build_registry.py — scan sentinels/@publisher/*.py, validate each, write registry.json.

Run manually:  python3 build_registry.py          (exit 1 if any sentinel fails validation)
CI:            .github/workflows/build-registry.yml on every push to main
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sentinel_sdk as sdk  # noqa: E402

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "registry.json"


def build():
    entries, failures = [], []
    for path in sorted((ROOT / "sentinels").glob("@*/*.py")):
        errors, warns, m = sdk.validate_file(path, expect_path="strict")
        if errors:
            failures.append((path, errors))
            continue
        text = path.read_text(encoding="utf-8")
        pub, slug = sdk.NAME_RE.match(m["name"]).groups()
        entries.append({
            "name": m["name"], "publisher": pub, "slug": slug, "version": m["version"],
            "description": m["description"], "category": m["category"],
            "checks": list(m["checks"].keys()), "kinds": m["checks"],
            "config": m.get("config", {}), "requires": m.get("requires", []),
            "tags": m.get("tags", []), "author": m.get("author", pub),
            "license": m.get("license"), "vantage": m["vantage"],
            "path": str(path.relative_to(ROOT)).replace("\\", "/"),
            "raw_url": sdk.RAW_BASE + str(path.relative_to(ROOT)).replace("\\", "/"),
            "sha256": sdk.sha256_lf(text), "hash_algo": "sha256-lf-v1",
            "lines": text.count("\n") + 1,
            "install": f"python3 sentinel_sdk.py install {m['name']}",
        })
    doc = {
        "schema": "rapp-sentinel-hub/1.0",
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "hub": sdk.HUB_REPO,
        "count": len(entries),
        "publishers": sorted({e["publisher"] for e in entries}),
        "categories": sorted({e["category"] for e in entries}),
        "sentinels": entries,
    }
    # keep `generated` stable when nothing else changed, so CI/bots do not churn
    try:
        prev = json.loads(OUT.read_text(encoding="utf-8"))
        if {k: v for k, v in prev.items() if k != "generated"} == {k: v for k, v in doc.items() if k != "generated"}:
            doc["generated"] = prev["generated"]
    except Exception:
        pass
    if "--check" in sys.argv:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != json.dumps(doc, indent=2) + "\n":
            print("registry.json is stale - run python3 build_registry.py and commit")
            sys.exit(1)
        return doc, failures
    OUT.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return doc, failures


if __name__ == "__main__":
    doc, failures = build()
    for path, errors in failures:
        print(f"FAIL {path}")
        for e in errors:
            print(f"   - {e}")
    print(f"registry.json: {doc['count']} sentinel(s), {len(doc['publishers'])} publisher(s)"
          + (f", {len(failures)} FAILED" if failures else ""))
    sys.exit(1 if failures else 0)
