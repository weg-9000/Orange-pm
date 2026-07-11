#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""render_transpose.py unit tests (stdlib unittest).

Run:
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


# ── fixture helpers ─────────────────────────────────────────────────────────


def _make_cluster_draft(
    *,
    capability: str,
    cluster_id: str,
    cluster_name: str,
    targets: list[str],
    is_common_shell: bool = False,
    include_s1: bool = True,
    include_s2: bool = True,
    include_alpha: str | None = None,  # "api" / "db" / "migration" or None
    s1_body: str = "policy body — POL-001 base rule.",
    s2_body: str = "screen body — SCR-001 main screen.",
    alpha_body: str = "API body — POST /v1/foo.",
) -> str:
    """Build a cluster_draft style MD string."""
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
            '::: {.panel section="§1 Policy Decisions (D2 → transpose to policy definition)"}\n'
            "## §1 Policy Decisions\n\n"
            "### §1-1 Policy scope\n\n"
            f"{s1_body}\n"
            ":::\n\n"
        )
    if include_s2:
        parts.append(
            '::: {.panel section="§2 Screen Design (D3 → transpose to screen design spec)"}\n'
            "## §2 Screen Design\n\n"
            "### §2-1 Main screens\n\n"
            f"{s2_body}\n"
            ":::\n\n"
        )
    if include_alpha:
        alpha_title = {
            "api": "§α API Spec",
            "db": "§α DB Schema",
            "migration": "§α Migration",
        }[include_alpha]
        parts.append(
            f'::: {{.panel section="{alpha_title}"}}\n'
            f"## {alpha_title}\n\n"
            f"{alpha_body}\n"
            ":::\n\n"
        )
    # §3 / §4 (excluded from publish) — must not appear in the assembled result
    parts.append(
        '::: {.panel section="§3 Data / Dependencies (internal, excluded from publish)"}\n'
        "## §3 Data\n\n"
        "internal data — must never appear in D2/D3 (SENTINEL_S3).\n"
        ":::\n\n"
    )
    parts.append(
        '::: {.panel section="§4 Open Questions (internal, excluded from publish)" '
        'style="tbd"}\n'
        "## §4 OQ\n\n"
        "OQ-001 SENTINEL_S4 — never published.\n"
        ":::\n"
    )
    return "".join(parts)


def _write(tmpdir: Path, name: str, content: str) -> Path:
    p = tmpdir / name
    p.write_text(content, encoding="utf-8")
    return p


# ── T1: single-cluster D2 transpose ─────────────────────────────────────────


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
                    s1_body="POL-101 base pricing policy applies.",
                ),
            )
            result = rt.transpose([draft], "D2")
            # 1 chapter panel
            self.assertEqual(
                result.count("::: {.panel section="),
                1,
                f"expected 1 D2 chapter panel\n{result}",
            )
            # chapter title (publication-map.md §7 format)
            self.assertIn(
                'section="§1 Pricing / PlanMatrix (PR-01)"', result
            )
            self.assertIn("## §1 Pricing / PlanMatrix (PR-01)", result)
            # §1 body included
            self.assertIn("POL-101 base pricing policy applies.", result)
            # §2 / §3 / §4 bodies excluded
            self.assertNotIn("screen body", result)
            self.assertNotIn("SENTINEL_S3", result)
            self.assertNotIn("SENTINEL_S4", result)
            # default frontmatter (no template)
            self.assertIn("title: ", result)
            self.assertIn("type: policy", result)


# ── T2: multi-cluster D2 — sort verification ────────────────────────────────


