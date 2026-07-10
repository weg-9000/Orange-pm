#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""session_emit 유닛 테스트."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import session_emit as M  # noqa: E402

DECISIONS = """# 의사결정 로그
| DEC ID | 일자 | 결정 | 사유 | 영향 |
|---|---|---|---|---|
| DEC-VIZ-001 | 2026-06-03 | 디자인 외부화 | 지시 | 정책 |
| DEC-VIZ-002 | 2026-06-03 | A안 단독 | 균형 | 계획 |
"""

OPEN = """# 미결
## P0 (블로킹)
(없음)
## P1 (협의)
| ID | 항목 | 현황 | 담당 | 목표일 |
|---|---|---|---|---|
| OI-001 | 터미널 식별 | 잠정 | PM | M4 |
## P2 (보완)
| ID | 항목 | 현황 | 담당 | 목표일 |
|---|---|---|---|---|
| OI-003 | bridge 기본값 | off | PM | M5 |
"""


def test_parse_decisions():
    res = M.parse_decisions(DECISIONS)
    assert [d["id"] for d in res] == ["DEC-VIZ-001", "DEC-VIZ-002"]
    assert res[0]["date"] == "2026-06-03"
    assert res[0]["title"] == "디자인 외부화"
    assert res[0]["status"] == "approved"


DECISIONS_REAL = """## 결정 로그
| DEC ID | 등재일 | 상태 | 도메인 | 결정 요지 | 영향 FR/§ | 번복 대상 | 승인 | 근거 파일 |
|---|---|---|---|---|---|---|---|---|
| DEC-001 | 2026-04-27 | 등재 | 🏗️ | 상위 계층 참조 제외 | 전 산출물 | - | ✅ jeongdh | session-log |
| ~~DEC-003~~ | 2026-05-11 | 번복 | 💰 | 약정기간 탭 미배치 | S01 | - | ✅ jeongdh | DEC-045 |
| DEC-080 | 2026-05-20 | 등재 | 🧭 | 프리셋 변경 | S02 | - | ⬜ | 미정 |
"""


def test_parse_decisions_header_aware_real_layout():
    # 실제 9열 표: 결정 요지가 4열·상태가 2열·승인이 7열 — 헤더명 기반 탐색 검증
    res = M.parse_decisions(DECISIONS_REAL)
    by = {d["id"]: d for d in res}
    assert by["DEC-001"]["date"] == "2026-04-27"
    assert by["DEC-001"]["title"] == "상위 계층 참조 제외"   # cells[2]='등재' 가 아님
    assert by["DEC-001"]["regType"] == "등재"
    assert by["DEC-001"]["approval"] == "approved"
    assert by["DEC-001"]["approver"] == "jeongdh"
    assert "DEC-003" in by                                   # ~~취소선~~ 제거된 id
    assert by["DEC-080"]["approval"] == "pending"            # ⬜ 미승인


DECISIONS_ID_HEADER = """## 결정
| ID | 일자 | 도메인 | 핵심 결정 | 번복 | 승인 | 근거 |
|---|---|---|---|---|---|---|
| DEC-001 | 2026-05-28 | 🤖자동기록 | Confluence 단독 합성 | — | ✅ jeongdh | /draft-req |
"""

DECISIONS_4COL = """## 결정
| ID | 결정 내용 | 확정일 | 결정자 |
|---|---|---|---|
| DEC-01 | **프로젝트 범위**: 통계 신규 개발만 | 2026-05-13 | PM |
"""


def test_parse_decisions_id_header_7col():
    # 첫 컬럼이 'DEC ID' 가 아니라 'ID' 인 표 (dbaas 형) — 헤더 탐색 일반화 검증
    res = M.parse_decisions(DECISIONS_ID_HEADER)
    d = res[0]
    assert d["date"] == "2026-05-28"
    assert d["title"] == "Confluence 단독 합성"
    assert d["approval"] == "approved" and d["approver"] == "jeongdh"


def test_parse_decisions_4col_no_approval():
    # 승인 컬럼 없는 4열 표 (백오피스 형) — 결정자 를 approver 로, ** 마크다운 제거
    res = M.parse_decisions(DECISIONS_4COL)
    d = res[0]
    assert d["date"] == "2026-05-13"
    assert d["title"] == "프로젝트 범위: 통계 신규 개발만"   # ** 제거
    assert d["approval"] == "approved"                       # 승인 컬럼 부재 → 기본
    assert d["approver"] == "PM"                             # 결정자 폴백


DECISIONS_LEDGER = """## 결정 원장
| 결정 ID | 결정 내용 | 결정자 | 영향 범위 (cluster) | 발효일 |
|---|---|---|---|---|
| DEC-001 | 캐시 TTL 5분 확정 | 박PM | CL-RES | 2026-06-02 |
"""


def test_parse_decisions_ledger_header():
    # 회의록 원장형: 첫칸 '결정 ID', 날짜 '발효일', approver '결정자'
    res = M.parse_decisions(DECISIONS_LEDGER)
    d = res[0]
    assert d["date"] == "2026-06-02"
    assert d["title"] == "캐시 TTL 5분 확정"
    assert d["approver"] == "박PM"


