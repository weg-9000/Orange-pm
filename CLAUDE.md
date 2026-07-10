# orange-pm Planning Automation — Session Configuration

## Advisor 모델 라우팅 전략

본 시스템은 `advisor_20260301` 서버사이드 도구를 활용해 세션 내부에서 모델을 동적으로 라우팅합니다.
**신규 모델 출시 시 아래 Advisor 설정의 `model` 필드 1곳만 업데이트하면 됩니다.**

### 역할 레이블 정의

| 레이블 | 적용 모델 | 용도 |
|--------|-----------|------|
| `advisor` | claude-opus-4-8 | 복잡 판단, 클러스터 발견, 그래프 설계, 정책 구조 분석 |
| `direct`  | claude-sonnet-4-6 (기본) | 일반 대화, 커맨드 라우팅, 중간 복잡도 작업 |
| `batch`   | claude-haiku-4-5 | 인덱스 빌드, 분류, 요약, 반복·저비용 처리 |

### Advisor 도구 설정

`model: advisor` 스킬 실행 시 아래 도구를 선언해 Opus에 심층 판단을 위임합니다:

```json
{
  "type": "advisor_20260301",
  "name": "advisor",
  "model": "claude-opus-4-8"
}
```

Beta header: `advisor-tool-2026-03-01`

### 신규 모델 출시 대응

1. 위 `"model": "claude-opus-4-8"` 값 1개만 새 모델 ID로 교체
2. VS Code 설정 `orangePmViz.modelAdvisor` 값 동기화 (선택)
3. 36개 SKILL.md는 레이블(`advisor/direct/batch`)만 사용하므로 무변경

### 스킬별 모델 라우팅 원칙

- `effort: high` 스킬 → `model: advisor` — Opus가 판단, Sonnet이 실행
- `effort: medium` 스킬 → `model: direct` — Sonnet 직접 처리
- `effort: low` 스킬 → `model: batch` — Haiku (경량, 고속)

### advisor 도구 사용 지침 (model: advisor 스킬)

복잡한 판단이 필요한 시점에 advisor 도구를 호출합니다:
- 클러스터 경계 식별 및 의존성 그래프 설계
- 정책 충돌 탐지 및 Delta 범위 결정
- 멀티-스킬 파이프라인 계획 수립
- 복수 문서 교차 분석

단순 진행(파일 읽기, 포맷 변환, 상태 기록)은 advisor 호출 없이 직접 처리합니다.
