# CredAble 협업 및 GitHub 규칙

이 문서는 CredAble 프론트엔드와 백엔드에서 사람과 코딩 에이전트가 함께 사용하는 공통 개발 규칙이다.

## 1. 기본 원칙

- 기본 브랜치는 `main`이며 직접 커밋과 직접 푸시를 금지한다.
- 모든 변경은 짧게 유지되는 작업 브랜치와 Pull Request를 통해 병합한다.
- 하나의 PR은 하나의 목적만 다룬다.
- 기능 하나마다 별도의 작업 브랜치 하나와 Pull Request 하나를 생성한다.
- 서로 다른 기능·버그·문서 목적을 같은 브랜치나 PR에 묶지 않는다.
- 하나의 기능에 필요한 프론트엔드·백엔드·API 계약 변경은 같은 브랜치와 PR에 포함할 수 있다.
- 코드 변경에는 가능한 범위에서 테스트를 포함한다.
- 리뷰 가능한 크기를 우선하며 대규모 변경은 여러 PR로 나눈다.
- 프론트엔드와 백엔드는 같은 Git 규칙을 사용한다.
- API 계약을 변경하는 PR은 양쪽 영향과 호환성을 반드시 확인한다.

## 2. 작업 영역 표시

모든 Issue와 PR에는 변경 영역을 하나 이상 표시한다.

- `frontend`: 화면, 컴포넌트, 상태, 스타일, 프론트 API 클라이언트
- `backend`: API, 도메인 서비스, 저장소, DB, 외부 연동
- `contract`: 요청·응답 스키마, enum, 오류 코드, 공유 타입
- `data-ai`: 데이터 처리, 모델 인터페이스, Agent와 평가
- `docs-infra`: 문서, CI/CD, 배포 및 저장소 설정

## 3. 표준 작업 흐름

```bash
git switch main
git pull --ff-only
git switch -c feat/evidence-quality-api

# 구현 및 검증
git status --short
git diff --check

git add <변경한-파일>
git commit -m "feat: add evidence quality endpoint"
git push -u origin feat/evidence-quality-api
```

푸시 후 GitHub에서 PR을 만들고 최소 1명의 리뷰를 받은 뒤 병합한다.

## 4. 브랜치 규칙

형식은 `<type>/<short-description>`을 사용한다. 설명은 영문 소문자와 kebab-case로 작성한다.

| Type | 용도 | 예시 |
| --- | --- | --- |
| `feat` | 기능 추가 | `feat/eligibility-engine` |
| `fix` | 버그 수정 | `fix/point-in-time-check` |
| `refactor` | 동작 변경 없는 구조 개선 | `refactor/case-repository` |
| `test` | 테스트 추가·수정 | `test/router-scenarios` |
| `docs` | 문서 변경 | `docs/github-workflow` |
| `chore` | 설정·도구·의존성 관리 | `chore/pytest-config` |
| `hotfix` | 긴급 운영 수정 | `hotfix/audit-write-failure` |

프론트엔드·백엔드 구분이 유용하면 설명에 포함한다.

```text
feat/frontend-case-dashboard
feat/backend-evidence-quality
fix/contract-risk-response
```

이슈 번호가 있으면 `feat/123-eligibility-engine`처럼 포함할 수 있다.

금지 사항:

- 개인 이름만 사용한 브랜치
- `test`, `temp`, `work`처럼 목적을 알 수 없는 이름
- 하나의 브랜치에서 서로 무관한 작업 수행
- 공유 브랜치 강제 푸시

## 5. 커밋 규칙

Conventional Commits 형식을 사용한다.

```text
<type>(optional-scope): <summary>
```

사용 가능한 주요 타입:

- `feat`: 새로운 기능
- `fix`: 버그 수정
- `refactor`: 기능 변화 없는 코드 개선
- `test`: 테스트 변경
- `docs`: 문서 변경
- `chore`: 설정, 빌드, 의존성 변경
- `perf`: 성능 개선
- `ci`: CI/CD 변경

예시:

```text
feat(evidence): add candidate utility calculation
fix(policy): block routing when hard stop exists
test(router): cover suspicious evidence path
docs: document pull request workflow
feat(frontend): add evidence request screen
feat(backend): add evidence quality endpoint
fix(contract): align risk response enum
```

작성 원칙:

- 제목은 명령형으로 간결하게 작성하고 마침표를 붙이지 않는다.
- 한 커밋에는 하나의 논리적 변경만 담는다.
- 포맷팅과 기능 변경을 가능하면 분리한다.
- 테스트가 실패하거나 미완성인 상태를 정상 커밋처럼 숨기지 않는다.
- `WIP`, `update`, `fix stuff`처럼 의미 없는 메시지는 사용하지 않는다.

## 6. Pull Request 규칙

PR 제목도 Conventional Commits 형식을 사용한다.

```text
feat(evidence): add adaptive evidence recommendation
```

PR 본문에는 반드시 다음을 포함한다.

