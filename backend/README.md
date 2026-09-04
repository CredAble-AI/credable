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
curl -X POST http://127.0.0.1:8000/v1/sessions/demo \
  -H 'Content-Type: application/json' \
  -d '{"demoProfileId":"small-business"}'

curl http://127.0.0.1:8000/v1/sessions/<sessionId>
```

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
호출합니다. 기본 Demo Adapter는 Frontend Mock과 같은 결과 상태를 사용하되 점수·등급을
생성하지 않습니다. 은행 내부 데이터와 정식 조회 신용정보가 모두 검증된 경우 소상공인은
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

## 검증

```bash
uv run ruff format --check .
uv run ruff check .
uv run pytest
```

## 현재 범위

현재 FastAPI 애플리케이션, liveness/readiness API, Demo 고객 세션, 데이터 출처별 동의와
조회·검증 상태, 보완평가 실행 기반, 합성 자사 상품 카탈로그와 비교 API를 제공합니다. 합성
데이터 출처 상태와 보완평가 상태, 소상공인용 개인화 상품 조건은 기존 Frontend Fixture와
일치합니다. Legacy `/v1/cases/*` 흐름은 제거됐습니다. 실제 평가모델·은행 상품정책·은행 연동과
Frontend의 Backend API 전환은 별도 작업으로 진행합니다.

기존 SQLite 파일에 남아 있을 수 있는 Legacy Case 테이블과 데이터는 보존·삭제 정책이 정해질
때까지 애플리케이션이 자동으로 삭제하지 않습니다.