class T2MultiClusterSorting(unittest.TestCase):
    def test_sort_by_capability_then_cluster_id_natural(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            # intentionally shuffled input order
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
            # expected order: Pricing PR-01 < Pricing PR-02 < Provisioning PV-02 < Provisioning PV-10
            i_pr01 = result.index("PRICING_PR01_BODY")
            i_pr02 = result.index("PRICING_PR02_BODY")
            i_pv02 = result.index("PROV_PV02_BODY")
            i_pv10 = result.index("PROV_PV10_BODY")
            self.assertLess(i_pr01, i_pr02, "PR-01 before PR-02")
            self.assertLess(i_pr02, i_pv02, "Pricing before Provisioning")
            self.assertLess(
                i_pv02, i_pv10, "PV-02 before PV-10 (natural sort)"
            )
            # chapter numbers auto-assigned §1~§4
            self.assertIn("§1 Pricing / PlanMatrix (PR-01)", result)
            self.assertIn("§2 Pricing / PriceCalc (PR-02)", result)
            self.assertIn(
                "§3 Provisioning / InstanceCatalog (PV-02)", result
            )
            self.assertIn(
                "§4 Provisioning / ResourceLimit (PV-10)", result
            )


# ── T3: D3 with common shell — separate appendix ────────────────────────────


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
                    s2_body="MAIN_SCREEN_BODY — SCR-001 body.",
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
                    s2_body="COMMON_NAVSHELL_BODY — global nav.",
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
                    s2_body="COMMON_AUTH_BODY — login flow.",
                ),
            )
            result = rt.transpose(
                [cluster, shell, shell2],
                "D3",
                common_shell_clusters=[shell, shell2],
            )
            # normal chapters: PR-01 only (shells excluded via is_common_shell)
            self.assertIn("§1 Pricing / PlanMatrix (PR-01)", result)
            self.assertIn("MAIN_SCREEN_BODY", result)
            # appendix separate
            self.assertIn('section="§Appendix A — Common Shell"', result)
            self.assertIn("Appendix A.1 NavShell (COMMON-01)", result)
            self.assertIn("Appendix A.2 AuthFlow (COMMON-02)", result)
            self.assertIn("COMMON_NAVSHELL_BODY", result)
            self.assertIn("COMMON_AUTH_BODY", result)
            # NavShell must not have been captured as a normal chapter —
            # it appears only in the appendix panel (section= attribute + body h3)
            self.assertNotIn(
                '"§1 Common / NavShell', result,
                "common shell misclassified as a normal chapter",
            )
            self.assertNotIn(
                '"§2 Common / AuthFlow', result,
                "common shell misclassified as a normal chapter",
            )


# ── T4: D2 not in deliverable_targets → excluded ────────────────────────────


class T4FilterByTarget(unittest.TestCase):
    def test_filter_when_d2_not_in_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            # one targets D2, one targets D3 only
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
                    targets=["D3"],  # no D2
                    s1_body="EXCLUDED_BODY",
                ),
            )
            result = rt.transpose([d1, d2], "D2")
            self.assertIn("INCLUDED_BODY", result)
            self.assertNotIn("EXCLUDED_BODY", result)
            self.assertEqual(result.count("::: {.panel section="), 1)


# ── T5: cluster without §1 → warn + skip ────────────────────────────────────


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
                    include_s1=False,  # no §1
                    s1_body="UNUSED",
                ),
            )
            buf = io.StringIO()
            with redirect_stderr(buf):
                result = rt.transpose([d_ok, d_bad], "D2")
            stderr_text = buf.getvalue()
            self.assertIn("PR-02", stderr_text)
            self.assertIn("§1", stderr_text)
            # the healthy cluster is included in the assembled result
            self.assertIn("OK_BODY", result)
            self.assertIn("§1 Pricing / PlanMatrix (PR-01)", result)
            # no chapter for the bad cluster
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


# ── T6: target_template frontmatter applied ─────────────────────────────────


