#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bdd_coverage_scan 유닛 테스트."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import bdd_assemble as A  # noqa: E402
import bdd_coverage_scan as M  # noqa: E402

FULL_4STATE = """## 2. 4-state

| 상태 | 조건 | UI 표현 | 사용자 액션 | 다음 상태 |
|---|---|---|---|---|
| Empty | x | a | b | Loading |
| Loading | x | a | b | Loaded |
| Loaded | x | a | b | Loaded |
| Error | x | a | b | Loading |
"""

MISSING_ERROR = """## 2. 4-state

| 상태 | 조건 | UI 표현 | 사용자 액션 | 다음 상태 |
|---|---|---|---|---|
| Empty | x | a | b | Loading |
| Loading | x | a | b | Loaded |
| Loaded | x | a | b | Loaded |
"""

MATRIX = """## 3. 상태 × 액션 매트릭스

| 상태 \\ 액션 | A1 | A2 |
|---|---|---|
| S1 | 허용 | 금지 |
| S2 | 허용 | 허용 |
"""

SPARSE_MATRIX = """## 3. 상태 × 액션 매트릭스

| 상태 \\ 액션 | A1 | A2 | A3 | A4 |
|---|---|---|---|---|
| S1 | 허용 |  |  |  |
"""


def _table(md, finder):
    return finder(A.extract_tables(md))


def test_full_4state_no_missing():
    assert M.screen_missing_states(_table(FULL_4STATE, A.find_state_table)) == []


def test_missing_error_state_detected():
    miss = M.screen_missing_states(_table(MISSING_ERROR, A.find_state_table))
    assert "error" in miss
    assert len(miss) == 1


def test_na_reason_exempts_missing():
    draft = MISSING_ERROR + "\n\n비고: error 상태 해당 없음 — 이 화면은 정적 표시 전용.\n"
    # screen_missing_states 는 표 데이터만 보므로 표 안에 N/A 행을 넣어 검증
    with_na = MISSING_ERROR.rstrip() + "| Error | 해당 없음 | - | - | - |\n"
    assert "error" not in M.screen_missing_states(_table(with_na, A.find_state_table))


def test_policy_full_matrix_ratio():
    filled, total = M.policy_empty_ratio(_table(MATRIX, A.find_matrix_table))
    assert (filled, total) == (4, 4)


def test_policy_sparse_matrix_ratio_under_half():
    filled, total = M.policy_empty_ratio(_table(SPARSE_MATRIX, A.find_matrix_table))
    assert filled == 1 and total == 4
    assert filled / total < 0.5


CLUSTER_FULL = """## §1
| 상태 \\ 액션 | A1 | A2 |
|---|---|---|
| S1 | 허용 | 금지 |
## §2
| 상태 | 조건 | UI 표현 | 사용자 액션 | 다음 상태 |
|---|---|---|---|---|
| Empty | x | a | b | Loading |
| Loading | x | a | b | Loaded |
| Loaded | x | a | b | Loaded |
| Error | x | a | b | Loading |
"""

CLUSTER_MISSING_STATE = CLUSTER_FULL.replace("| Error | x | a | b | Loading |\n", "")


def test_cluster_both_tables_extracted():
    tables = A.extract_tables(CLUSTER_FULL)
    assert A.find_matrix_table_strict(tables) is not None      # §1 매트릭스
    assert A.find_state_table(tables) is not None              # §2 4-state
    # §2 4-state 가 strict 매트릭스로 오인되지 않음
    state = A.find_state_table(tables)
    assert M.screen_missing_states(state) == []                # 4-state 전부


def test_cluster_missing_4state_is_uncovered():
    tables = A.extract_tables(CLUSTER_MISSING_STATE)
    state = A.find_state_table(tables)
    miss = M.screen_missing_states(state)
    assert "error" in miss                                     # §2 error 누락 → UNCOVERED 대상


