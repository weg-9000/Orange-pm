#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for fr_cluster_check.py (P4, docs/fr-cluster-alignment.md).

stdlib unittest. Covers clean pass / orphan WARN / unmapped WARN /
mismatch BLOCK (both directions) / exit codes / graceful handling of
corrupt input. Seeds are read from the sidecar requirements.seeds.yml
(not inline tags).
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from fr_cluster_check import (  # type: ignore
    Finding,
    check_traceability,
    exit_code_for,
    parse_fr_ids,
    parse_cluster_fr_refs,
    read_fr_index,
    read_seeds,
    render_report,
    run_check,
    seeded_set,
)


# ── 1. Parse requirements FR universe (no seed info) ──────────────────────
class TestParseFrIds(unittest.TestCase):
    def test_parses_leading_fr_universe(self):
        md = (
            "| **FR-101** | name | desc | P0 |\n"
            "| **FR-102** | name | desc | P1 |\n"
            "A mention of FR-999 in body text is not a row subject\n"
        )
        ids = parse_fr_ids(md)
        self.assertEqual(ids, ["FR-101", "FR-102"])  # order preserved, deduped

    def test_dedupes_repeated_fr(self):
        md = (
            "| FR-101 | a | b | P0 |\n"
            "| FR-101 | a | c | P0 |\n"
        )
        self.assertEqual(parse_fr_ids(md), ["FR-101"])

    def test_non_string_graceful(self):
        self.assertEqual(parse_fr_ids(None), [])  # type: ignore[arg-type]


# ── 1b. Parse sidecar seeds yml ───────────────────────────────────────────
class TestReadSeeds(unittest.TestCase):
    def _write(self, tmp: Path, text: str) -> Path:
        p = tmp / "requirements.seeds.yml"
        p.write_text(text, encoding="utf-8")
        return p

    def test_reads_map_and_seeded_set(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            p = self._write(
                tmp,
                "FR-101:\n"
                "  capability: Provisioning\n"
                "  cluster_hint: PR\n"
                "FR-102:\n"
                "  capability: ''\n"      # empty capability → not a seed
                "FR-103:\n"
                "  cluster_hint: X\n",    # no capability key → not a seed
            )
            seeds = read_seeds(p)
            self.assertEqual(seeds["FR-101"]["capability"], "Provisioning")
            self.assertEqual(seeded_set(seeds), {"FR-101"})

    def test_missing_file_graceful(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(read_seeds(Path(t) / "nope.yml"), {})

    def test_corrupt_yaml_graceful(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            p = self._write(tmp, "FR-101: [unclosed\n  : : :")
            self.assertEqual(read_seeds(p), {})

    def test_non_mapping_top_level_graceful(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            p = self._write(tmp, "- FR-101\n- FR-102\n")  # list, not map
            self.assertEqual(read_seeds(p), {})

    def test_seeded_set_non_dict_graceful(self):
        self.assertEqual(seeded_set(None), set())  # type: ignore[arg-type]


# ── 2. Parse cluster draft fr_refs ────────────────────────────────────────
class TestParseClusterFrRefs(unittest.TestCase):
    def test_block_list(self):
        text = (
            "---\n"
            'cluster_id: "PR-01"\n'
            "fr_refs:\n"
            '  - "FR-101"\n'
            '  - "FR-103"\n'
            "domain_objects: [\"Instance\"]\n"
            "---\n"
            "body\n"
        )
        cid, refs = parse_cluster_fr_refs(text)
        self.assertEqual(cid, "PR-01")
        self.assertEqual(refs, ["FR-101", "FR-103"])

    def test_inline_list(self):
        text = 'cluster_id: PR-02\nfr_refs: ["FR-201", "FR-202"]\n'
        cid, refs = parse_cluster_fr_refs(text)
        self.assertEqual(cid, "PR-02")
        self.assertEqual(refs, ["FR-201", "FR-202"])

    def test_no_cluster_id_graceful(self):
        cid, refs = parse_cluster_fr_refs("no frontmatter here")
        self.assertIsNone(cid)
        self.assertEqual(refs, [])


# ── 3. read_fr_index graceful handling ────────────────────────────────────
class TestReadFrIndex(unittest.TestCase):
    def test_valid(self):
        cm = {"fr_index": {"FR-101": {"capability": "Prov", "cluster_id": "PR-01"}}}
        idx = read_fr_index(cm)
        self.assertEqual(idx["FR-101"]["cluster_id"], "PR-01")

    def test_malformed_returns_empty(self):
        self.assertEqual(read_fr_index({"fr_index": "oops"}), {})
        self.assertEqual(read_fr_index(None), {})  # type: ignore[arg-type]
        self.assertEqual(read_fr_index([]), {})  # type: ignore[arg-type]


# ── 4. Clean pass ──────────────────────────────────────────────────────────
class TestCleanPass(unittest.TestCase):
    def test_consistent_no_findings(self):
        fr_ids = ["FR-101", "FR-102"]
        seeded = {"FR-101", "FR-102"}
        fr_index = {
            "FR-101": {"capability": "Prov", "cluster_id": "PR-01"},
            "FR-102": {"capability": "Prov", "cluster_id": "PR-01"},
        }
        drafts = {"PR-01": ["FR-101", "FR-102"]}
        findings = check_traceability(fr_ids, seeded, fr_index, drafts)
        self.assertEqual(findings, [])
        self.assertEqual(exit_code_for(findings), 0)


# ── 5. orphan WARN ─────────────────────────────────────────────────────────
class TestOrphan(unittest.TestCase):
    def test_orphan_is_warn_not_block(self):
        fr_ids = ["FR-900"]            # no seed + not in fr_index
        findings = check_traceability(fr_ids, set(), {}, {})
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].level, "WARN")
        self.assertIn("orphan", findings[0].reason)
        self.assertEqual(exit_code_for(findings), 0)  # WARN is non-blocking


# ── 6. unmapped WARN ───────────────────────────────────────────────────────
class TestUnmapped(unittest.TestCase):
    def test_seed_but_not_in_index_is_warn(self):
        fr_ids = ["FR-500"]           # has seed but not in fr_index
        findings = check_traceability(fr_ids, {"FR-500"}, {}, {})
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].level, "WARN")
        self.assertIn("unmapped", findings[0].reason)
        self.assertEqual(exit_code_for(findings), 0)