DECISIONS_WITH_ADDENDUM = """## DEC 원장 (SSoT)
| ID | 일자 | 도메인 | 핵심 결정 | 번복 | 승인 | 근거(스킬·세션) |
|---|---|---|---|---|---|---|
| DEC-001 | 2026-06-01 | 🏗️ | 실제 결정 A | - | ✅ jeongdh | /write |
| DEC-002 | 2026-06-01 | 💰 | 실제 결정 B | - | ⬜ | /su |

## 미해소·이슈
| DEC ID | 이슈 | PM 확인 필요 |
|---|---|---|
| DEC-067·068 | 승급 필요 | PM 확인 |

## 보류 사항
| ID | 항목 | 사유 |
|---|---|---|
| DEC-099 | 보류 항목 | 미정 |
"""


def test_parse_decisions_skips_addendum_tables():
    # 결정표(핵심 결정 컬럼)만 파싱, 이슈/보류 부속표의 DEC 행은 제외
    res = M.parse_decisions(DECISIONS_WITH_ADDENDUM)
    assert [d["id"] for d in res] == ["DEC-001", "DEC-002"]
    assert res[0]["title"] == "실제 결정 A"
    assert res[0]["approval"] == "approved" and res[1]["approval"] == "pending"


def test_parse_open_issues_priority_from_section():
    res = M.parse_open_issues(OPEN)
    by = {i["id"]: i for i in res}
    assert by["OI-001"]["p"] == 1
    assert by["OI-003"]["p"] == 2
    assert "(없음)" not in [i["id"] for i in res]   # 표 행만


# ── 체크박스 형식 (실파일 회귀: 백오피스 통계 / dbaas-mysql / cloud-calculator) ──

OPEN_CHECKBOX = """# 백오피스 통계 Open Issues
## P0 — 즉시 해소 필요
_(없음)_
## Gen1·Gen2 실데이터 조사 결과 (2026-06-01)
- [x] **[OPEN-30] 해소 (DEC-37, 2026-06-01)** — 옵션 B 채택
- [ ] **[OPEN-33] (P1)** 공공클라우드 매출 소스·집계 방식 미확정 — DEC-37 통합 뷰 전제
- [i] **[OPEN-31 연계]** 월간보고 자동 피드 후보
- [ ] **[OPEN-32] (P1)** 가입자 변동 지표 정의 차이
- [ ] **[OPEN-12] 진전** — 불완전 export, 조인 키 확인 잔존
## P1 — Discovery 필수 수집 항목
- [x] [DISC-01] 경쟁사 분석 → `/research` 완료
- [ ] [DISC-04] `BACKSTAT-B` 마스터 정책 문서 Confluence 링크 미등록
## P2 — 권장 수집 항목
- [ ] [OPEN-02] 스냅샷 인프라 도입 결정 미완
"""


def test_parse_open_issues_checkbox_format():
    # 백오피스 형: 표 0건·전부 체크박스 + **[ID]** 래핑 — 종전 파서는 0건 반환(회귀)
    res = M.parse_open_issues(OPEN_CHECKBOX)
    by = {i["id"]: i for i in res}
    assert set(by) == {"OPEN-33", "OPEN-32", "OPEN-12", "DISC-04", "OPEN-02"}
    assert by["OPEN-33"]["p"] == 1                       # 비-P 섹션 + 인라인 (P1) 우선
    assert by["OPEN-33"]["title"].startswith("공공클라우드")  # (P1)·** 마크업 제거
    assert by["OPEN-12"]["p"] == 1                       # 비-P ## 섹션 → 기본 P1
    assert by["DISC-04"]["p"] == 1 and by["OPEN-02"]["p"] == 2


OPEN_DBAAS_STYLE = """# dbaas-mysql Open Issues
## P1 — 합성 결과 보강·해소 필수
### 정책 자체 미확정 (Confluence v94/v12 명시 미결)
- [ ] **[TBD-01]** 연체 정지 처리 — 수치 미기재 / 확인 대상: 결제·청구팀
- [x] ~~**[TBD-06]** 모니터링 알람 임계치 정책 미수립~~ → **해소 (2026-05-28 / DEC-005)**
## P2 — 권장 수집 / 정책 자체 검토중
- [ ] **[ERRCODE-G2A-UNRESOLVED]** *(P1 / upstream gap, 2026-06-05)* G2-A 오류코드 체계 미확정
- [ ] **[CONSOLIDATED-FM-SYNC]** *(WRN-01 / Round 5)* 통합본 frontmatter stale — P2 수용
"""


