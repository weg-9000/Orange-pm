#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""journey_emit 유닛 테스트."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import journey_emit as M  # noqa: E402

STORYBOARD = """고객 여정 스토리보드 — openapi
액터: 전체 / 생성 시각: 2026-05-30
총 3개 화면 (완료 1 ✅ / 작성중 1 📝 / 미착수 1 ⬜)
─────────────────────────────────────────────
[1] SCR-001 API 키 관리 화면  ✅
  진입 조건: 로그인 후
  핵심 행동: 키 발급
  전환:      → SCR-002 (발급 완료)
[2] SCR-002 사용량 대시보드  📝
  핵심 행동: 사용량 조회
[3] SCR-003 파트너 콘솔  ⬜
  목적: 위임 운영
─────────────────────────────────────────────
여정 요약
  진입점: SCR-001
  핵심 경로: SCR-001 → SCR-002 → SCR-003
"""


def test_parse_storyboard_steps():
    steps = M.parse_storyboard(STORYBOARD)
    assert [s["id"] for s in steps] == ["SCR-001", "SCR-002", "SCR-003"]
    assert steps[0]["label"] == "API 키 관리 화면"
    assert steps[0]["status"] == "done"
    assert steps[1]["status"] == "draft"
    assert steps[2]["status"] == "todo"


def test_ignores_non_screen_lines():
    # 요약·구분선·진입조건 라인은 단계로 잡히지 않는다
    steps = M.parse_storyboard(STORYBOARD)
    assert len(steps) == 3


def test_order_sorted():
    shuffled = "[3] SCR-C 셋\n[1] SCR-A 하나\n[2] SCR-B 둘\n"
    steps = M.parse_storyboard(shuffled)
    assert [s["id"] for s in steps] == ["SCR-A", "SCR-B", "SCR-C"]


def test_transform_journey_shape():
    out = M.transform_journey(STORYBOARD, "openapi")
    assert out["kind"] == "journey"
    assert out["product"] == "openapi"
    assert len(out["steps"]) == 3


def test_parse_storyboard_details():
    steps = M.parse_storyboard(STORYBOARD)
    by = {s["id"]: s for s in steps}
    assert by["SCR-001"]["entry"] == "로그인 후"
    assert by["SCR-001"]["action"] == "키 발급"
    assert by["SCR-001"]["transition"] == "SCR-002 (발급 완료)"
    assert by["SCR-002"]["action"] == "사용량 조회"
    assert "entry" not in by["SCR-002"]            # 없는 키는 미부가
    assert by["SCR-003"]["purpose"] == "위임 운영"


def test_journey_build_roundtrip(tmp_path=None):
    """journey_build 산출물을 journey_emit 이 그대로 파싱한다(파이프라인 호환)."""
    import json as _json
    import tempfile
    from pathlib import Path as _P
    import journey_build as B
    with tempfile.TemporaryDirectory() as d:
        hub = _P(d)
        pdir = hub / "PROJECTS" / "demo"
        (pdir / "work-orders").mkdir(parents=True)
        (pdir / "drafts").mkdir()
        (pdir / "work-orders" / "cluster_index.json").write_text(_json.dumps({
            "clusters": [
                {"cluster_id": "PR-01", "capability": "Provisioning",
                 "draft_path": "drafts/cluster_PR-01.draft.md"},
                {"cluster_id": "PR-02", "capability": "Billing",
                 "draft_path": "drafts/cluster_PR-02.draft.md"},
            ]}), encoding="utf-8")
        (pdir / "drafts" / "cluster_PR-01.draft.md").write_text(
            "---\nreview_status: human-reviewed\n---\n"
            "## §1 정책\n- p\n\n## §2 화면\n- SCR-001 인스턴스 생성\n- 토폴로지 뷰\n",
            encoding="utf-8")
        # PR-02: draft 없음 → §2 미작성 todo
        assert B.build(hub, "demo", quiet=True) == 0
        out = pdir / "reports" / "journey-latest.md"
        steps = M.parse_storyboard(out.read_text(encoding="utf-8"))
        ids = [s["id"] for s in steps]
        assert ids == ["SCR-001", "PR-01-S2", "PR-02-S1"]
        assert steps[0]["status"] == "done"
        assert steps[2]["status"] == "todo"
        assert steps[0]["entry"] == "서비스 진입 (첫 화면)"
        # 무변경 재실행 → 멱등(파일 동일, exit 0)
        before = out.read_text(encoding="utf-8")
        assert B.build(hub, "demo", quiet=True) == 0
        assert out.read_text(encoding="utf-8") == before


def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print("PASS", name)


if __name__ == "__main__":
    _run()
