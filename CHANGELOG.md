# Changelog

이 프로젝트의 주요 변경 사항을 기록한다.
형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)를 따르고,
버전은 [SemVer](https://semver.org/lang/ko/)를 따른다.

- **MAJOR** — 호환 파괴: 스킬 제거·이름 변경, graph.json 스키마 변경, Hub 구조 변경, 네임스페이스 변경
- **MINOR** — 기능 추가: 새 스킬/에이전트, 새 capability, 하위호환 확장
- **PATCH** — 버그픽스, 문구·문서 수정, 성능 개선

버전 bump는 `python scripts/bump_version.py patch|minor|major` 로 수행한다
(plugin.json + marketplace.json 3곳 원자 동기화).

## [Unreleased]

## [2.0.0] — 2026-07-10

### Added
- 독립 레포 최초 릴리스 (gabia-pm-work 모노레포에서 분리)
- `CONNECTORS.md` — capability 기반(wiki/chat/design/repo/tasks) MCP 커넥터 자동 탐지 규약
- `/init-hub` — Planning-Agent-Hub 전체 스캐폴딩 (CONTEXT·gates·templates·connectors.md)
- 36 skills / 6 agents — Discovery → Graph → Fanout → Draft → Integrate → Confirm 워크플로우

### Changed
- 특정 벤더(Confluence·GitLab·Mattermost·Figma) 하드코딩 전면 제거 → 사용자가 연결한
  MCP 서버/커넥터 자동 탐지로 전환. 커넥터 없이도 전체 워크플로우 로컬 동작
- 환경변수 네임스페이스 `ORANGE_*` 로 정리