# ── 7. mismatch BLOCK — direction (a): fr_index → draft missing ref ───────
class TestMismatchIndexToDraft(unittest.TestCase):
    def test_index_maps_but_draft_missing_ref(self):
        fr_ids = ["FR-101"]
        fr_index = {"FR-101": {"capability": "Prov", "cluster_id": "PR-01"}}
        drafts = {"PR-01": ["FR-999"]}  # PR-01 draft is missing FR-101
        findings = check_traceability(fr_ids, {"FR-101"}, fr_index, drafts)
        blocks = [f for f in findings if f.level == "BLOCK"]
        self.assertTrue(any("FR-101" in f.fr and "PR-01" in f.reason for f in blocks))
        self.assertEqual(exit_code_for(findings), 2)

    def test_no_draft_for_cluster_is_not_block(self):
        # if the mapped cluster's draft itself is missing, that's a partial
        # check — not a BLOCK
        fr_ids = ["FR-101"]
        fr_index = {"FR-101": {"capability": "Prov", "cluster_id": "PR-01"}}
        findings = check_traceability(fr_ids, {"FR-101"}, fr_index, {})
        self.assertFalse(any(f.level == "BLOCK" for f in findings))


# ── 8. mismatch BLOCK — direction (b): draft → index mismatch ─────────────
class TestMismatchDraftToIndex(unittest.TestCase):
    def test_draft_ref_maps_to_other_cluster(self):
        fr_index = {"FR-101": {"capability": "Prov", "cluster_id": "PR-01"}}
        drafts = {"PR-02": ["FR-101"]}  # draft PR-02 carries FR-101, index says PR-01
        findings = check_traceability([], set(), fr_index, drafts)
        blocks = [f for f in findings if f.level == "BLOCK"]
        self.assertTrue(blocks)
        self.assertTrue(any("PR-02" in f.reason and "PR-01" in f.reason for f in blocks))
        self.assertEqual(exit_code_for(findings), 2)

    def test_draft_ref_maps_nowhere(self):
        drafts = {"PR-01": ["FR-777"]}  # FR-777 not in fr_index
        findings = check_traceability([], set(), {}, drafts)
        blocks = [f for f in findings if f.level == "BLOCK"]
        self.assertTrue(any(f.fr == "FR-777" for f in blocks))
        self.assertEqual(exit_code_for(findings), 2)


