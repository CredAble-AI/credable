# CredAble Backend

CredAble의 은행용 보완 신용평가·자사 대출상품 비교 API 서버입니다.

## 요구사항

- Python 3.12
- uv

## 설치

```bash
cd backend
uv sync
```

## 개발 서버 실행

```bash
uv run uvicorn app.main:app --reload
```

- API 문서: <http://127.0.0.1:8000/docs>
- ReDoc: <http://127.0.0.1:8000/redoc>
- 상태 확인: <http://127.0.0.1:8000/health>
- 준비 상태: <http://127.0.0.1:8000/ready>

## Demo 고객 세션 API

Demo Profile은 소상공인과 스타트업 예시만 제공합니다. 같은 Profile을 다시 요청해도 새로운
세션을 생성하며, 생성된 세션은 `sessionId`로 복구할 수 있습니다.

```bash
curl http://127.0.0.1:8000/v1/demo-profiles

curl -X POST http://127.0.0.1:8000/v1/sessions/demo \
  -H 'Content-Type: application/json' \
  -d '{"demoProfileId":"small-business"}'

curl http://127.0.0.1:8000/v1/sessions/<sessionId>
```

Frontend는 `GET /v1/demo-profiles` 응답의 `demoProfileId`를 세션 생성 요청에 사용합니다.
응답에는 표시용 이름·설명과 `dataVersion`, `demoOnly`가 포함되므로 Profile 목록을 별도로
하드코딩하지 않습니다.

세션에는 평가점수·등급·한도·금리를 포함하지 않습니다. 현재 단계에서는 합성 Demo Profile,
`demoOnly`, 데이터 버전과 생성 시각만 저장합니다.

## Demo 동의 상태 API

동의는 데이터 출처별로 조회·등록·철회합니다. 현재 Demo 설정에는 은행의 필수·선택 정책이
없으므로 `required`는 `null`이며, 실제 동의 문구·보존기간과 원본 금융정보는 저장하지
않습니다.

```bash
curl http://127.0.0.1:8000/v1/sessions/<sessionId>/consents

curl -X POST \
  http://127.0.0.1:8000/v1/sessions/<sessionId>/consents/BANK_INTERNAL/grant

curl -X POST \
  http://127.0.0.1:8000/v1/sessions/<sessionId>/consents/BANK_INTERNAL/withdraw
```

지원하는 출처는 `BANK_INTERNAL`, `CREDIT_INFORMATION`, `CUSTOMER_SUBMITTED`,
`EXTERNAL_CONNECTED`입니다. 동의 상태와 변경 Audit만 저장하며 실제 데이터 연결은 후속
기능에서 구현합니다.

## Demo 데이터 조회·검증 상태 API

데이터 출처별 조회·검증 상태는 동의 상태와 분리해 제공합니다. 동의하지 않은 출처는
`CONSENT_REQUIRED`, 동의 후 조회 전에는 `NOT_REQUESTED`로 표시합니다.

```bash
curl http://127.0.0.1:8000/v1/sessions/<sessionId>/data-sources

curl -X POST \
  http://127.0.0.1:8000/v1/sessions/<sessionId>/data-sources/refresh
```

기본 Demo Adapter는 Frontend Mock과 같은 합성 조회·검증 상태를 프로필별로 제공합니다.
소상공인 출처는 조회·검증 완료, 스타트업의 고객 제출 자료는 `STALE`, 제휴 외부 데이터는
`FAILED`로 구분합니다. 동의하지 않은 출처는 Adapter를 호출하지 않으며, Fixture에 없는 상태는
값을 만들지 않고 `NO_DATA`로 반환합니다. 원시 금융데이터는 응답·상태·Audit에 저장하지
않습니다.

## Demo 보완평가 실행 기반

보완평가는 현재 데이터 출처 상태를 고정된 입력 Snapshot으로 저장한 뒤 별도 Adapter를
호출합니다. 은행 내부 데이터와 정식 조회 신용정보가 모두 검증된 경우 소상공인은
`COMPLETED`, 스타트업은 `INSUFFICIENT_DATA`를 반환합니다.

```bash
curl http://127.0.0.1:8000/v1/sessions/<sessionId>/assessment

curl -X POST \
  http://127.0.0.1:8000/v1/sessions/<sessionId>/assessment/run
```

실행 이력마다 `assessmentId`, 입력 `inputSnapshotId`, 실행시각과 모델 버전을 분리해
보존합니다. 두 필수 출처가 준비되지 않았으면 `DEMO_REQUIRED_DATA_NOT_VERIFIED`를 반환하며,
이는 신용상 불리한 결과가 아닙니다. 모든 분기는 합성 Demo 규칙이고 생성형 AI가 평가값을
생성하지 않습니다.

