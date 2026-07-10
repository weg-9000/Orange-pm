---
title: "[회의록] {{PRODUCT_NAME}}"
wo_id: G2-DIRECT-D4
type: meetings
layer: DIRECT
version: 1.0
last_updated: 2026-05-30

publication:
  header:
    style: info
    body: |
      **본 페이지는 {{PRODUCT_NAME}} 회의록 누적 페이지다. 회의 항목은 시간 역순으로 정렬한다 — 최신 회의가 §1.**

      doc_id: {{DOC_ID}} 버전: {{VERSION}} 최종 수정: {{DATE}}
  meta:
    layout: two_equal
    cells:
      - panel:
          title: "관련 페이지"
          body: |
            **관련 문서**

            - [[page:[요구사항 정의서] {{PRODUCT_NAME}}]]
            - [[page:[정책정의서] {{PRODUCT_NAME}}]]
            - [[page:[화면설계서] {{PRODUCT_NAME}}]]
      - change_history: 10
---

::: {.panel section="회의록 작성 가이드" style="info"}
## 회의록 작성 가이드

---

- **누적형 페이지**: 회의가 발생할 때마다 §1 위치에 신규 항목을 추가한다 (시간 역순).
- **번호 규칙**: §1이 최신 회의, §2가 직전 회의 … 회의 표시 ID는 `MTG-{{YYYYMMDD}}-{{NN}}` 형식을 권장한다(발행 페이지 가독용).
- **⚠️ 핀 정본 ID 구분**: 화면 frontmatter `meeting_decisions: [...]` 핀과 `mtg-ledger.md` 원장 행 ID 는 **원장 정본 `MTG-\d+`(예 MTG-01)만 사용**한다. `mtg_ledger_scan.py` 가 `^MTG-\d+$` 로만 교차검증하므로, 위 표시 ID(`MTG-YYYYMMDD-NN`)를 핀에 쓰면 원장 매칭이 실패한다. 표시 ID ↔ 원장 ID 매핑이 필요하면 회의 메타 표에 원장 `MTG-NN` 을 병기한다.
- **cluster 참조**: 회의 메타 표의 "관련 cluster" 행에 PR-XX / BL-XX 형태로 cross-reference 한다.
- **결정 사항**: DEC-XXX 단언형 문장으로 기록한다 (~한다 / ~이다). 추측·의견은 §N-5 미결로 분리한다.
- **액션 아이템**: 담당·기한·상태(📋 미착수 / ⏳ 진행 / ✅ 완료)를 반드시 명시한다.
- **하단 인덱스**: 신규 회의 추가 시 페이지 하단 "회의록 인덱스" 표에 1행 추가한다.
:::

::: {.panel section="§1 회의 — {{MEETING_DATE_LATEST}} {{MEETING_TOPIC_LATEST}}"}
## §1 회의 — {{MEETING_DATE_LATEST}} {{MEETING_TOPIC_LATEST}}

---

<!-- col-widths: 20%, 80% -->
| 항목 | 내용 |
|---|---|
| **회의 ID** | MTG-{{YYYYMMDD_LATEST}}-01 |
| **일시** | {{MEETING_DATE_LATEST}} {{MEETING_TIME_LATEST}} |
| **참석자** | {{ATTENDEES_LATEST}} |
| **부재** | {{ABSENTEES_LATEST}} |
| **장소/방식** | {{MEETING_VENUE_LATEST}} |
| **관련 cluster** | {{CLUSTER_REFS_LATEST}} |
| **회의 유형** | R2 / 진행 |

### §1-1 안건

1. {{안건1}}
2. {{안건2}}
3. {{안건3}}

### §1-2 논의 요약

- **안건 1 — {{안건1}}**: {{논의 요약}}
- **안건 2 — {{안건2}}**: {{논의 요약}}
- **안건 3 — {{안건3}}**: {{논의 요약}}

### §1-3 결정 사항

<!-- col-widths: 10%, 40%, 15%, 20%, 15% -->
| 결정 ID | 결정 내용 | 결정자 | 영향 범위 (cluster) | 발효일 |
|---|---|---|---|---|
| **DEC-001** | {{결정 단언 — ~한다 / ~이다}} | {{결정자}} | {{PR-01}} | {{YYYY-MM-DD}} |
| **DEC-002** | {{결정 단언}} | {{결정자}} | {{BL-02}} | {{YYYY-MM-DD}} |

### §1-4 액션 아이템

<!-- col-widths: 10%, 45%, 15%, 15%, 15% -->
| 액션 ID | 내용 | 담당 | 기한 | 상태 |
|---|---|---|---|---|
| **ACT-001** | {{액션 내용}} | {{담당자}} | {{YYYY-MM-DD}} | 📋 |
| **ACT-002** | {{액션 내용}} | {{담당자}} | {{YYYY-MM-DD}} | ⏳ |

### §1-5 미결 / Open Questions

- **OQ-001** {{미결 질문}} — 차기 회의(MTG-{{YYYYMMDD_NEXT}}) 이관
- **OQ-002** {{미결 질문}} — {{담당}} 별도 채널 확인
:::

