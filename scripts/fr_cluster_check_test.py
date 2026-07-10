#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fr_cluster_check.py 테스트 (P4, docs/fr-cluster-alignment.md).

stdlib unittest. clean pass / orphan WARN / unmapped WARN /
mismatch BLOCK(양방향) / 종료 코드 / 손상 입력 graceful 커버.
씨앗은 사이드카 requirements.seeds.yml 에서 읽는다(인라인 태그 아님).
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


# ── 1. requirements FR universe 파싱 (씨앗 정보 없음) ─────────────────────
class TestParseFrIds(unittest.TestCase):
    def test_parses_leading_fr_universe(self):
        md = (
            "| **FR-101** | 명칭 | 내용 | P0 |\n"
            "| **FR-102** | 명칭 | 내용 | P1 |\n"
            "본문에서 FR-999 언급은 행 주체가 아님\n"
        )
        ids = parse_fr_ids(md)
        self.assertEqual(ids, ["FR-101", "FR-102"])  # 순서 보존, 중복 제거

    def test_dedupes_repeated_fr(self):
        md = (
            "| FR-101 | a | b | P0 |\n"
            "| FR-101 | a | c | P0 |\n"
        )
        self.assertEqual(parse_fr_ids(md), ["FR-101"])

    def test_non_string_graceful(self):
        self.assertEqual(parse_fr_ids(None), [])  # type: ignore[arg-type]


# ── 1b. 사이드카 seeds yml 파싱 ───────────────────────────────────────────
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
                "  capability: ''\n"      # 빈 capability → 씨앗 아님
                "FR-103:\n"
                "  cluster_hint: X\n",    # capability 키 없음 → 씨앗 아님
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


# ── 2. cluster draft fr_refs 파싱 ────────────────────────────────────────
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
            "본문\n"
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


# ── 3. read_fr_index graceful ────────────────────────────────────────────
class TestReadFrIndex(unittest.TestCase):
    def test_valid(self):
        cm = {"fr_index": {"FR-101": {"capability": "Prov", "cluster_id": "PR-01"}}}
        idx = read_fr_index(cm)
        self.assertEqual(idx["FR-101"]["cluster_id"], "PR-01")

    def test_malformed_returns_empty(self):
        self.assertEqual(read_fr_index({"fr_index": "oops"}), {})
        self.assertEqual(read_fr_index(None), {})  # type: ignore[arg-type]
        self.assertEqual(read_fr_index([]), {})  # type: ignore[arg-type]


# ── 4. clean pass ────────────────────────────────────────────────────────
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


# ── 5. orphan WARN ───────────────────────────────────────────────────────
class TestOrphan(unittest.TestCase):
    def test_orphan_is_warn_not_block(self):
        fr_ids = ["FR-900"]            # 씨앗 없음 + fr_index 부재
        findings = check_traceability(fr_ids, set(), {}, {})
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].level, "WARN")
        self.assertIn("orphan", findings[0].reason)
        self.assertEqual(exit_code_for(findings), 0)  # WARN 비차단


# ── 6. unmapped WARN ─────────────────────────────────────────────────────
class TestUnmapped(unittest.TestCase):
    def test_seed_but_not_in_index_is_warn(self):
        fr_ids = ["FR-500"]           # 씨앗 있으나 fr_index 부재
        findings = check_traceability(fr_ids, {"FR-500"}, {}, {})
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].level, "WARN")
        self.assertIn("unmapped", findings[0].reason)
        self.assertEqual(exit_code_for(findings), 0)


# ── 7. mismatch BLOCK — 방향 (a): fr_index → draft 누락 ──────────────────
class TestMismatchIndexToDraft(unittest.TestCase):
    def test_index_maps_but_draft_missing_ref(self):
        fr_ids = ["FR-101"]
        fr_index = {"FR-101": {"capability": "Prov", "cluster_id": "PR-01"}}
        drafts = {"PR-01": ["FR-999"]}  # PR-01 draft 가 FR-101 누락
        findings = check_traceability(fr_ids, {"FR-101"}, fr_index, drafts)
        blocks = [f for f in findings if f.level == "BLOCK"]
        self.assertTrue(any("FR-101" in f.fr and "PR-01" in f.reason for f in blocks))
        self.assertEqual(exit_code_for(findings), 2)

    def test_no_draft_for_cluster_is_not_block(self):
        # 매핑된 cluster 의 draft 자체가 없으면 부분 검증 — BLOCK 아님
        fr_ids = ["FR-101"]
        fr_index = {"FR-101": {"capability": "Prov", "cluster_id": "PR-01"}}
        findings = check_traceability(fr_ids, {"FR-101"}, fr_index, {})
        self.assertFalse(any(f.level == "BLOCK" for f in findings))


# ── 8. mismatch BLOCK — 방향 (b): draft → index 불일치 ───────────────────
class TestMismatchDraftToIndex(unittest.TestCase):
    def test_draft_ref_maps_to_other_cluster(self):
        fr_index = {"FR-101": {"capability": "Prov", "cluster_id": "PR-01"}}
        drafts = {"PR-02": ["FR-101"]}  # draft PR-02 가 FR-101 실음, index 는 PR-01
        findings = check_traceability([], set(), fr_index, drafts)
        blocks = [f for f in findings if f.level == "BLOCK"]
        self.assertTrue(blocks)
        self.assertTrue(any("PR-02" in f.reason and "PR-01" in f.reason for f in blocks))
        self.assertEqual(exit_code_for(findings), 2)

    def test_draft_ref_maps_nowhere(self):
        drafts = {"PR-01": ["FR-777"]}  # fr_index 에 FR-777 없음
        findings = check_traceability([], set(), {}, drafts)
        blocks = [f for f in findings if f.level == "BLOCK"]
        self.assertTrue(any(f.fr == "FR-777" for f in blocks))
        self.assertEqual(exit_code_for(findings), 2)


# ── 9. graceful — 빈/손상 입력 ───────────────────────────────────────────
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


# ── 10. End-to-end run_check (파일 I/O + 종료 코드) ──────────────────────
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
            # seeds_path 생략 → requirements 형제 requirements.seeds.yml 자동 사용
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
            # 별도 위치의 seeds 파일을 명시 전달 → unmapped WARN
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
            # seeds 파일 없음 → FR-900 씨앗 없음 + fr_index 부재 → orphan WARN
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
            # 손상 cluster_map → exit 1 아님(graceful), orphan WARN 산출 → exit 0
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
            # 손상 seeds yml → 빈 seeds 로 흡수, FR-1 은 orphan WARN
            (tmp / "requirements.seeds.yml").write_text(
                "FR-1: [unclosed\n : : :", encoding="utf-8")
            code, findings = run_check(req, cmap, drafts)
            self.assertEqual(code, 0)
            self.assertTrue(any("orphan" in f.reason for f in findings))


# ── 11. 큐 출력 — ssot_emit 파서 호환성 ───────────────────────────────────
class TestQueueSsotCompatible(unittest.TestCase):
    """--queue/render_report 헤더가 ssot_emit(_emit_common) 파서로 집계 가능한지."""

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
            # PR-01 draft 가 FR-101 누락 → mismatch BLOCK
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


# ── 실행기 ───────────────────────────────────────────────────────────────
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
    print(f"\n총 {total}개 — PASS {total - failed} / FAIL {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(_run())