# ── 9. graceful — empty/corrupt input ──────────────────────────────────────
class TestGraceful(unittest.TestCase):
    def test_all_empty_no_crash(self):
        self.assertEqual(check_traceability([], set(), {}, {}), [])
        self.assertEqual(
            check_traceability(None, None, None, None), []  # type: ignore[arg-type]
        )

    def test_report_renders(self):
        findings = [Finding("BLOCK", "FR-1", "x"), Finding("WARN", "FR-2", "y")]
        out = render_report(findings, product="acme")
        self.assertIn("BLOCK: 1", out)
        self.assertIn("WARN: 1", out)
        self.assertIn("FR-1", out)


# ── 10. End-to-end run_check (file I/O + exit code) ────────────────────────
class TestRunCheck(unittest.TestCase):
    def _setup(self, tmp: Path, *, fr_index: dict, draft_refs: dict,
               req_lines: list[str], seeds: dict | None = None) -> tuple[Path, Path, Path]:
        req = tmp / "requirements.md"
        req.write_text("\n".join(req_lines) + "\n", encoding="utf-8")
        cmap = tmp / "cluster_map.json"
        cmap.write_text(json.dumps({"fr_index": fr_index}), encoding="utf-8")
        if seeds is not None:
            seeds_lines: list[str] = []
            for fr, info in seeds.items():
                seeds_lines.append(f"{fr}:")
                for k, v in info.items():
                    seeds_lines.append(f"  {k}: {v}")
            (tmp / "requirements.seeds.yml").write_text(
                "\n".join(seeds_lines) + "\n", encoding="utf-8")
        drafts = tmp / "drafts"
        drafts.mkdir()
        for cid, refs in draft_refs.items():
            body = ['---', f'cluster_id: "{cid}"', "fr_refs:"]
            body += [f'  - "{fr}"' for fr in refs]
            body += ["---", ""]
            (drafts / f"cluster_{cid}.draft.md").write_text(
                "\n".join(body), encoding="utf-8")
        return req, cmap, drafts

    def test_clean_exit_0(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            req, cmap, drafts = self._setup(
                tmp,
                fr_index={"FR-101": {"capability": "P", "cluster_id": "PR-01"}},
                draft_refs={"PR-01": ["FR-101"]},
                req_lines=["| **FR-101** | n | c | P0 |"],
                seeds={"FR-101": {"capability": "P"}},
            )
            report = tmp / "out.md"
            # seeds_path omitted → automatically uses the sibling requirements.seeds.yml
            code, findings = run_check(req, cmap, drafts, report_path=report)
            self.assertEqual(code, 0)
            self.assertEqual(findings, [])
            self.assertTrue(report.is_file())

    def test_explicit_seeds_path(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            req, cmap, drafts = self._setup(
                tmp,
                fr_index={},
                draft_refs={},
                req_lines=["| **FR-500** | n | c | P0 |"],
            )
            # explicitly pass a seeds file at a separate location → unmapped WARN
            seeds_p = tmp / "custom.seeds.yml"
            seeds_p.write_text("FR-500:\n  capability: Billing\n", encoding="utf-8")
            code, findings = run_check(req, cmap, drafts, seeds_path=seeds_p)
            self.assertEqual(code, 0)
            self.assertTrue(any("unmapped" in f.reason for f in findings))

    def test_mismatch_exit_2(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            req, cmap, drafts = self._setup(
                tmp,
                fr_index={"FR-101": {"capability": "P", "cluster_id": "PR-01"}},
                draft_refs={"PR-01": ["FR-999"]},
                req_lines=["| **FR-101** | n | c | P0 |"],
                seeds={"FR-101": {"capability": "P"}},
            )
            code, findings = run_check(req, cmap, drafts)
            self.assertEqual(code, 2)
            self.assertTrue(any(f.level == "BLOCK" for f in findings))

    def test_orphan_exit_0(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            # no seeds file → FR-900 has no seed + not in fr_index → orphan WARN
            req, cmap, drafts = self._setup(
                tmp, fr_index={}, draft_refs={},
                req_lines=["| **FR-900** | n | c | P0 |"],
            )
            code, findings = run_check(req, cmap, drafts)
            self.assertEqual(code, 0)
            self.assertTrue(any(
                f.level == "WARN" and "orphan" in f.reason for f in findings))

    def test_missing_requirements_exit_1(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            cmap = tmp / "cluster_map.json"
            cmap.write_text("{}", encoding="utf-8")
            drafts = tmp / "drafts"
            drafts.mkdir()
            code, findings = run_check(tmp / "nope.md", cmap, drafts)
            self.assertEqual(code, 1)

    def test_malformed_cluster_map_graceful(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            req = tmp / "requirements.md"
            req.write_text("| **FR-1** | n | c | P0 |\n", encoding="utf-8")
            cmap = tmp / "cluster_map.json"
            cmap.write_text("{ this is not json", encoding="utf-8")
            drafts = tmp / "drafts"
            drafts.mkdir()
            # corrupt cluster_map → not exit 1 (graceful), yields orphan WARN → exit 0
            code, findings = run_check(req, cmap, drafts)
            self.assertEqual(code, 0)
            self.assertTrue(any(f.level == "WARN" for f in findings))

    def test_malformed_seeds_graceful(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            req, cmap, drafts = self._setup(
                tmp, fr_index={}, draft_refs={},
                req_lines=["| **FR-1** | n | c | P0 |"],
            )
            # corrupt seeds yml → absorbed as empty seeds, FR-1 becomes orphan WARN
            (tmp / "requirements.seeds.yml").write_text(
                "FR-1: [unclosed\n : : :", encoding="utf-8")
            code, findings = run_check(req, cmap, drafts)
            self.assertEqual(code, 0)
            self.assertTrue(any("orphan" in f.reason for f in findings))


# ── 11. Queue output — ssot_emit parser compatibility ─────────────────────
class TestQueueSsotCompatible(unittest.TestCase):
    """Whether the --queue/render_report header can be aggregated by the
    ssot_emit (_emit_common) parser."""

    def test_render_header_parses_block_warn(self):
        import _emit_common as C  # type: ignore
        findings = [
            Finding("BLOCK", "FR-1", "mismatch x"),
            Finding("WARN", "FR-2", "orphan y"),
            Finding("WARN", "FR-3", "unmapped z"),
        ]
        out = render_report(findings, product="acme")
        counts = C.parse_header_counts(out)
        self.assertEqual(counts.get("BLOCK"), 1)
        self.assertEqual(counts.get("WARN"), 2)

    def test_clean_header_parses_zeroes(self):
        import _emit_common as C  # type: ignore
        counts = C.parse_header_counts(render_report([]))
        self.assertEqual(counts.get("BLOCK"), 0)
        self.assertEqual(counts.get("WARN"), 0)

    def test_run_check_writes_queue_file(self):
        import _emit_common as C  # type: ignore
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            req = tmp / "requirements.md"
            req.write_text("| **FR-101** | n | c | P0 |\n", encoding="utf-8")
            cmap = tmp / "cluster_map.json"
            cmap.write_text(json.dumps(
                {"fr_index": {"FR-101": {"capability": "P", "cluster_id": "PR-01"}}}
            ), encoding="utf-8")
            drafts = tmp / "drafts"
            drafts.mkdir()
            # PR-01 draft is missing FR-101 → mismatch BLOCK
            (drafts / "cluster_PR-01.draft.md").write_text(
                '---\ncluster_id: "PR-01"\nfr_refs:\n  - "FR-999"\n---\n',
                encoding="utf-8")
            (tmp / "requirements.seeds.yml").write_text(
                "FR-101:\n  capability: P\n", encoding="utf-8")
            queue = tmp / "reports" / "fr-cluster-queue.md"
            code, findings = run_check(req, cmap, drafts, queue_path=queue)
            self.assertEqual(code, 2)
            self.assertTrue(queue.is_file())
            counts = C.parse_header_counts(queue.read_text(encoding="utf-8"))
            self.assertGreaterEqual(counts.get("BLOCK", 0), 1)


# ── Runner ──────────────────────────────────────────────────────────────
def _run() -> int:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in (
        TestParseFrIds,
        TestReadSeeds,
        TestParseClusterFrRefs,
        TestReadFrIndex,
        TestCleanPass,
        TestOrphan,
        TestUnmapped,
        TestMismatchIndexToDraft,
        TestMismatchDraftToIndex,
        TestGraceful,
        TestRunCheck,
        TestQueueSsotCompatible,
    ):
        suite.addTests(loader.loadTestsFromTestCase(cls))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    total = result.testsRun
    failed = len(result.failures) + len(result.errors)
    print(f"\nTotal {total} — PASS {total - failed} / FAIL {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(_run())
