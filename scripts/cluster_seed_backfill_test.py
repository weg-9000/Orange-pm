#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for cluster_seed_backfill.py (P5 bootstrap — sidecar YAML).

stdlib unittest. Same style as cluster_identify_test.py (_run + SystemExit).
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))

from cluster_seed_backfill import (  # type: ignore
    backfill_seeds,
    run_backfill,
    _read_fr_index,
    _read_seeds,
    _dump_seeds,
)


_FR_INDEX = {
    "FR-101": {"capability": "Provisioning", "cluster_id": "PR-01"},
    "FR-102": {"capability": "Provisioning", "cluster_id": "PR-01"},
    "FR-201": {"capability": "DataProjection", "cluster_id": "DA-01"},
}


# ── 1. inject into an empty sidecar ─────────────────────────────────────────────────
class TestInject(unittest.TestCase):
    def test_injects_into_empty_sidecar(self):
        new_seeds, changes = backfill_seeds(_FR_INDEX, {})
        injected = [c for c in changes if c["action"] == "injected"]
        self.assertEqual(len(injected), 3)
        self.assertEqual(new_seeds["FR-101"]["capability"], "Provisioning")
        self.assertEqual(new_seeds["FR-101"]["cluster_hint"], "PR-01")
        self.assertEqual(new_seeds["FR-201"]["capability"], "DataProjection")
        self.assertEqual(new_seeds["FR-201"]["cluster_hint"], "DA-01")

    def test_cluster_hint_omitted_when_absent(self):
        idx = {"FR-9": {"capability": "Notify"}}  # no cluster_id
        new_seeds, _ = backfill_seeds(idx, {})
        self.assertEqual(new_seeds["FR-9"]["capability"], "Notify")
        self.assertNotIn("cluster_hint", new_seeds["FR-9"])

    def test_empty_index_no_changes(self):
        new_seeds, changes = backfill_seeds({}, {})
        self.assertEqual(new_seeds, {})
        self.assertEqual(changes, [])


# ── 2. idempotent — skip existing capability ───────────────────────────
class TestIdempotent(unittest.TestCase):
    def test_second_run_skips_existing(self):
        once, _ = backfill_seeds(_FR_INDEX, {})
        twice, changes = backfill_seeds(_FR_INDEX, once)
        self.assertEqual(once, twice)
        skipped = [c for c in changes if c["action"] == "skipped_existing"]
        self.assertEqual(len(skipped), 3)
        self.assertEqual([c for c in changes if c["action"] == "injected"], [])


# ── 3. --force overwrite ───────────────────────────────────────────────────
class TestForce(unittest.TestCase):
    def test_force_overwrites_existing(self):
        once, _ = backfill_seeds(_FR_INDEX, {})
        new_index = dict(_FR_INDEX)
        new_index["FR-101"] = {"capability": "Catalog", "cluster_id": "CA-02"}
        forced, changes = backfill_seeds(new_index, once, force=True)
        updated = [c for c in changes if c["action"] == "updated"]
        self.assertTrue(any(c["fr"] == "FR-101" for c in updated))
        self.assertEqual(forced["FR-101"]["capability"], "Catalog")
        self.assertEqual(forced["FR-101"]["cluster_hint"], "CA-02")
        # FR-102 stays Provisioning
        self.assertEqual(forced["FR-102"]["capability"], "Provisioning")

    def test_force_preserves_extra_fields(self):
        seeds = {"FR-101": {"capability": "Old", "cluster_hint": "OL-01", "lock": True}}
        forced, _ = backfill_seeds(_FR_INDEX, seeds, force=True)
        # capability/cluster_hint are updated, lock is preserved
        self.assertEqual(forced["FR-101"]["capability"], "Provisioning")
        self.assertEqual(forced["FR-101"]["cluster_hint"], "PR-01")
        self.assertTrue(forced["FR-101"]["lock"])