def _scan_one(tmp, *drafts, write_feature=False):
    """tmp 아래 PROJECTS/p/drafts 에 draft 들을 깔고 scan 실행 → (rc, 큐 텍스트)."""
    import pathlib
    proj = pathlib.Path(tmp) / "PROJECTS" / "p"
    (proj / "drafts").mkdir(parents=True)
    (proj / "reports" / "bdd").mkdir(parents=True)
    for wo, body in drafts:
        (proj / "drafts" / f"{wo}.draft.md").write_text(body, encoding="utf-8")
        if write_feature:
            (proj / "reports" / "bdd" / f"{wo}.feature").write_text("Feature: x\n", encoding="utf-8")
    rc = M.scan(pathlib.Path(tmp), "p")
    return rc, (proj / "reports" / "bdd-coverage-queue.md").read_text(encoding="utf-8")


def test_screen_without_state_table_is_uncovered():
    """4-state 표 없는 screen draft = UNCOVERED (허위 green 방지 회귀)."""
    import tempfile
    no_tbl = "---\ntype: screen\n---\n\n## 화면 설명\n\n| 영역 | 값 |\n|---|---|\n| a | b |\n"
    with tempfile.TemporaryDirectory() as tmp:
        rc, q = _scan_one(tmp, ("WO-99", no_tbl))
    assert "UNCOVERED: 1" in q
    assert "표 없음" in q
    assert rc == 1  # 차단


def test_cluster_draft_type_classified_as_screen():
    """cluster_draft type 은 screen 으로 정규화 — 크래시 없이 처리(회귀)."""
    import tempfile
    cluster = "---\ntype: cluster_draft\n---\n\n" + FULL_4STATE
    with tempfile.TemporaryDirectory() as tmp:
        rc, q = _scan_one(tmp, ("cluster_X", cluster), write_feature=True)
    assert "UNCOVERED: 0" in q and "STALE: 0" in q
    assert rc == 0


LIFECYCLE_TABLE = """## §1-4 상태 / 라이프사이클

| 상태 | 정의 | 진입 조건 | 다음 상태(가능) |
|---|---|---|---|
| 마감(불변) | 스냅샷 확정 | 분기 마감 배치 | 보존 만료 |
"""


def test_policy_lifecycle_table_not_detected_as_screen():
    """정책 라이프사이클 표(UI·액션 컬럼 없음)는 screen 4-state 표로 오인식 금지."""
    assert A.find_state_table(A.extract_tables(LIFECYCLE_TABLE)) is None


def test_na_subsection_exempts_missing_state():
    """'### error 상태' + '해당 없음' prose 는 error 누락을 면제(문서화 N/A)."""
    import tempfile
    body = (
        "---\ntype: screen\n---\n\n## 5. 4-State 인터랙션 시퀀스\n\n"
        "### 5-1. idle\n\n| 항목 | 내용 |\n|---|---|\n| 진입 | a |\n\n"
        "### 5-2. loading\n\n| 항목 | 내용 |\n|---|---|\n| 트리거 | a |\n\n"
        "### 5-3. success\n\n| 항목 | 내용 |\n|---|---|\n| 완료 | a |\n\n"
        "### error 상태\n\n- **해당 없음** — 정적 재산출이라 독립 error 없음.\n"
    )
    with tempfile.TemporaryDirectory() as tmp:
        rc, q = _scan_one(tmp, ("WO-NA", body), write_feature=True)
    assert "UNCOVERED: 0" in q
    assert "N/A:error" in q
    assert rc == 0


def test_wo_stub_skipped():
    """'# Work Order:' 지시 스텁은 콘텐츠 draft 아님 — 스캔/카운트에서 제외."""
    import tempfile
    stub = ("---\ntype: screen\n---\n\n# Work Order: WO-08 — 계산기 메인 화면\n\n"
            "## 1. 할당 범위\n\n## 7. 완료 후 절차\n")
    with tempfile.TemporaryDirectory() as tmp:
        rc, q = _scan_one(tmp, ("WO-08", stub))
    assert "UNCOVERED: 0" in q
    assert rc == 0


def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print("PASS", name)


if __name__ == "__main__":
    _run()