`COMPLETED` 응답은 단일 점수만 확정하지 않고 `uncertainty`를 함께 제공합니다. 이 계약은
선택적인 점추정치·상하한 구간 또는 가능한 등급 집합, `calibrationMode`와
`calibrationVersion`을 포함합니다. 현재 Demo는 실제 확률 보정을 주장하지 않으며
`RULE_TABLE` 방식의 합성 등급 집합만 반환합니다. 실제 은행 성과라벨로 독립 검증하기 전에는
`CONFORMAL_CALIBRATED`를 사용하지 않습니다. 이전 실행 이력에는 `uncertainty: null`이 적용돼
기존 SQLite JSON 상태를 그대로 읽을 수 있습니다.

## Demo 정책 경계 판정 API

정책 경계 판정은 완료된 기준평가의 가능한 등급 집합을 버전이 고정된 Demo 정책표와
대조합니다. 평가 범위 전체가 같은 경로에 속하면 `STABLE`, 둘 이상의 경로에 걸치면
`AMBIGUOUS`, 정책이 구성되지 않아 안전하게 판단할 수 없으면 `POLICY_BLOCKED`를 반환합니다.

```bash
curl http://127.0.0.1:8000/v1/sessions/<sessionId>/assessment/boundary-check

curl -X POST \
  http://127.0.0.1:8000/v1/sessions/<sessionId>/assessment/boundary-check
```

현재 정책표의 `DEMO_PATH_*`와 `DEMO_BOUNDARY_*`는 흐름 검증용 합성 식별자이며 실제
승인·거절·보류 기준을 뜻하지 않습니다. 수치 구간 또는 알 수 없는 등급처럼 정책표에 없는
입력은 임의의 경로로 보내지 않고 `POLICY_BLOCKED`와 심사역 확인 필요 상태로 종료합니다.
판정마다 평가·입력 Snapshot·보정·정책 버전과 요약 Audit을 저장하며 같은 버전의 입력은 같은
판정 결과를 만듭니다.

## Demo 최소 증빙 선택 API

최신 정책 경계 판정이 `AMBIGUOUS`이면 해당 경계를 해소할 수 있는 후보만 비교해 다음
Evidence 한 건을 선택합니다. `STABLE`이면 `PATH_STABLE`로 추가 요청 없이 종료하고,
`POLICY_BLOCKED`이거나 유효한 후보가 없으면 임의 선택하지 않고 심사역 확인 상태로 보냅니다.

```bash
curl http://127.0.0.1:8000/v1/sessions/<sessionId>/evidence/next

curl -X POST \
  http://127.0.0.1:8000/v1/sessions/<sessionId>/evidence/next
```

Demo 후보 순서는 `경계 해소값 × 예상 품질 신뢰도 - 고객 노력 - 개인정보 민감도 - 획득 지연
- 획득 비용`으로 계산합니다. 모든 입력값은 실제 은행 통계가 아닌 합성 정규화 값이며,
후보 종류·값·선택 정책 버전은 파일 기반 정책표에서 관리합니다. 고객용 응답에는 내부
가중치나 선택값을 노출하지 않고 요청 자료·출처·준비 상태·설명 코드만 제공합니다. 선택값과
선택 Evidence 유형은 보호된 관리자 Audit에만 남깁니다.

같은 `boundaryCheckId`에 대한 재호출은 저장된 결과를 반환해 중복 요청과 중복 Audit을 만들지
않습니다. 실제 후보 목록·가중치·최대 요청 횟수는 은행 운영정책 확정이 필요한 항목이므로
현재 버전에서는 Demo 후보 한 건 선택까지만 구현합니다.

## Demo Evidence 제출 상태 API

선택된 Evidence는 원문 파일 대신 Demo Fixture 참조를 사용해 제출 상태만 등록합니다. 서버는
클라이언트가 보낸 Evidence 유형을 신뢰하지 않고 최신 `selectionId`에서 유형과 출처를 다시
확인합니다.

```bash
curl http://127.0.0.1:8000/v1/sessions/<sessionId>/evidence/submissions/latest

curl -X POST \
  http://127.0.0.1:8000/v1/sessions/<sessionId>/evidence/submissions \
  -H 'Content-Type: application/json' \
  -d '{"selectionId":"<selectionId>","submissionMode":"DEMO_FIXTURE_REFERENCE"}'
```

응답과 DB에는 제출 ID·Evidence 유형·출처·관측시점·데이터 버전·Snapshot Hash만 저장합니다.
Fixture의 내부 참조 문자열이나 원본 금융자료는 저장·응답·Audit에 포함하지 않습니다. 같은
`selectionId`를 다시 제출하면 기존 상태를 반환해 중복 제출과 중복 Audit을 만들지 않습니다.

실제 파일 업로드는 허용하지 않습니다. 지원 파일 형식·용량, 암호화 저장, 악성파일 검사,
보존·삭제 기간과 접근권한은 은행 보안·개인정보 정책 결정 후 별도 Adapter와 저장소로
구현해야 합니다. 다음 단계의 품질 검증은 현재 등록된 메타데이터와 별도 Demo 품질 Fixture를
사용합니다.

## 자사 상품 카탈로그 API

상품 카탈로그는 세션별 최신 상태 조회와 새로고침을 지원합니다. 기본 Demo Adapter는
Frontend Mock과 같은 합성 자사 상품 4개를 파일 기반 카탈로그에서 불러옵니다.