# ── 4. preserve existing entries not in fr_index ────────────────────────────────────
class TestPreserve(unittest.TestCase):
    def test_unrelated_existing_entries_preserved(self):
        seeds = {
            "FR-900": {"capability": "Legacy", "cluster_hint": "LE-01", "lock": True},
        }
        new_seeds, _ = backfill_seeds(_FR_INDEX, seeds)
        # FR-900, not in fr_index, is preserved as-is
        self.assertEqual(new_seeds["FR-900"], seeds["FR-900"])
        # new entries are also added
        self.assertIn("FR-101", new_seeds)

    def test_skip_preserves_existing_fields(self):
        seeds = {"FR-101": {"capability": "Mine", "cluster_hint": "MI-01", "lock": True}}
        new_seeds, changes = backfill_seeds(_FR_INDEX, seeds)
        # capability already exists, so it's skipped -> stays as the original
        self.assertEqual(new_seeds["FR-101"], seeds["FR-101"])
        self.assertTrue(any(c["fr"] == "FR-101" and c["action"] == "skipped_existing"
                            for c in changes))

    def test_does_not_mutate_input_seeds(self):
        seeds = {"FR-900": {"capability": "Legacy"}}
        backfill_seeds(_FR_INDEX, seeds)
        # the input dict is not mutated
        self.assertEqual(seeds, {"FR-900": {"capability": "Legacy"}})