::: {.panel section="§2 회의 — {{MEETING_DATE_PREV}} {{MEETING_TOPIC_PREV}}"}
## §2 회의 — {{MEETING_DATE_PREV}} {{MEETING_TOPIC_PREV}}

---

<!-- col-widths: 20%, 80% -->
| 항목 | 내용 |
|---|---|
| **회의 ID** | MTG-{{YYYYMMDD_PREV}}-01 |
| **일시** | {{MEETING_DATE_PREV}} {{MEETING_TIME_PREV}} |
| **참석자** | {{ATTENDEES_PREV}} |
| **부재** | {{ABSENTEES_PREV}} |
| **장소/방식** | {{MEETING_VENUE_PREV}} |
| **관련 cluster** | {{CLUSTER_REFS_PREV}} |
| **회의 유형** | R1 / 진행 |

### §2-1 안건

1. {{안건1}}
2. {{안건2}}

### §2-2 논의 요약

- **안건 1 — {{안건1}}**: {{논의 요약}}
- **안건 2 — {{안건2}}**: {{논의 요약}}

### §2-3 결정 사항

<!-- col-widths: 10%, 40%, 15%, 20%, 15% -->
| 결정 ID | 결정 내용 | 결정자 | 영향 범위 (cluster) | 발효일 |
|---|---|---|---|---|
| **DEC-003** | {{결정 단언}} | {{결정자}} | {{PR-02}} | {{YYYY-MM-DD}} |

### §2-4 액션 아이템

<!-- col-widths: 10%, 45%, 15%, 15%, 15% -->
| 액션 ID | 내용 | 담당 | 기한 | 상태 |
|---|---|---|---|---|
| **ACT-003** | {{액션 내용}} | {{담당자}} | {{YYYY-MM-DD}} | ✅ |

### §2-5 미결 / Open Questions

- **OQ-003** {{미결 질문}} — §1 회의에서 해소(DEC-001 참조)
:::

::: {.panel section="§3 회의 — {{MEETING_DATE_R0}} 킥오프"}
## §3 회의 — {{MEETING_DATE_R0}} 킥오프

---

<!-- col-widths: 20%, 80% -->
| 항목 | 내용 |
|---|---|
| **회의 ID** | MTG-{{YYYYMMDD_R0}}-01 |
| **일시** | {{MEETING_DATE_R0}} {{MEETING_TIME_R0}} |
| **참석자** | {{ATTENDEES_R0}} |
| **부재** | {{ATTENDEES_R0_ABS}} |
| **장소/방식** | {{MEETING_VENUE_R0}} |
| **관련 cluster** | 전체 (Phase 0 스코프) |
| **회의 유형** | R0 / 킥오프 |

### §3-1 안건

1. 프로젝트 스코프 확정
2. 역할 분담
3. 마일스톤 합의

### §3-2 논의 요약

- **스코프**: {{스코프 합의 내용}}
- **역할**: {{역할 분담 결과}}
- **마일스톤**: {{마일스톤 합의 내용}}

### §3-3 결정 사항

<!-- col-widths: 10%, 40%, 15%, 20%, 15% -->
| 결정 ID | 결정 내용 | 결정자 | 영향 범위 (cluster) | 발효일 |
|---|---|---|---|---|
| **DEC-004** | {{PRODUCT_NAME}} Phase 1 스코프는 {{스코프}}으로 한다 | {{결정자}} | 전체 | {{MEETING_DATE_R0}} |
| **DEC-005** | PM은 {{담당}}, 개발 리드는 {{담당}}으로 한다 | {{결정자}} | 전체 | {{MEETING_DATE_R0}} |

### §3-4 액션 아이템

<!-- col-widths: 10%, 45%, 15%, 15%, 15% -->
| 액션 ID | 내용 | 담당 | 기한 | 상태 |
|---|---|---|---|---|
| **ACT-004** | 요구사항 초안 작성 | {{담당자}} | {{YYYY-MM-DD}} | ✅ |
| **ACT-005** | 정책 초안 작성 | {{담당자}} | {{YYYY-MM-DD}} | ✅ |

### §3-5 미결 / Open Questions

- 없음 (킥오프 완료)
:::

::: {.panel section="회의록 인덱스" style="info"}
## 회의록 인덱스

---

<!-- col-widths: 15%, 15%, 35%, 20%, 15% -->
| 회의 ID | 일시 | 주제 | 관련 cluster | 핵심 결정 수 |
|---|---|---|---|---|
| **MTG-{{YYYYMMDD_LATEST}}-01** | {{MEETING_DATE_LATEST}} | {{MEETING_TOPIC_LATEST}} | {{CLUSTER_REFS_LATEST}} | 2 |
| **MTG-{{YYYYMMDD_PREV}}-01** | {{MEETING_DATE_PREV}} | {{MEETING_TOPIC_PREV}} | {{CLUSTER_REFS_PREV}} | 1 |
| **MTG-{{YYYYMMDD_R0}}-01** | {{MEETING_DATE_R0}} | 킥오프 | 전체 | 2 |
:::
