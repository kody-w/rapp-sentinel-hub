"""Every sentinel on the hub honours the contract; the SDK and registry hold together."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import sentinel_sdk as sdk  # noqa: E402

FILES = sorted((ROOT / "sentinels").glob("@*/*.py"))


class EverySentinel(unittest.TestCase):
    def test_at_least_one_sentinel(self):
        self.assertTrue(FILES)

    def test_contract(self):
        for p in FILES:
            with self.subTest(p.name):
                errors, _, m = sdk.validate_file(p, expect_path="strict")
                self.assertEqual(errors, [], f"{p}: {errors}")

    def test_standalone_prove_cli(self):
        for p in FILES:
            with self.subTest(p.name):
                r = subprocess.run([sys.executable, str(p), "--prove"], capture_output=True, text=True, timeout=120)
                self.assertEqual(r.returncode, 0, r.stderr)

    def test_unique_ids_across_hub(self):
        seen = {}
        for p in FILES:
            for cid in sdk.read_manifest(p)["checks"]:
                self.assertNotIn(cid, seen, f"check id {cid} declared by both {seen.get(cid)} and {p.name}")
                seen[cid] = p.name


class Registry(unittest.TestCase):
    def test_registry_matches_tree(self):
        import build_registry
        doc, failures = build_registry.build()
        self.assertEqual(failures, [])
        self.assertEqual({e["path"] for e in doc["sentinels"]},
                         {str(p.relative_to(ROOT)) for p in FILES})
        for e in doc["sentinels"]:
            self.assertEqual(e["sha256"], sdk.sha256_lf((ROOT / e["path"]).read_text(encoding="utf-8")))


class Sdk(unittest.TestCase):
    def test_validator_rejects_blind_critical_and_missing_ids(self):
        bad = ROOT / "sentinels" / "@kody-w" / "hello_world_sentinel.py"
        text = bad.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "hello_world_sentinel.py"
            # declares two ids, emits one
            p.write_text(text.replace('"hello_world": {"domain": "example", "kind": "consistency"},',
                                      '"hello_world": {"domain": "example", "kind": "consistency"}, "ghost": {"domain": "example", "kind": "consistency"},'),
                         encoding="utf-8")
            errors, _, _ = sdk.validate_file(p, expect_path=False)
            self.assertTrue(any("ghost" in e for e in errors), errors)
            # critical under a blind ctx
            p.write_text(text.replace('return [c["ok"]("hello_world", f"{cfg[\'greeting\']} - the contract holds")]',
                                      'return [c["fail"]("hello_world", "boom")]'), encoding="utf-8")
            errors, _, _ = sdk.validate_file(p, expect_path=False)
            self.assertTrue(any("blind" in e.lower() for e in errors), errors)

    def test_new_then_validate(self):
        with tempfile.TemporaryDirectory() as d:
            env = dict(os.environ)
            # scaffold into a copy of the repo so `new` writes under a temp sentinels/ tree
            import shutil
            work = Path(d) / "hub"
            shutil.copytree(ROOT, work, ignore=shutil.ignore_patterns(".git", "__pycache__", "tests"))
            r = subprocess.run([sys.executable, "sentinel_sdk.py", "new", "@tester/probe_sentinel"],
                               cwd=work, capture_output=True, text=True, env=env)
            self.assertEqual(r.returncode, 0, r.stderr)
            r = subprocess.run([sys.executable, "sentinel_sdk.py", "validate", "sentinels/@tester/probe_sentinel.py"],
                               cwd=work, capture_output=True, text=True, env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_install_from_local_registry(self):
        with tempfile.TemporaryDirectory() as d:
            env = dict(os.environ, SENTINEL_HUB_LOCAL="1")
            home = Path(d) / "home"
            # point RAW fetch at the local tree by monkeypatching through a tiny shim
            code = (
                "import sys, sentinel_sdk as s, urllib.request\n"
                "from pathlib import Path\n"
                "class R:\n"
                "    def __init__(self, p): self.p = p\n"
                "    def __enter__(self): return self\n"
                "    def __exit__(self, *a): pass\n"
                "    def read(self): return Path(self.p).read_bytes()\n"
                "s.urllib.request.urlopen = lambda req, timeout=0: R(str(s.HERE / req.full_url.replace(s.RAW_BASE, '')))\n"
                f"s.main(['install', '@kody-w/hello_world_sentinel', '--home', {str(home)!r}])\n"
                f"s.main(['installed', '--home', {str(home)!r}, '--json'])\n"
            )
            r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertTrue((home / "hub" / "hello_world_sentinel.py").exists())
            self.assertIn("@kody-w/hello_world_sentinel", r.stdout)


if __name__ == "__main__":
    unittest.main()