- 왜 필요한 변경인지
- 무엇을 변경했는지
- 어떤 검증을 실행했고 결과가 어땠는지
- API, DB, 보안, 개인정보, 정책 판단에 미치는 영향
- UI 변경 시 스크린샷, API 변경 시 요청·응답 예시
- 후속 작업이나 알려진 제한사항
- 변경 영역이 프론트엔드, 백엔드 또는 양쪽인지
- API 계약 변경 시 양쪽 적용 상태와 호환 전략

PR 크기 권장 기준:

- 가능하면 변경 파일 15개 이하, 순수 변경 400줄 이하로 유지한다.
- 기준을 넘으면 PR 본문에 분리하지 못한 이유를 적는다.
- 생성 파일, 잠금 파일, 스키마 변경처럼 줄 수가 큰 기계적 변경은 예외로 볼 수 있다.

## 7. 프론트엔드·백엔드 계약 규칙

- 백엔드 API 스키마와 프론트엔드 타입을 일치시킨다.
- 계약 변경 시 Mock, Fixture, API 예시와 양쪽 테스트를 함께 갱신한다.
- 필드 삭제·이름 변경·타입 변경은 breaking change로 취급한다.
- enum, nullable 필드, 날짜·시간대, 오류 코드와 HTTP 상태를 명시한다.
- 한쪽을 먼저 배포해야 하면 하위 호환 가능한 순서와 제거 시점을 PR에 적는다.
- 화면은 서버의 정책·위험도·경로 결정을 임의로 다시 계산하지 않는다.

## 8. 리뷰 및 병합

- 작성자가 아닌 팀원 1명 이상의 승인을 권장한다.
- 리뷰 의견은 수정, 근거 있는 반론, 후속 이슈 중 하나로 처리한다.
- 필수 검증이 실패한 상태에서는 병합하지 않는다.
- 기본 병합 방식은 **Squash and merge**로 한다.
- Squash 커밋 제목은 PR 제목과 동일한 Conventional Commits 형식을 유지한다.
- 병합 후 원격과 로컬 작업 브랜치를 정리한다.

## 9. 변경별 체크사항

### Backend

- 요청·응답 스키마와 상태 코드가 문서 및 테스트와 일치하는가?
- 적격성, 증빙 추천, 위험도, 정책과 경로 결정 책임이 분리돼 있는가?
- `demoOnly`, 기준시점, 입력 스냅샷과 버전 정보가 보존되는가?
- 외부 연동 실패 시 fallback과 오류가 명시되는가?

### Frontend

- 서버 판단값을 클라이언트에서 임의로 재계산하지 않는가?
- 로딩, 빈 상태, 오류, 재시도와 접근성을 확인했는가?
- API 계약 변경을 반영했는가?

### Full stack / API 계약

- 프론트엔드 요청과 백엔드 스키마가 실제로 일치하는가?
- Mock과 실제 API의 응답 형태가 같은가?
- 한쪽만 배포돼도 기존 기능이 깨지지 않는가?
- 핵심 사용자 흐름을 처음부터 끝까지 확인했는가?

### Data / AI

- 데이터 출처, 동의 범위와 기준시점이 기록되는가?
- 실제 정보와 Fixture·Mock·Snapshot이 명확히 구분되는가?
- LLM 출력이 정책 또는 최종 의사결정 값을 덮어쓰지 않는가?
- 검증되지 않은 성능 수치나 금융 결과를 주장하지 않는가?

## 10. 보안 및 저장소 위생

- `.env`, 비밀키, 토큰, 자격증명과 개인정보를 커밋하지 않는다.
- 예시는 합성 데이터나 익명화된 Fixture만 사용한다.
- 대용량 바이너리 파일은 필요한 경우 팀과 합의하고 Git LFS 사용 여부를 결정한다.
- 의존성 추가 시 목적과 라이선스·보안 영향을 PR에 적는다.
- 로그와 오류 메시지에 민감한 원문 Evidence를 남기지 않는다.

## 11. 완료 체크리스트

- [ ] 작업 브랜치에서 진행했다.
- [ ] 이 브랜치와 PR에는 하나의 기능 또는 수정 목적만 포함했다.
- [ ] 변경 영역을 frontend/backend/contract/data-ai/docs-infra 중에서 표시했다.
- [ ] 변경 범위가 PR 목적과 일치한다.
- [ ] 관련 테스트·린트·타입 검사를 실행했다.
- [ ] `git diff --check`를 통과했다.
- [ ] 문서와 API 예시를 필요한 만큼 갱신했다.
- [ ] API 변경 시 프론트엔드와 백엔드의 호환성을 확인했다.
- [ ] 민감정보와 불필요한 생성물이 포함되지 않았다.
- [ ] Conventional Commits 형식으로 커밋했다.
- [ ] 원격 브랜치에 푸시했다.
- [ ] PR 템플릿을 작성하고 리뷰를 요청했다.