# ── 5. graceful input handling ─────────────────────────────────────────────────
class TestGraceful(unittest.TestCase):
    def test_read_fr_index_tolerates_bad_shapes(self):
        self.assertEqual(_read_fr_index({}), {})
        self.assertEqual(_read_fr_index({"fr_index": "nope"}), {})
        idx = _read_fr_index({"fr_index": {"FR-1": {"capability": "X"}, "FR-2": 5}})
        self.assertIn("FR-1", idx)
        self.assertNotIn("FR-2", idx)

    def test_read_seeds_missing_file_returns_empty(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(_read_seeds(Path(t) / "nope.yml"), {})

    def test_read_seeds_corrupt_yaml_returns_empty(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "bad.yml"
            p.write_text("::: not valid yaml :::\n  - [", encoding="utf-8")
            self.assertEqual(_read_seeds(p), {})

    def test_index_without_capability_skipped(self):
        idx = {"FR-1": {"cluster_id": "AA-01"}}  # no capability
        new_seeds, changes = backfill_seeds(idx, {})
        self.assertNotIn("FR-1", new_seeds)
        self.assertEqual(changes, [])


# ── 6. deterministic output (sorted) ─────────────────────────────────────────────────
class TestDeterministic(unittest.TestCase):
    def test_dump_is_sorted_and_stable(self):
        seeds = {
            "FR-201": {"capability": "DataProjection", "cluster_hint": "DA-01"},
            "FR-101": {"capability": "Provisioning", "cluster_hint": "PR-01"},
        }
        out = _dump_seeds(seeds)
        # FR-101 comes before FR-201 (sort_keys)
        self.assertLess(out.index("FR-101"), out.index("FR-201"))
        # dumping twice gives the same result
        self.assertEqual(out, _dump_seeds(seeds))

    def test_dump_preserves_unicode(self):
        seeds = {"FR-1": {"capability": "[needs-confirmation ✓]"}}
        out = _dump_seeds(seeds)
        self.assertIn("[needs-confirmation ✓]", out)
        # round-trip
        self.assertEqual(yaml.safe_load(out)["FR-1"]["capability"], "[needs-confirmation ✓]")


# ── 7. file I/O + dry-run / input errors ─────────────────────────────────────
class TestRunBackfill(unittest.TestCase):
    def _write_cluster_map(self, tmp: Path, fr_index: dict) -> Path:
        cmap = tmp / "cluster_map.json"
        cmap.write_text(json.dumps({"fr_index": fr_index}), encoding="utf-8")
        return cmap

    def test_inject_into_empty_sidecar_writes_file(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            cmap = self._write_cluster_map(tmp, _FR_INDEX)
            seeds = tmp / "requirements.seeds.yml"
            code, changes = run_backfill(cmap, seeds)
            self.assertEqual(code, 0)
            self.assertTrue(seeds.is_file())
            data = yaml.safe_load(seeds.read_text(encoding="utf-8"))
            self.assertEqual(data["FR-101"]["capability"], "Provisioning")
            self.assertEqual(data["FR-101"]["cluster_hint"], "PR-01")
            self.assertEqual(
                len([c for c in changes if c["action"] == "injected"]), 3
            )

    def test_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            cmap = self._write_cluster_map(tmp, _FR_INDEX)
            seeds = tmp / "requirements.seeds.yml"
            code, changes = run_backfill(cmap, seeds, dry_run=True)
            self.assertEqual(code, 0)
            self.assertFalse(seeds.exists())  # not written
            self.assertEqual(
                len([c for c in changes if c["action"] == "injected"]), 3
            )

    def test_idempotent_skip_via_files(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            cmap = self._write_cluster_map(tmp, _FR_INDEX)
            seeds = tmp / "requirements.seeds.yml"
            run_backfill(cmap, seeds)
            first = seeds.read_text(encoding="utf-8")
            code, changes = run_backfill(cmap, seeds)
            self.assertEqual(code, 0)
            self.assertEqual(seeds.read_text(encoding="utf-8"), first)  # unchanged
            self.assertEqual(
                len([c for c in changes if c["action"] == "skipped_existing"]), 3
            )

    def test_force_overwrite_via_files(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            cmap = self._write_cluster_map(tmp, _FR_INDEX)
            seeds = tmp / "requirements.seeds.yml"
            run_backfill(cmap, seeds)
            # update cluster_map then --force
            cmap.write_text(json.dumps({"fr_index": {
                "FR-101": {"capability": "Catalog", "cluster_id": "CA-02"},
            }}), encoding="utf-8")
            code, changes = run_backfill(cmap, seeds, force=True)
            self.assertEqual(code, 0)
            data = yaml.safe_load(seeds.read_text(encoding="utf-8"))
            self.assertEqual(data["FR-101"]["capability"], "Catalog")
            self.assertEqual(data["FR-101"]["cluster_hint"], "CA-02")
            # the original FR-102 is preserved
            self.assertEqual(data["FR-102"]["capability"], "Provisioning")

    def test_preserves_unrelated_existing_entries(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            cmap = self._write_cluster_map(tmp, _FR_INDEX)
            seeds = tmp / "requirements.seeds.yml"
            seeds.write_text(
                _dump_seeds({"FR-900": {"capability": "Legacy", "lock": True}}),
                encoding="utf-8",
            )
            code, _ = run_backfill(cmap, seeds)
            self.assertEqual(code, 0)
            data = yaml.safe_load(seeds.read_text(encoding="utf-8"))
            self.assertEqual(data["FR-900"]["capability"], "Legacy")
            self.assertTrue(data["FR-900"]["lock"])
            self.assertIn("FR-101", data)

    def test_written_yaml_is_sorted(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            cmap = self._write_cluster_map(tmp, _FR_INDEX)
            seeds = tmp / "requirements.seeds.yml"
            run_backfill(cmap, seeds)
            text = seeds.read_text(encoding="utf-8")
            self.assertLess(text.index("FR-101"), text.index("FR-201"))

    def test_missing_cluster_map_is_input_error(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            code, _ = run_backfill(tmp / "nope.json", tmp / "seeds.yml")
            self.assertEqual(code, 1)
            self.assertFalse((tmp / "seeds.yml").exists())

    def test_corrupt_cluster_map_is_graceful_input_error(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            cmap = tmp / "cluster_map.json"
            cmap.write_text("{ not json", encoding="utf-8")
            code, _ = run_backfill(cmap, tmp / "seeds.yml")
            self.assertEqual(code, 1)


# ── runner ───────────────────────────────────────────────────────────────
def _run() -> int:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in (
        TestInject,
        TestIdempotent,
        TestForce,
        TestPreserve,
        TestGraceful,
        TestDeterministic,
        TestRunBackfill,
    ):
        suite.addTests(loader.loadTestsFromTestCase(cls))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    total = result.testsRun
    failed = len(result.failures) + len(result.errors)
    print(f"\nTotal {total} — PASS {total - failed} / FAIL {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(_run())