class T6TargetTemplate(unittest.TestCase):
    def test_target_template_frontmatter_applied(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            # fake template
            tpl = _write(
                tmpdir,
                "D2_policy_tpl.md",
                "---\n"
                'title: "[Policy Definition] DBaaS"\n'
                "type: policy\n"
                "layer: C\n"
                "version: 1.2\n"
                "last_updated: 2020-01-01\n"
                "publication:\n"
                "  header:\n"
                "    style: info\n"
                "    body: |\n"
                "      **TEST_POLICY_SKELETON**\n"
                "---\n\n"
                "existing body (unused).\n",
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
            # template title preserved (yaml.safe_dump uses '' or "")
            self.assertIn("[Policy Definition] DBaaS", result)
            self.assertTrue(
                result.startswith("---\n") and "title:" in result.split("---")[1],
                "frontmatter generated correctly",
            )
            # last_updated refreshed (not 2020-01-01)
            self.assertNotIn("2020-01-01", result)
            self.assertIn("last_updated:", result)
            # transposed_at / transposed_from metadata added
            self.assertIn("transposed_from:", result)
            self.assertIn("transposed_at:", result)
            # template's publication.header also preserved
            self.assertIn("TEST_POLICY_SKELETON", result)


# ── T7: Dα type branching ────────────────────────────────────────────────────


class T7DalphaTypes(unittest.TestCase):
    def test_da_api_extracts_alpha_api_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            # API only
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
            # DB only (not a Da_api target)
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
        """Verifies the actual §α labels of cluster-draft.md (§α-API / §α-DB / §α-MIG)
        are extracted per deliverable — guards template ↔ render_transpose contract drift."""
        cases = [
            ("Da_api", '§α-API API Spec (Dα → transpose to API spec · optional)', "ALPHA_API_BODY"),
            ("Da_db", '§α-DB DB Schema (Dα → transpose to DB schema · optional)', "ALPHA_DB_BODY"),
            ("Da_migration", '§α-MIG Migration (Dα → transpose to migration plan · optional)', "ALPHA_MIG_BODY"),
        ]
        for deliverable, label, body in cases:
            with tempfile.TemporaryDirectory() as tmp:
                tmpdir = Path(tmp)
                draft = (
                    "---\n"
                    'title: "Cluster Pricing / PR-01 — Pricing"\n'
                    "wo_id: G2-K-PR-01\ntype: cluster_draft\nlayer: C\n"
                    "cluster:\n  capability: \"Pricing\"\n  cluster_id: \"PR-01\"\n"
                    "  cluster_name: \"Pricing\"\n"
                    f"deliverable_targets:\n  - {deliverable}\n---\n\n"
                    f'::: {{.panel section="{label}"}}\n## {label}\n\n{body}\n:::\n'
                )
                p = _write(tmpdir, "cluster_pr01.draft.md", draft)
                result = rt.transpose([p], deliverable)
                self.assertIn(body, result, f"{deliverable}: failed to extract {label}")


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
                    targets=["D3"],  # not D2
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


# ── helper — direct sort verification ───────────────────────────────────────


class TSortHelper(unittest.TestCase):
    def test_natural_key_pr_order(self):
        ids = ["PR-10", "PR-01", "PR-2", "PR-09"]
        ids.sort(key=rt._natural_key)
        self.assertEqual(ids, ["PR-01", "PR-2", "PR-09", "PR-10"])


# ── P3-1: D1 capability group-by derived view (DEC-C) ───────────────────────


class TP3FrCapabilityView(unittest.TestCase):
    def test_grouping_and_anchor(self):
        fr_index = {
            "FR-101": {"capability": "Pricing", "cluster_id": "PR-01"},
            "FR-103": {"capability": "Pricing", "cluster_id": "PR-01"},
            "FR-201": {"capability": "Provisioning", "cluster_id": "PV-02"},
        }
        out = rt.render_fr_capability_view(fr_index)
        # panel wrapper + SSoT provenance note
        self.assertIn('::: {.panel section="§D1 FR groups by capability', out)
        self.assertIn("fr_index", out)
        # capability group headers
        self.assertIn("### Pricing", out)
        self.assertIn("### Provisioning", out)
        # FR → feature-definition (cluster_id) anchor
        self.assertIn("**FR-101** → [feature definition PR-01](#PR-01)", out)
        self.assertIn("**FR-201** → [feature definition PV-02](#PV-02)", out)
        # both FRs of the same capability sit under the same group
        i_cap = out.index("### Pricing")
        self.assertIn("FR-101", out[i_cap:])
        self.assertIn("FR-103", out[i_cap:])

    def test_deterministic_order(self):
        # output is deterministic even with shuffled input (capability alphabetical → FR natural order)
        # FR-1 / FR-2 natural order + Pricing before Provisioning
        fr_index = {
            "FR-10": {"capability": "Provisioning", "cluster_id": "PV-01"},
            "FR-2": {"capability": "Pricing", "cluster_id": "PR-01"},
            "FR-1": {"capability": "Pricing", "cluster_id": "PR-01"},
        }
        out = rt.render_fr_capability_view(fr_index)
        self.assertLess(out.index("### Pricing"), out.index("### Provisioning"))
        self.assertLess(out.index("FR-1**"), out.index("FR-2**"))
        # idempotent (same input → same output)
        self.assertEqual(out, rt.render_fr_capability_view(fr_index))

    def test_empty_input(self):
        out = rt.render_fr_capability_view({})
        self.assertIn('::: {.panel section="§D1 FR groups by capability', out)
        self.assertIn("No FRs mapped", out)
        # the panel closes properly
        self.assertTrue(out.rstrip().endswith(":::"))

    def test_unmapped_cluster(self):
        out = rt.render_fr_capability_view(
            {"FR-9": {"capability": "Misc", "cluster_id": ""}}
        )
        self.assertIn("**FR-9** → (cluster unmapped)", out)


# ── P3-2: cross-cutting concern matrix derived view (DEC-F) ─────────────────


class TP3CrossCuttingMatrix(unittest.TestCase):
    def test_multi_module_matrix(self):
        # generality check — non-email modules behave the same
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
        self.assertIn('::: {.panel section="§Cross-cutting concern matrix', out)
        self.assertIn("module_index", out)
        # per-module headers (docId alphabetical order: DOC-EMAIL < DOC-LOG)
        self.assertLess(out.index("### DOC-EMAIL"), out.index("### DOC-LOG"))
        # table header
        self.assertIn(
            "| capability | cluster_id | source | via | section |", out
        )
        # row content + None section → "—"
        self.assertIn("| Provisioning | PV-01 | NODE-C | includes | — |", out)
        self.assertIn("| Account | PR-01 | NODE-A | references | §1 |", out)
        # deterministic row sort within a module (Account < Backup)
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
            node_titles={"DOC-EMAIL": "Email/SMS delivery module"},
        )
        self.assertIn("### Email/SMS delivery module (DOC-EMAIL)", out)

    def test_empty_input(self):
        out = rt.render_cross_cutting_matrix({})
        self.assertIn('::: {.panel section="§Cross-cutting concern matrix', out)
        self.assertIn("No cross-cutting modules", out)
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


# ── T9: D3 screen-level chapters (split-deliverable) ────────────────────────


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
        '::: {.panel section="§2 Screen Design"}\n## §2 Screen Design\n\n'
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
                        "### §2-1 List Screen (SCR-001)\n\nLIST_BODY list.\n\n"
                        "### §2-2 Create Screen (SCR-002)\n\nCREATE_BODY create.\n"
                    ),
                ),
            )
            result = rt.transpose([d], "D3")
            # screen index panel
            self.assertIn('section="§Screen Index"', result)
            self.assertIn("| SCR-001 | List Screen |", result)
            self.assertIn("| SCR-002 | Create Screen |", result)
            # screen-level chapters (Screen ID natural order: SCR-001 < SCR-002)
            self.assertIn('section="§1 List Screen (SCR-001)"', result)
            self.assertIn('section="§2 Create Screen (SCR-002)"', result)
            self.assertLess(result.index("LIST_BODY"), result.index("CREATE_BODY"))
            # no cluster-level chapter panel titles appear (split into screens).
            # the cluster string appears only in the screen index 'source' column.
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
                    s2_inner="### §2-1 Main screens\n\nNO_TAG_BODY body.\n",
                ),
            )
            buf = io.StringIO()
            with redirect_stderr(buf):
                result = rt.transpose([d], "D3")
            # fallback WARN
            self.assertIn("cannot split into screen-level chapters", buf.getvalue())
            # assembled as a cluster-level chapter
            self.assertIn("§1 Pricing / PlanMatrix (PR-01)", result)
            self.assertIn("NO_TAG_BODY", result)
            self.assertNotIn('section="§Screen Index"', result)

    def test_common_shell_still_routed_to_appendix_in_screen_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            main = _write(
                tmpdir, "c_main.draft.md",
                _d3_screen_draft(
                    cluster_id="PR-01", cluster_name="PlanMatrix",
                    capability="Pricing", related=["SCR-001"],
                    s2_inner="### §2-1 List (SCR-001)\n\nMAIN_BODY.\n",
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
            # screen chapters + appendix coexist, shell not captured as a normal chapter
            self.assertIn('section="§1 List (SCR-001)"', result)
            self.assertIn("§Appendix A — Common Shell", result)
            self.assertIn("SHELL_NAV_BODY", result)
            self.assertNotIn("(COMMON-01)\"", result.split("§Appendix")[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
