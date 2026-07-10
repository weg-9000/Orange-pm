---
name: critique
description: |
  정책서·화면설계서에 대해 완전 비판적 기획 리뷰를 수행한다.
  위키 페이지 URL 또는 로컬 파일을 입력받아 9개 평가 축으로 분석하고,
  실제 기획 리뷰 회의록 형식으로 BLOCK/FIX/HOLD/WARN/BACKLOG 피드백을 출력한다.
  기존 /review(초안 자기완결성 검증)와 달리, 기획 의사결정의 품질·운영가능성·고객관점까지 평가한다.
  AXIS-04 는 제품 G2-C ↔ 공통 G2-B/G2-A 정합(C0·C-PIN, 공통 opt-out 안티패턴)도 검증한다.
  9개 축은 전부 유지된다(슬림화 보류 — 상류 검증의 최종 judgment 안전망).
triggers:
  - "critique"
  - "비판적 리뷰"
  - "기획 리뷰"
  - "기획서 평가"
  - "정책서 평가"
  - "화면설계 평가"
  - "review critique"
phase: any
effort: high
model: opus
user-invocable: true
---
