---
name: orange-pm:update
description: orange-pm 플러그인을 git pull로 최신 커밋으로 업데이트한다. 로컬 git 저장소에서 직접 당겨오므로 별도 토큰이 필요 없다.
triggers:
  - "update"
  - "plugin update"
  - "orange-pm update"
  - "플러그인 업데이트"
phase: any
effort: low
model: haiku
user-invocable: true
---

## 실행 단계

### 단계 1 — 새 커밋 확인

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/update_orange_pm.py" --check
```

- **exit 0**: 최신 상태 → "현재 최신 버전입니다." 출력 후 종료
- **exit 2**: 새 커밋 있음 → 커밋 수와 함께 단계 2 진행
- **exit 1**: 오류 → 오류 내용 출력 후 PM에게 안내

**소스 경로를 찾지 못한 경우 안내:**
```
~/.claude/plugins/known_marketplaces.json 에 'orange-pm' 항목이 없습니다.
처음 설치라면 README의 팀원 설치 가이드를 따르세요.
```

### 단계 2 — PM 확인 요청

새 커밋이 있으면 현재 상태를 보여주고 진행 여부를 묻는다:

```
orange-pm 업데이트 가능
  새 커밋: {N}개
  소스: {source_dir}

업데이트를 진행할까요? [Y/N]
```

PM이 N이면 종료한다.

### 단계 3 — 업데이트 실행

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/update_orange_pm.py"
```

진행 상태를 실시간으로 보여준다:
- "git pull 실행 중..."
- git 출력 그대로 표시 (새 파일, 변경 파일 목록)
- "플러그인 캐시 동기화: N개 경로"

### 단계 4 — 완료 안내

```
✓ orange-pm 업데이트 완료 (vX.X.X)

Claude Code를 재시작하면 새 버전이 적용됩니다.
  Mac: Cmd+Q 후 재실행
  Windows: 창 닫기 후 재실행
```

## 오류 처리

| 상황 | 조치 |
|---|---|
| `known_marketplaces.json` 에 orange-pm 없음 | 팀원 최초 설치 가이드 안내 |
| `.git` 을 찾을 수 없음 | 소스 경로가 git 저장소인지 확인 요청 |
| `git pull` 충돌 | 충돌 메시지 출력, 수동 해소 안내 |
| 네트워크 오류 | git 자격증명·VPN 확인 안내 |

## 최초 설치

가장 간단한 방법 — GitHub 마켓플레이스로 설치:

```
/plugin marketplace add weg-9000/Orange-pm
/plugin install orange-pm@orange-pm
```

git 저장소를 직접 클론해서 로컬 마켓플레이스로 쓰는 방법 (개발/사내 미러용):

```bash
# 1. 저장소 클론 (자신의 fork 또는 미러 주소로)
git clone <저장소 URL> ~/orange-pm

# 2. Claude Code 에 로컬 마켓플레이스 추가
/plugin marketplace add ~/orange-pm
/plugin install orange-pm@orange-pm
```

이후 업데이트는 `/orange-pm:update` 만으로 끝납니다.
