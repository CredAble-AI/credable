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

## Legacy Demo Case API

```bash
curl -X POST http://127.0.0.1:8000/v1/cases/demo \
  -H 'Content-Type: application/json' \
  -d '{"demoCaseId":"borderline"}'

curl http://127.0.0.1:8000/v1/cases/case-demo-borderline
```

Demo Case 원본은 `app/data/demo_cases.json`, 실행 중 Case와 Audit 상태는
Repository 인터페이스 뒤의 `data/credable.db`에 분리하여 저장합니다.
모든 Demo Case 데이터는 합성 데이터이며 동일 `demoCaseId` 요청은 같은 Case를 반환합니다.

## 검증

```bash
uv run ruff format --check .
uv run ruff check .
uv run pytest
```

## 현재 범위

현재 FastAPI 애플리케이션, liveness/readiness API, Demo 고객 세션과 데이터 출처별 동의
상태 API를 제공합니다. 기존 Case Repository와 4개 Demo Case는 호환성을 위해 유지합니다.
실제 데이터 연결·검증, 보완 평가와 상품 조건 조회는 후속 기능입니다.
