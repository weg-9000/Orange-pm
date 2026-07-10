#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""render_transpose.py 단위 테스트 (stdlib unittest).

실행:
    python render_transpose_test.py
"""
from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

import render_transpose as rt  # noqa: E402


# ── 픽스처 헬퍼 ─────────────────────────────────────────────────────────────


def _make_cluster_draft(
    *,
    capability: str,
    cluster_id: str,
    cluster_name: str,
    targets: list[str],
    is_common_shell: bool = False,
    include_s1: bool = True,
    include_s2: bool = True,
    include_alpha: str | None = None,  # "api" / "db" / "migration" 또는 None
    s1_body: str = "정책 본문 — POL-001 기본 규칙.",
    s2_body: str = "화면 본문 — SCR-001 메인 화면.",
    alpha_body: str = "API 본문 — POST /v1/foo.",
) -> str:
    """cluster_draft 양식의 MD 문자열 생성."""
    targets_yaml = "\n".join(f"  - {t}" for t in targets)
    fm = (
        "---\n"
        f'title: "Cluster {capability} / {cluster_id} — {cluster_name}"\n'
        f"wo_id: G2-K-{cluster_id}\n"
        "type: cluster_draft\n"
        "layer: C\n"
        "version: 1.0\n"
        "last_updated: 2026-05-30\n"
        "cluster:\n"
        f'  capability: "{capability}"\n'
        f'  cluster_id: "{cluster_id}"\n'
        f'  cluster_name: "{cluster_name}"\n'
        "deliverable_targets:\n"
        f"{targets_yaml}\n"
        f"is_common_shell: {str(is_common_shell).lower()}\n"
        "---\n\n"
    )
    parts = [fm]
    if include_s1:
        parts.append(
            '::: {.panel section="§1 정책 결정 (D2 → 정책정의서로 transpose)"}\n'
            "## §1 정책 결정\n\n"
            "### §1-1 정책 범위\n\n"
            f"{s1_body}\n"
            ":::\n\n"
        )
    if include_s2:
        parts.append(
            '::: {.panel section="§2 화면 설계 (D3 → 화면설계서로 transpose)"}\n'
            "## §2 화면 설계\n\n"
            "### §2-1 주요 화면\n\n"
            f"{s2_body}\n"
            ":::\n\n"
        )
    if include_alpha:
        alpha_title = {
            "api": "§α API 스펙",
            "db": "§α DB 스키마",
            "migration": "§α 마이그레이션",
        }[include_alpha]
        parts.append(
            f'::: {{.panel section="{alpha_title}"}}\n'
            f"## {alpha_title}\n\n"
            f"{alpha_body}\n"
            ":::\n\n"
        )
    # §3 / §4 (publish 제외) — 어셈블 결과에 포함되지 않아야 함
    parts.append(
        '::: {.panel section="§3 데이터 / 의존성 (내부용, publish 제외)"}\n'
        "## §3 데이터\n\n"
        "내부용 데이터 — 절대 D2/D3 에 포함되면 안 됨 (SENTINEL_S3).\n"
        ":::\n\n"
    )
    parts.append(
        '::: {.panel section="§4 Open Questions (내부용, publish 제외)" '
        'style="tbd"}\n'
        "## §4 OQ\n\n"
        "OQ-001 SENTINEL_S4 — 절대 publish 안 됨.\n"
        ":::\n"
    )
    return "".join(parts)


def _write(tmpdir: Path, name: str, content: str) -> Path:
    p = tmpdir / name
    p.write_text(content, encoding="utf-8")
    return p


# ── T1: 단일 cluster D2 transpose ───────────────────────────────────────────


class T1SingleClusterD2(unittest.TestCase):
    def test_single_cluster_d2(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            draft = _write(
                tmpdir,
                "cluster_pricing_pr01.draft.md",
                _make_cluster_draft(
                    capability="Pricing",
                    cluster_id="PR-01",
                    cluster_name="PlanMatrix",
                    targets=["D2", "D3"],
                    s1_body="POL-101 기본 요금 정책 적용.",
                ),
            )
            result = rt.transpose([draft], "D2")
            # 챕터 panel 1개
            self.assertEqual(
                result.count("::: {.panel section="),
                1,
                f"D2 챕터 panel 1개 기대\n{result}",
            )
            # 챕터 타이틀 (publication-map.md §7 형식)
            self.assertIn(
                'section="§1 Pricing / PlanMatrix (PR-01)"', result
            )
            self.assertIn("## §1 Pricing / PlanMatrix (PR-01)", result)
            # §1 본문 포함
            self.assertIn("POL-101 기본 요금 정책 적용.", result)
            # §2 / §3 / §4 본문 미포함
            self.assertNotIn("화면 본문", result)
            self.assertNotIn("SENTINEL_S3", result)
            self.assertNotIn("SENTINEL_S4", result)
            # frontmatter 기본 (template 없음)
            self.assertIn("title: ", result)
            self.assertIn("type: policy", result)


# ── T2: 다중 cluster D2 — 정렬 검증 ─────────────────────────────────────────


class T2MultiClusterSorting(unittest.TestCase):
    def test_sort_by_capability_then_cluster_id_natural(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            # 의도적으로 무작위 순서로 입력
            drafts = [
                _write(
                    tmpdir,
                    "c_prov_pv10.draft.md",
                    _make_cluster_draft(
                        capability="Provisioning",
                        cluster_id="PV-10",
                        cluster_name="ResourceLimit",
                        targets=["D2"],
                        s1_body="PROV_PV10_BODY",
                    ),
                ),
                _write(
                    tmpdir,
                    "c_pricing_pr02.draft.md",
                    _make_cluster_draft(
                        capability="Pricing",
                        cluster_id="PR-02",
                        cluster_name="PriceCalc",
                        targets=["D2"],
                        s1_body="PRICING_PR02_BODY",
                    ),
                ),
                _write(
                    tmpdir,
                    "c_prov_pv02.draft.md",
                    _make_cluster_draft(
                        capability="Provisioning",
                        cluster_id="PV-02",
                        cluster_name="InstanceCatalog",
                        targets=["D2"],
                        s1_body="PROV_PV02_BODY",
                    ),
                ),
                _write(
                    tmpdir,
                    "c_pricing_pr01.draft.md",
                    _make_cluster_draft(
                        capability="Pricing",
                        cluster_id="PR-01",
                        cluster_name="PlanMatrix",
                        targets=["D2"],
                        s1_body="PRICING_PR01_BODY",
                    ),
                ),
            ]
            result = rt.transpose(drafts, "D2")
            # 기대 순서: Pricing PR-01 < Pricing PR-02 < Provisioning PV-02 < Provisioning PV-10
            i_pr01 = result.index("PRICING_PR01_BODY")
            i_pr02 = result.index("PRICING_PR02_BODY")
            i_pv02 = result.index("PROV_PV02_BODY")
            i_pv10 = result.index("PROV_PV10_BODY")
            self.assertLess(i_pr01, i_pr02, "PR-01 이 PR-02 보다 먼저")
            self.assertLess(i_pr02, i_pv02, "Pricing 이 Provisioning 보다 먼저")
            self.assertLess(
                i_pv02, i_pv10, "PV-02 가 PV-10 보다 먼저 (자연 정렬)"
            )
            # 챕터 번호 자동 매김 §1~§4
            self.assertIn("§1 Pricing / PlanMatrix (PR-01)", result)
            self.assertIn("§2 Pricing / PriceCalc (PR-02)", result)
            self.assertIn(
                "§3 Provisioning / InstanceCatalog (PV-02)", result
            )
            self.assertIn(
                "§4 Provisioning / ResourceLimit (PV-10)", result
            )


# ── T3: D3 with 공통 셸 — 부록 별도 ─────────────────────────────────────────


class T3D3WithCommonShell(unittest.TestCase):
    def test_d3_with_common_shell_appendix(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            cluster = _write(
                tmpdir,
                "cluster_pricing_pr01.draft.md",
                _make_cluster_draft(
                    capability="Pricing",
                    cluster_id="PR-01",
                    cluster_name="PlanMatrix",
                    targets=["D3"],
                    s2_body="MAIN_SCREEN_BODY — SCR-001 본문.",
                ),
            )
            shell = _write(
                tmpdir,
                "cluster_common_navshell.draft.md",
                _make_cluster_draft(
                    capability="Common",
                    cluster_id="COMMON-01",
                    cluster_name="NavShell",
                    targets=["D3"],
                    is_common_shell=True,
                    s2_body="COMMON_NAVSHELL_BODY — 글로벌 nav.",
                ),
            )
            shell2 = _write(
                tmpdir,
                "cluster_common_authflow.draft.md",
                _make_cluster_draft(
                    capability="Common",
                    cluster_id="COMMON-02",
                    cluster_name="AuthFlow",
                    targets=["D3"],
                    is_common_shell=True,
                    s2_body="COMMON_AUTH_BODY — 로그인 흐름.",
                ),
            )
            result = rt.transpose(
                [cluster, shell, shell2],
                "D3",
                common_shell_clusters=[shell, shell2],
            )
            # 일반 챕터: PR-01 만 (shell 은 is_common_shell 로 제외)
            self.assertIn("§1 Pricing / PlanMatrix (PR-01)", result)
            self.assertIn("MAIN_SCREEN_BODY", result)
            # 부록 별도
            self.assertIn('section="§부록 A — 공통 셸"', result)
            self.assertIn("부록 A.1 NavShell (COMMON-01)", result)
            self.assertIn("부록 A.2 AuthFlow (COMMON-02)", result)
            self.assertIn("COMMON_NAVSHELL_BODY", result)
            self.assertIn("COMMON_AUTH_BODY", result)
            # 일반 챕터로는 NavShell 이 안 잡혔어야 함 — 부록 panel
            # (section= 속성 + 본문 h3) 에만 등장
            # 일반 챕터 section= 속성에는 NavShell 없음
            self.assertNotIn(
                '"§1 Common / NavShell', result,
                "공통 셸이 일반 챕터로 잘못 분류됨",
            )
            self.assertNotIn(
                '"§2 Common / AuthFlow', result,
                "공통 셸이 일반 챕터로 잘못 분류됨",
            )


# ── T4: deliverable_targets 에 D2 미포함 → 제외 ─────────────────────────────


class T4FilterByTarget(unittest.TestCase):
    def test_filter_when_d2_not_in_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            # 1개는 D2, 1개는 D3 만
            d1 = _write(
                tmpdir,
                "c1.draft.md",
                _make_cluster_draft(
                    capability="Pricing",
                    cluster_id="PR-01",
                    cluster_name="PlanMatrix",
                    targets=["D2"],
                    s1_body="INCLUDED_BODY",
                ),
            )
            d2 = _write(
                tmpdir,
                "c2.draft.md",
                _make_cluster_draft(
                    capability="Pricing",
                    cluster_id="PR-02",
                    cluster_name="Other",
                    targets=["D3"],  # D2 없음
                    s1_body="EXCLUDED_BODY",
                ),
            )
            result = rt.transpose([d1, d2], "D2")
            self.assertIn("INCLUDED_BODY", result)
            self.assertNotIn("EXCLUDED_BODY", result)
            self.assertEqual(result.count("::: {.panel section="), 1)


# ── T5: §1 없는 cluster → 경고 + skip ──────────────────────────────────────


class T5MissingSection(unittest.TestCase):
    def test_missing_section_warned_and_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            d_ok = _write(
                tmpdir,
                "ok.draft.md",
                _make_cluster_draft(
                    capability="Pricing",
                    cluster_id="PR-01",
                    cluster_name="PlanMatrix",
                    targets=["D2"],
                    s1_body="OK_BODY",
                ),
            )
            d_bad = _write(
                tmpdir,
                "bad.draft.md",
                _make_cluster_draft(
                    capability="Pricing",
                    cluster_id="PR-02",
                    cluster_name="NoS1",
                    targets=["D2"],
                    include_s1=False,  # §1 없음
                    s1_body="UNUSED",
                ),
            )
            buf = io.StringIO()
            with redirect_stderr(buf):
                result = rt.transpose([d_ok, d_bad], "D2")
            stderr_text = buf.getvalue()
            self.assertIn("PR-02", stderr_text)
            self.assertIn("§1", stderr_text)
            # 정상 cluster 는 어셈블 결과에 포함
            self.assertIn("OK_BODY", result)
            self.assertIn("§1 Pricing / PlanMatrix (PR-01)", result)
            # bad cluster 챕터는 없음
            self.assertNotIn("NoS1", result)
            self.assertEqual(result.count("::: {.panel section="), 1)

    def test_all_missing_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            d = _write(
                tmpdir,
                "bad.draft.md",
                _make_cluster_draft(
                    capability="Pricing",
                    cluster_id="PR-99",
                    cluster_name="X",
                    targets=["D2"],
                    include_s1=False,
                ),
            )
            buf = io.StringIO()
            with redirect_stderr(buf):
                with self.assertRaises(rt.TransposeError):
                    rt.transpose([d], "D2")


# ── T6: target_template frontmatter 적용 ────────────────────────────────────


class T6TargetTemplate(unittest.TestCase):
    def test_target_template_frontmatter_applied(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            # 가짜 template
            tpl = _write(
                tmpdir,
                "D2_policy_tpl.md",
                "---\n"
                'title: "[정책정의서] DBaaS"\n'
                "type: policy\n"
                "layer: C\n"
                "version: 1.2\n"
                "last_updated: 2020-01-01\n"
                "publication:\n"
                "  header:\n"
                "    style: info\n"
                "    body: |\n"
                "      **테스트 정책서 골격**\n"
                "---\n\n"
                "기존 본문 (사용 안 됨).\n",
            )
            d = _write(
                tmpdir,
                "c1.draft.md",
                _make_cluster_draft(
                    capability="Pricing",
                    cluster_id="PR-01",
                    cluster_name="PlanMatrix",
                    targets=["D2"],
                    s1_body="BODY",
                ),
            )
            result = rt.transpose([d], "D2", target_template=tpl)
            # template 의 title 보존 (yaml.safe_dump 가 '' 또는 "" 사용)
            self.assertIn("[정책정의서] DBaaS", result)
            self.assertTrue(
                result.startswith("---\n") and "title:" in result.split("---")[1],
                "frontmatter 정상 생성",
            )
            # last_updated 가 갱신됨 (2020-01-01 이 아님)
            self.assertNotIn("2020-01-01", result)
            self.assertIn("last_updated:", result)
            # transposed_at / transposed_from 메타 추가
            self.assertIn("transposed_from:", result)
            self.assertIn("transposed_at:", result)
            # template 의 publication.header 도 보존
            self.assertIn("테스트 정책서 골격", result)


# ── T7: Dα 타입 분기 ─────────────────────────────────────────────────────────


class T7DalphaTypes(unittest.TestCase):
    def test_da_api_extracts_alpha_api_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            # API 만
            d_api = _write(
                tmpdir,
                "c_api.draft.md",
                _make_cluster_draft(
                    capability="Pricing",
                    cluster_id="PR-01",
                    cluster_name="PlanMatrix",
                    targets=["Da_api"],
                    include_alpha="api",
                    alpha_body="API_BODY POST /v1/plans.",
                ),
            )
            # DB 만 (Da_api 대상 아님)
            d_db = _write(
                tmpdir,
                "c_db.draft.md",
                _make_cluster_draft(
                    capability="Pricing",
                    cluster_id="PR-02",
                    cluster_name="PlanDB",
                    targets=["Da_db"],
                    include_alpha="db",
                    alpha_body="DB_BODY plan_table.",
                ),
            )
            result = rt.transpose([d_api, d_db], "Da_api")
            self.assertIn("API_BODY", result)
            self.assertNotIn("DB_BODY", result)

    def test_template_alpha_labels_extracted(self):
        """cluster-draft.md 의 실제 §α 라벨(§α-API / §α-DB / §α-MIG)이 deliverable
        별로 추출되는지 — 템플릿 ↔ render_transpose 계약 드리프트 가드."""
        cases = [
            ("Da_api", '§α-API API 스펙 (Dα → API 스펙으로 transpose · 선택)', "ALPHA_API_BODY"),
            ("Da_db", '§α-DB DB 스키마 (Dα → DB 스키마로 transpose · 선택)', "ALPHA_DB_BODY"),
            ("Da_migration", '§α-MIG 마이그레이션 (Dα → 마이그레이션 플랜으로 transpose · 선택)', "ALPHA_MIG_BODY"),
        ]
        for deliverable, label, body in cases:
            with tempfile.TemporaryDirectory() as tmp:
                tmpdir = Path(tmp)
                draft = (
                    "---\n"
                    'title: "Cluster Pricing / PR-01 — 요금"\n'
                    "wo_id: G2-K-PR-01\ntype: cluster_draft\nlayer: C\n"
                    "cluster:\n  capability: \"Pricing\"\n  cluster_id: \"PR-01\"\n"
                    "  cluster_name: \"요금\"\n"
                    f"deliverable_targets:\n  - {deliverable}\n---\n\n"
                    f'::: {{.panel section="{label}"}}\n## {label}\n\n{body}\n:::\n'
                )
                p = _write(tmpdir, "cluster_pr01.draft.md", draft)
                result = rt.transpose([p], deliverable)
                self.assertIn(body, result, f"{deliverable}: {label} 추출 실패")


# ── T8: CLI main() smoke ────────────────────────────────────────────────────


class T8CLI(unittest.TestCase):
    def test_cli_smoke(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            d = _write(
                tmpdir,
                "c.draft.md",
                _make_cluster_draft(
                    capability="Pricing",
                    cluster_id="PR-01",
                    cluster_name="PlanMatrix",
                    targets=["D2"],
                    s1_body="CLI_BODY",
                ),
            )
            out = tmpdir / "out" / "D2.md"
            rc = rt.main(
                [
                    "--cluster-drafts",
                    str(d),
                    "--deliverable",
                    "D2",
                    "--output",
                    str(out),
                ]
            )
            self.assertEqual(rc, 0)
            self.assertTrue(out.exists())
            content = out.read_text(encoding="utf-8")
            self.assertIn("CLI_BODY", content)

    def test_cli_no_match_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            d = _write(
                tmpdir,
                "c.draft.md",
                _make_cluster_draft(
                    capability="Pricing",
                    cluster_id="PR-01",
                    cluster_name="X",
                    targets=["D3"],  # D2 아님
                    s1_body="X",
                ),
            )
            out = tmpdir / "out" / "D2.md"
            buf = io.StringIO()
            with redirect_stderr(buf):
                rc = rt.main(
                    [
                        "--cluster-drafts",
                        str(d),
                        "--deliverable",
                        "D2",
                        "--output",
                        str(out),
                    ]
                )
            self.assertEqual(rc, 2)
            self.assertFalse(out.exists())


# ── 헬퍼 — 정렬 직접 검증 ──────────────────────────────────────────────────


class TSortHelper(unittest.TestCase):
    def test_natural_key_pr_order(self):
        ids = ["PR-10", "PR-01", "PR-2", "PR-09"]
        ids.sort(key=rt._natural_key)
        self.assertEqual(ids, ["PR-01", "PR-2", "PR-09", "PR-10"])


# ── P3-1: D1 capability group-by 파생 뷰 (DEC-C) ────────────────────────────


class TP3FrCapabilityView(unittest.TestCase):
    def test_grouping_and_anchor(self):
        fr_index = {
            "FR-101": {"capability": "Pricing", "cluster_id": "PR-01"},
            "FR-103": {"capability": "Pricing", "cluster_id": "PR-01"},
            "FR-201": {"capability": "Provisioning", "cluster_id": "PV-02"},
        }
        out = rt.render_fr_capability_view(fr_index)
        # 패널 wrapper + SSoT 출처 명시
        self.assertIn('::: {.panel section="§D1 capability별 FR 묶음', out)
        self.assertIn("fr_index", out)
        # capability 헤더 그룹
        self.assertIn("### Pricing", out)
        self.assertIn("### Provisioning", out)
        # FR → 기능정의서(cluster_id) 앵커
        self.assertIn("**FR-101** → [기능정의서 PR-01](#PR-01)", out)
        self.assertIn("**FR-201** → [기능정의서 PV-02](#PV-02)", out)
        # 같은 capability 의 FR 둘 다 동일 그룹 아래
        i_cap = out.index("### Pricing")
        self.assertIn("FR-101", out[i_cap:])
        self.assertIn("FR-103", out[i_cap:])

    def test_deterministic_order(self):
        # 입력 순서를 섞어도 출력은 결정적 (capability 알파벳 → FR 자연 순)
        # FR-1 / FR-2 자연 순 + Pricing 이 Provisioning 보다 먼저
        fr_index = {
            "FR-10": {"capability": "Provisioning", "cluster_id": "PV-01"},
            "FR-2": {"capability": "Pricing", "cluster_id": "PR-01"},
            "FR-1": {"capability": "Pricing", "cluster_id": "PR-01"},
        }
        out = rt.render_fr_capability_view(fr_index)
        self.assertLess(out.index("### Pricing"), out.index("### Provisioning"))
        self.assertLess(out.index("FR-1**"), out.index("FR-2**"))
        # 멱등 (동일 입력 → 동일 출력)
        self.assertEqual(out, rt.render_fr_capability_view(fr_index))

    def test_empty_input(self):
        out = rt.render_fr_capability_view({})
        self.assertIn('::: {.panel section="§D1 capability별 FR 묶음', out)
        self.assertIn("매핑된 FR 없음", out)
        # 패널이 정상적으로 닫힘
        self.assertTrue(out.rstrip().endswith(":::"))

    def test_unmapped_cluster(self):
        out = rt.render_fr_capability_view(
            {"FR-9": {"capability": "Misc", "cluster_id": ""}}
        )
        self.assertIn("**FR-9** → (cluster 미매핑)", out)


# ── P3-2: 횡단 관심사 매트릭스 파생 뷰 (DEC-F) ──────────────────────────────


class TP3CrossCuttingMatrix(unittest.TestCase):
    def test_multi_module_matrix(self):
        # 일반성 검증 — 이메일 아닌 모듈도 동일하게 동작
        module_index = {
            "DOC-EMAIL": [
                {
                    "cluster_id": "PR-02",
                    "capability": "Backup",
                    "source": "NODE-B",
                    "via": "references",
                    "section": "§2",
                },
                {
                    "cluster_id": "PR-01",
                    "capability": "Account",
                    "source": "NODE-A",
                    "via": "references",
                    "section": "§1",
                },
            ],
            "DOC-LOG": [
                {
                    "cluster_id": "PV-01",
                    "capability": "Provisioning",
                    "source": "NODE-C",
                    "via": "includes",
                    "section": None,
                },
            ],
        }
        out = rt.render_cross_cutting_matrix(module_index)
        self.assertIn('::: {.panel section="§횡단 관심사 매트릭스', out)
        self.assertIn("module_index", out)
        # 모듈별 헤더 (docId 알파벳 순: DOC-EMAIL < DOC-LOG)
        self.assertLess(out.index("### DOC-EMAIL"), out.index("### DOC-LOG"))
        # 테이블 헤더
        self.assertIn(
            "| capability | cluster_id | source | via | section |", out
        )
        # 행 내용 + None section → "—"
        self.assertIn("| Provisioning | PV-01 | NODE-C | includes | — |", out)
        self.assertIn("| Account | PR-01 | NODE-A | references | §1 |", out)
        # 모듈 내 행 결정적 정렬 (Account < Backup)
        email_block = out[out.index("### DOC-EMAIL"):out.index("### DOC-LOG")]
        self.assertLess(
            email_block.index("Account"), email_block.index("Backup")
        )

    def test_node_titles_mapping(self):
        out = rt.render_cross_cutting_matrix(
            {"DOC-EMAIL": [
                {"cluster_id": "PR-01", "capability": "A",
                 "source": "N1", "via": "references", "section": "§1"}
            ]},
            node_titles={"DOC-EMAIL": "이메일·SMS 발송 모듈"},
        )
        self.assertIn("### 이메일·SMS 발송 모듈 (DOC-EMAIL)", out)

    def test_empty_input(self):
        out = rt.render_cross_cutting_matrix({})
        self.assertIn('::: {.panel section="§횡단 관심사 매트릭스', out)
        self.assertIn("횡단 참조 모듈 없음", out)
        self.assertTrue(out.rstrip().endswith(":::"))

    def test_deterministic(self):
        module_index = {
            "DOC-LOG": [
                {"cluster_id": "PV-01", "capability": "P",
                 "source": "N", "via": "includes", "section": None}
            ],
            "DOC-EMAIL": [
                {"cluster_id": "PR-01", "capability": "A",
                 "source": "N", "via": "references", "section": "§1"}
            ],
        }
        out1 = rt.render_cross_cutting_matrix(module_index)
        out2 = rt.render_cross_cutting_matrix(module_index)
        self.assertEqual(out1, out2)


# ── T9: D3 화면 단위 챕터 (split-deliverable) ───────────────────────────────


def _d3_screen_draft(
    *, cluster_id: str, cluster_name: str, capability: str,
    related: list[str], s2_inner: str,
) -> str:
    rs = "\n".join(f"  - {s}" for s in related)
    return (
        "---\n"
        f'title: "Cluster {capability} / {cluster_id} — {cluster_name}"\n'
        f"wo_id: G2-K-{cluster_id}\ntype: cluster_draft\nlayer: C\n"
        "cluster:\n"
        f'  capability: "{capability}"\n  cluster_id: "{cluster_id}"\n'
        f'  cluster_name: "{cluster_name}"\n'
        "deliverable_targets:\n  - D3\n"
        f"related_screens:\n{rs}\n"
        "is_common_shell: false\n---\n\n"
        '::: {.panel section="§2 화면 설계"}\n## §2 화면 설계\n\n'
        f"{s2_inner}\n:::\n"
    )


class T9D3ScreenChapters(unittest.TestCase):
    def test_screen_tagged_headings_become_chapters(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            d = _write(
                tmpdir, "c.draft.md",
                _d3_screen_draft(
                    cluster_id="PR-01", cluster_name="PlanMatrix",
                    capability="Pricing", related=["SCR-002", "SCR-001"],
                    s2_inner=(
                        "### §2-1 목록 화면 (SCR-001)\n\nLIST_BODY 목록.\n\n"
                        "### §2-2 생성 화면 (SCR-002)\n\nCREATE_BODY 생성.\n"
                    ),
                ),
            )
            result = rt.transpose([d], "D3")
            # 화면 인덱스 패널
            self.assertIn('section="§화면 인덱스"', result)
            self.assertIn("| SCR-001 | 목록 화면 |", result)
            self.assertIn("| SCR-002 | 생성 화면 |", result)
            # 화면 단위 챕터 (Screen ID 자연순: SCR-001 < SCR-002)
            self.assertIn('section="§1 목록 화면 (SCR-001)"', result)
            self.assertIn('section="§2 생성 화면 (SCR-002)"', result)
            self.assertLess(result.index("LIST_BODY"), result.index("CREATE_BODY"))
            # cluster 단위 챕터 panel 제목은 등장하지 않음 (화면 단위로 분해됨).
            # cluster 문자열은 화면 인덱스 '출처' 열에만 나타난다.
            self.assertNotIn('section="§1 Pricing / PlanMatrix (PR-01)"', result)
            self.assertNotIn("## §1 Pricing / PlanMatrix (PR-01)", result)

    def test_no_screen_tagging_falls_back_to_cluster_chapter(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            d = _write(
                tmpdir, "c.draft.md",
                _d3_screen_draft(
                    cluster_id="PR-01", cluster_name="PlanMatrix",
                    capability="Pricing", related=[],
                    s2_inner="### §2-1 주요 화면\n\nNO_TAG_BODY 본문.\n",
                ),
            )
            buf = io.StringIO()
            with redirect_stderr(buf):
                result = rt.transpose([d], "D3")
            # fallback WARN
            self.assertIn("화면 단위 분해 불가", buf.getvalue())
            # cluster 단위 챕터로 어셈블
            self.assertIn("§1 Pricing / PlanMatrix (PR-01)", result)
            self.assertIn("NO_TAG_BODY", result)
            self.assertNotIn('section="§화면 인덱스"', result)

    def test_common_shell_still_routed_to_appendix_in_screen_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            main = _write(
                tmpdir, "c_main.draft.md",
                _d3_screen_draft(
                    cluster_id="PR-01", cluster_name="PlanMatrix",
                    capability="Pricing", related=["SCR-001"],
                    s2_inner="### §2-1 목록 (SCR-001)\n\nMAIN_BODY.\n",
                ),
            )
            shell = _write(
                tmpdir, "c_shell.draft.md",
                _make_cluster_draft(
                    capability="Common", cluster_id="COMMON-01",
                    cluster_name="NavShell", targets=["D3"],
                    is_common_shell=True, s2_body="SHELL_NAV_BODY.",
                ),
            )
            result = rt.transpose(
                [main, shell], "D3", common_shell_clusters=[shell]
            )
            # 화면 챕터 + 부록 공존, shell 은 일반 챕터로 안 잡힘
            self.assertIn('section="§1 목록 (SCR-001)"', result)
            self.assertIn("§부록 A — 공통 셸", result)
            self.assertIn("SHELL_NAV_BODY", result)
            self.assertNotIn("(COMMON-01)\"", result.split("§부록")[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
