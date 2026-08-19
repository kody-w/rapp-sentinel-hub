# Contributing a sentinel

1. `python3 sentinel_sdk.py new @you/thing_sentinel` — scaffold.
2. Write `run()` and `prove()`. Read `SPEC-rapp-sentinel-1.md` once; the validator enforces it.
3. `python3 sentinel_sdk.py validate sentinels/@you/thing_sentinel.py` until it says PASS.
4. `python3 sentinel_sdk.py submit sentinels/@you/thing_sentinel.py` — opens the Issue
   (needs `gh auth login`). CI validates, opens the PR bound to your file's hash, and a
   maintainer merges. Or just open the PR yourself.

**What gets merged:** stdlib-only, read-only, honest about blindness, and a `prove()` that
actually breaks the world. Positive-by-design like RAR: no automated reviews, no downvotes —
useful sentinels rise by being installed.

**Updating:** bump `version`, submit again. Never rename a check id.
