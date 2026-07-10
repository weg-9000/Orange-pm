---
name: graph-generator
description: |
  requirements.md와 screen-list.md, {PREFIX}-A/B/C 문서를 입력으로
  정책서 섹션 노드(type: policy)와 화면설계 노드(type: screen)를
  통합한 멀티레이어 그래프를 생성한다.
  /generate-graph 스킬에서 호출된다.
model: sonnet
effort: high
maxTurns: 40
---
사전 로드: CONTEXT/layer-config.md, CONTEXT/doc-layer-schema.md

7단계 절차:

1단계 - {PREFIX} 치환
layer-config.md에서 PREFIX 값을 읽어 이후 모든 참조에 적용한다.
이후 모든 로컬 파일 경로 참조 및 노드 ID 생성에 이 값을 사용한다.

2단계 - 상위 계층 로드
CONTEXT/reference-docs/ 로컬 디렉토리에서 {PREFIX}-A, {PREFIX}-B 문서를 읽는다.
- {PREFIX}-A: CONTEXT/reference-docs/A/ 내 .md 파일 전체 (공통 정의·어휘 기준서)
- {PREFIX}-B: CONTEXT/reference-docs/B/ 내 .md 파일 전체 (공통 정책)
README.md는 제외. status: Deprecated 파일은 로드 제외.
디렉토리 또는 파일 미존재 시 → 해당 계층 없음을 PM에게 안내하고 계속 진행.
로드된 문서를 Reference 노드로 그래프에 등록한다.

3단계 - {PREFIX}-C 정책서 후보 노드 파싱
inputs/requirements.md에서 기능 단위를 추출한다.
doc_id 생성: {PREFIX}-C-{PRODUCT_CODE}-{SEQ:03d}
node_type: policy
2종 분류:
- 제품 명세: 비즈니스 규칙, 데이터 처리, 연동 정책 단위
- 요구사항정의서: 액터·이벤트·제약 기반 정책 단위
{PREFIX}-B와 동일한 내용만 있는 노드 → delta_required: false

capability 씨앗 주입 (P1 — docs/fr-cluster-alignment.md DEC-B):
inputs/requirements.seeds.yml (FR ID → capability 가설 맵)이 있으면 읽어, work 노드를
낳은 FR 키에서 node.capability(및 cluster_hint)를 채운다. 사이드카 스키마:
```yaml
"FR-101":
  capability: "Provisioning"
  cluster_hint: "PR-01"   # 선택
  lock: false             # 선택, 기본 false
"FR-102":
  capability: "[확인필요]"
```
- 씨앗은 **가설(seed-not-lock, DEC-B)** — node.capability 로만 주입한다(경계 고정 금지).
  최종 cluster 경계는 cluster_identify(5축·threshold)가 union-find 초기값으로 소비해 확정.
- 사이드카가 없거나 해당 FR 키가 없으면 capability 를 비워 둔다(cluster_identify 가 계산).

4단계 - 화면설계 노드 파싱
screen-list.md에서 각 화면 항목을 추출한다.
doc_id: SCR-NNN (screen-list.md의 Screen ID 그대로 사용)
node_type: screen
각 항목에서 다음 엣지를 등록한다:
- 연결 요구사항 ID → requires 엣지
- 연결 정책 ID (TBD가 아닌 경우) → implements 엣지
- TBD 항목 → unresolved-decisions.md 등록 후 진행

5단계 - 상속 관계 분석
각 policy 노드에 대해:
- 어떤 {PREFIX}-B 공통 정책을 상속받는가 → inherits_from 엣지
- 어떤 {PREFIX}-C 모듈을 포함하는가 → includes 엣지
각 screen 노드에 대해:
- 어떤 policy 노드가 구현 기반이 되는가 → implements 엣지
- implements 엣지 미결 항목 → unresolved-decisions.md 등록

6단계 - 노드 간 의존 관계 추론
policy ↔ policy 의존 관계 추론
screen ↔ screen 의존 관계 추론 (화면 전환 흐름 기준)
policy ↔ screen 양방향 의존 관계 추론 (정책 변경 시 영향받는 화면 탐지)
결정 불가 항목 → unresolved-decisions.md 등록

7단계 - 어휘 통제 검증
requirements.md + screen-list.md의 상태명·오류코드를 {PREFIX}-A와 대조한다.
미등재 어휘 → unresolved-decisions.md 등록

산출:
graph/graph.json              (policy 노드 + screen 노드 통합)
graph/graph-preview.md        (노드·엣지 요약 보고서)
graph/unresolved-decisions.md
graph/integration-contract.md


## Workflow Connections
- 호출 스킬: [[graph-gen]]
- 읽는 컨텍스트: [[layer-config]], [[doc-layer-schema]], [[reference-docs-B-README]], inputs/requirements.seeds.yml (capability 씨앗)
- 쓰는 경로: PROJECTS/{product}/graph/
- 게이트: [[graph-exit-gate]]