def test_parse_open_issues_dbaas_subheading_and_inline_p():
    # dbaas 형: ~~취소선~~ 해소 항목 제외·### 하위 헤딩 P 유지·괄호 인라인 P1
    res = M.parse_open_issues(OPEN_DBAAS_STYLE)
    by = {i["id"]: i for i in res}
    assert set(by) == {"TBD-01", "ERRCODE-G2A-UNRESOLVED", "CONSOLIDATED-FM-SYNC"}
    assert by["TBD-01"]["p"] == 1                        # ### 하위 헤딩은 섹션 P1 유지
    assert by["ERRCODE-G2A-UNRESOLVED"]["p"] == 1        # P2 섹션 + 인라인 "(P1 / …)" 우선
    assert by["CONSOLIDATED-FM-SYNC"]["p"] == 2          # 인라인 표기 없음 → 섹션 P2


OPEN_CLOUDCALC_STYLE = """# cloud-calculator Open Issues
## P0 — 즉시 해소 필요
- [x] [RESP-Q01] ~~반응형 미정의~~ → **해소 (PM 결정 2026-05-18)**
- [~] (HOLD — 개발 착수 회의 이월) **자연 스크롤 셸 sticky 패널 높이 모델** | 개발 착수 회의
- [ ] [DRIFT-GATE-OPTOUT] **CON-001 drift-gate 정식 등재 — P2 (2026-05-20, /review --all 30차 발견)** | 기획자
## P1 — 인프라·보안 SW 종속·화면 모델 확정 (2026-05-16 19차)
- [x] [INFRA-SEC-MODEL] **종속·화면·과금 모델 확정** — 아래 표 정본.

  | 대상 | 화면 입력 방식(UI) | Requires / Suggests |
  |---|---|---|
  | CDN | 외부 도메인 URL 직접 텍스트 입력 | Requires: 없음 |
  | NAS | 서브넷 지정·용량 선택 | Requires: VPC |

- [ ] [STK-Q02] 상품관리 시스템 API 연동 — 개발 착수 회의 기술 검증 항목:
  - [ ] [STK-Q02-2] 비회원 견적 호출 경로 — 공통플랫폼개발팀
  - [~] [STK-Q02-1] 약정 할인 정책 등록 여부 — 부분 회신
"""


def test_parse_open_issues_embedded_reference_table_ignored():
    # 회귀 가드: 해소 항목 본문의 참조용 표(헤더 '대상')가 이슈 9건으로 오인되던 버그
    res = M.parse_open_issues(OPEN_CLOUDCALC_STYLE)
    ids = [i["id"] for i in res]
    assert "대상" not in ids and "CDN" not in ids and "NAS" not in ids


def test_parse_open_issues_hold_and_nested():
    res = M.parse_open_issues(OPEN_CLOUDCALC_STYLE)
    by = {i["id"]: i for i in res}
    assert "RESP-Q01" not in by                          # [x] 해소 제외
    assert by["DRIFT-GATE-OPTOUT"]["p"] == 2             # P0 섹션 + 인라인 "— P2 (…)" 우선
    assert by["STK-Q02"]["p"] == 1
    assert by["STK-Q02-2"]["p"] == 1                     # 들여쓴 하위 체크박스 개별 항목
    assert by["STK-Q02-1"]["p"] == 1                     # [~] 보류 = 미해결 포함
    no_id = [i for i in res if i["id"] == ""]            # ID 없는 [~] 항목도 수집
    assert len(no_id) == 1 and no_id[0]["p"] == 0
    assert no_id[0]["title"].startswith("(HOLD")


def test_parse_open_issues_long_title_truncated():
    res = M.parse_open_issues("## P1\n- [ ] [LONG-01] " + "가" * 200 + "\n")
    assert res[0]["id"] == "LONG-01"
    assert len(res[0]["title"]) == 120 and res[0]["title"].endswith("…")


UI_EVENTS = "\n".join([
    '{"ts":"2026-06-01T17:20:00+09:00","hook":"PostToolUse","tool":"edit","detail":"S01.draft.md"}',
    '{"ts":"2026-06-01T17:35:00+09:00","hook":"SubagentStop","agent":"reviewer"}',
    'not-json-line-ignored',
    '{"ts":"2026-06-01T16:50:00+09:00","hook":"SessionStart"}',
])


def test_parse_ui_events_sorted_and_mapped():
    tl = M.parse_ui_events(UI_EVENTS)
    assert len(tl) == 3                                   # 깨진 줄 무시
    assert tl[0]["ts"] == "2026-06-01T17:35:00+09:00"     # 최신 우선
    assert tl[0]["event"] == "subagent" and tl[0]["label"] == "reviewer"
    assert tl[-1]["event"] == "skill"                     # SessionStart → skill


def test_transform_session_timeline_from_hook_channel():
    out = M.transform_session({"decisions.md": DECISIONS, "open-issues.md": OPEN},
                              "demo", ui_events=UI_EVENTS)
    assert out["kind"] == "session"
    assert len(out["decisions"]) == 2
    assert len(out["openIssues"]) == 2
    assert out["resume"] is None
    assert len(out["timeline"]) == 3                      # hook 채널 보강


def test_transform_session_empty_timeline_without_events():
    out = M.transform_session({"decisions.md": DECISIONS}, "demo")
    assert out["timeline"] == []


def _run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print("PASS", name)


if __name__ == "__main__":
    _run()
