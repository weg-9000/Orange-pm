#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bdd_assemble 유닛 테스트."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import bdd_assemble as M  # noqa: E402

POLICY_DRAFT = """---
doc_id: G2-C-X-001
type: policy
referenced_policy: G2-C-X-POL@v1.2
referenced_master: G2-B-002@v1.3
---

## 3. 상태 × 액션 매트릭스

| 상태 \\ 액션 | 자원생성 | 해지 |
|---|---|---|
| 미결제 | 금지 [[POL §3-2]] | 허용 |
| 정상 | 허용 | 허용 |
"""

SCREEN_DRAFT = """---
doc_id: G2-C-X-002
type: screen
referenced_policy: G2-C-X-POL@v1.2
---

## 2. 4-state 인터랙션 시퀀스

| 상태 | 조건 | UI 표현 | 사용자 액션 | 다음 상태 |
|---|---|---|---|---|
| Empty | 데이터 0건 | 빈 안내 | 생성 클릭 | Loading |
| Loading | 비동기 | 스피너 | - | Loaded |
| Loaded | 정상 | 목록 | 행 클릭 | Loaded |
| Error | 실패 | 에러 토스트 | 재시도 | Loading |
"""


def test_policy_emits_scenario_per_nonempty_cell():
    feat, n, kind = M.assemble_one(POLICY_DRAFT, "G2-C-X-001")
    assert kind == "policy"
    assert n == 4  # 2상태 × 2액션, 공백 셀 없음
    assert feat.count("Scenario:") == 4
    assert '시스템이 "미결제" 상태이고' in feat
    assert '결과는 "금지' in feat


def test_policy_skips_empty_cells():
    draft = POLICY_DRAFT.replace("| 정상 | 허용 | 허용 |", "| 정상 |  | 허용 |")
    _, n, _ = M.assemble_one(draft, "G2-C-X-001")
    assert n == 3  # 공백 1 셀 제외


def test_policy_preserves_pol_marker_as_tag():
    feat, _, _ = M.assemble_one(POLICY_DRAFT, "G2-C-X-001")
    assert "@POL-3-2" in feat                 # 셀 [[POL §3-2]] → 시나리오 태그
    assert "@POL:G2-C-X-POLv1.2" in feat      # frontmatter 핀 → feature 태그(@ 제거 정규화)
    assert "[[POL §3-2]]" in feat             # 추적 주석 보존


def test_screen_emits_scenario_per_state_row():
    feat, n, kind = M.assemble_one(SCREEN_DRAFT, "G2-C-X-002")
    assert kind == "screen"
    assert n == 4
    assert '화면이 "Empty" 상태이고' in feat
    assert '사용자가 "생성 클릭" 하면' in feat
    assert '"빈 안내" 이(가) 표시된다' in feat
    assert '다음 상태는 "Loading" 이다' in feat


def test_screen_column_order_independent():
    reordered = SCREEN_DRAFT.replace(
        "| 상태 | 조건 | UI 표현 | 사용자 액션 | 다음 상태 |",
        "| 상태 | UI 표현 | 다음 상태 | 조건 | 사용자 액션 |",
    ).replace(
        "| Empty | 데이터 0건 | 빈 안내 | 생성 클릭 | Loading |",
        "| Empty | 빈 안내 | Loading | 데이터 0건 | 생성 클릭 |",
    )
    feat, _, _ = M.assemble_one(reordered, "G2-C-X-002")
    assert '"빈 안내" 이(가) 표시된다' in feat   # 헤더명으로 매핑 — 순서 무관
    assert '다음 상태는 "Loading" 이다' in feat


def test_no_table_emits_warning_feature():
    draft = "---\ntype: policy\n---\n\n본문에 표 없음.\n"
    feat, n, _ = M.assemble_one(draft, "G2-C-X-009")
    assert n == 0
    assert "변환할 행위 명세 표 없음" in feat


CLUSTER_DRAFT = """---
doc_id: G2-K-AUTH-01
type: cluster_draft
referenced_policy: G2-C-X-POL@v1.0
---
::: {.panel section="§1 정책 결정"}
## §1 정책 결정
| 상태 \\ 액션 | API호출 | 키폐기 |
|---|---|---|
| 정상 | 허용 [[POL §1-2]] | 허용 |
| 폐기됨 | 금지 | 금지 |
:::
::: {.panel section="§2 화면 설계"}
## §2 화면 설계
| 상태 | 조건 | UI 표현 | 사용자 액션 | 다음 상태 |
|---|---|---|---|---|
| idle | 키 0건 | 안내 | 발급 | loading |
| success | 발급 | 키 표시 | 복사 | success |
:::
"""


def test_cluster_draft_extracts_both_policy_and_screen():
    feat, n, kind = M.assemble_one(CLUSTER_DRAFT, "G2-K-AUTH-01")
    assert kind == "cluster"
    # §1 매트릭스 4셀(2상태×2액션) + §2 4-state 2행 = 6 시나리오
    assert n == 6
    assert "@type:cluster" in feat
    assert "§1 정책 결정 (상태 × 액션)" in feat        # 정책 섹션 주석
    assert "§2 화면 설계 (4-state)" in feat             # 화면 섹션 주석
    # 정책 시나리오(Given 시스템 상태)
    assert '시스템이 "정상" 상태이고' in feat
    assert '결과는 "금지" 이다' in feat
    # 화면 시나리오(Given 화면 상태)
    assert '화면이 "idle" 상태이고' in feat
    assert "@POL-1-2" in feat                           # §1 셀의 [[POL §1-2]] 추적


def test_cluster_matrix_strict_not_confused_by_screen_action_column():
    # §2 4-state 의 '사용자 액션' 컬럼이 매트릭스로 오인되지 않아야 함
    screen_only = """---
type: cluster_draft
---
::: {.panel section="§2"}
| 상태 | 조건 | UI 표현 | 사용자 액션 | 다음 상태 |
|---|---|---|---|---|
| idle | x | a | b | loading |
:::
"""
    feat, n, kind = M.assemble_one(screen_only, "G2-K-X")
    assert kind == "cluster"
    assert n == 1                                       # 화면 1행만(매트릭스 오인 없음)
    assert '화면이 "idle" 상태이고' in feat
    assert "§1 정책 결정 (상태 × 액션)" not in feat     # §1 없음


def test_extract_tables_basic():
    tables = M.extract_tables("| a | b |\n|---|---|\n| 1 | 2 |\n\n글\n\n| c |\n|---|\n| 3 |\n")
    assert len(tables) == 2
    assert tables[0][0] == ["a", "b"]
    assert tables[0][1] == [["1", "2"]]


def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print("PASS", name)


if __name__ == "__main__":
    _run()