```bash
curl http://127.0.0.1:8000/v1/sessions/<sessionId>/products

curl -X POST \
  http://127.0.0.1:8000/v1/sessions/<sessionId>/products/refresh
```

상품 계약은 공식 가입대상, 공개 최대한도, 공개 연 금리 범위, 기간, 상환방식, 공식 출처와
은행 신청 연결 정보를 포함합니다. 금액·금리는 부동소수점 오차를 피하기 위해 문자열로
표현합니다. 모든 상품·조건은 기능 흐름 검증용 합성 값이며 실제 은행 상품이 아닙니다.
개인화 조건과 추천·적합도·우선순위 필드는 포함하지 않습니다.

## 상품별 조건 조회 API

상품별 조건 조회는 최신 카탈로그·평가·데이터 상태 Snapshot을 은행 정책 Adapter에 전달하고
상품별 결과를 독립적으로 저장합니다. 서비스 계층은 자격·한도·금리를 계산하지 않습니다.

```bash
curl http://127.0.0.1:8000/v1/sessions/<sessionId>/product-conditions

curl -X POST \
  http://127.0.0.1:8000/v1/sessions/<sessionId>/product-conditions/query
```

카탈로그가 없으면 `CATALOG_UNAVAILABLE`, 상품은 있지만 정책이 없으면 상품별
`POLICY_NOT_CONFIGURED`를 반환합니다. Demo Adapter는 기존 Frontend Mock에 정의된 소상공인
조건만 파일에서 불러오며, 정의되지 않은 스타트업 조건은 값을 만들지 않고
`POLICY_NOT_CONFIGURED`로 남깁니다. 보완평가가 완료되지 않은 세션에도 개인화 값을 제공하지
않습니다. 한 상품의 조회 실패는 다른 상품 결과를 숨기지 않으며, 개인화 조건에는 항상 최종
은행 심사가 필요하다는 표시를 포함합니다. 추천·적합도·최적 상품 필드는 제공하지 않습니다.

## 상품 비교 통합 응답 API

비교 응답은 최신 카탈로그의 공개 조건과 같은 카탈로그 Snapshot에서 조회한 개인화 조건을
상품별로 결합합니다. 오래된 조건 결과는 연결하지 않으며 공개 조건만 표시합니다.

```bash
curl http://127.0.0.1:8000/v1/sessions/<sessionId>/comparison
```

Backend는 카탈로그 원본 순서를 유지하고 실제 정렬은 수행하지 않습니다. 대신 응답 데이터에
존재하는 공개·개인화 한도와 최저금리의 정렬 가능 여부를 제공합니다. 값이 없는 항목은
Frontend에서 마지막에 배치해야 하며, 원본 순서에는 추천·순위 의미가 없습니다.

## 은행 관리자 감사 이력 API

은행 관리자는 세션에서 수행된 처리 단계를 최신순으로 조회할 수 있습니다. 서버 실행 전에
관리자 API 키를 환경변수로 설정하고 요청 헤더로 전달합니다.

```bash
export CREDABLE_ADMIN_API_KEY='<관리자용-비밀키>'

curl \
  -H 'X-Admin-API-Key: <관리자용-비밀키>' \
  'http://127.0.0.1:8000/v1/admin/sessions/<sessionId>/audit-events?limit=50'
```

응답에는 처리 단계·시각·요청 ID·입력 Snapshot Hash·데이터/모델/정책 버전과 결과 요약만
포함하며 원본 금융데이터는 제공하지 않습니다. 기본 조회 개수는 50개, 최대 100개이며 다음
페이지는 응답의 `nextCursor`를 같은 이름의 `cursor` Query Parameter로 전달합니다. API 키가
설정되지 않은 서버는 관리자 요청을 허용하지 않습니다.

현재 API 키 방식은 Demo용입니다. 실제 은행 연동에서는 SSO/RBAC와 은행별 데이터 격리로
교체해야 하며, 관리자 조회 행위 자체의 감사 기록과 이력 보존·삭제 정책은 아직 포함하지
않습니다.

## 검증

```bash
uv run ruff format --check .
uv run ruff check .
uv run pytest
```

## 현재 범위

현재 FastAPI 애플리케이션, liveness/readiness API, Demo 고객 세션, 데이터 출처별 동의와
조회·검증 상태, 보완평가 실행 기반, Demo 정책 경계 판정·최소 증빙 선택·제출 상태, 합성
자사 상품 카탈로그와 비교 API를 제공합니다. 합성 데이터 출처 상태와 보완평가 상태,
소상공인용 개인화 상품 조건은 기존 Frontend Fixture와 일치합니다. Legacy `/v1/cases/*`
흐름은 제거됐습니다. 실제 평가모델·은행 상품정책·은행 연동과 Frontend의 Backend API
전환은 별도 작업으로 진행합니다.

기존 SQLite 파일에 남아 있을 수 있는 Legacy Case 테이블과 데이터는 보존·삭제 정책이 정해질
때까지 애플리케이션이 자동으로 삭제하지 않습니다.
