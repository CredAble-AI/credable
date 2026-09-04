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

현재 FastAPI 애플리케이션, liveness/readiness API, Demo 고객 세션 Repository와 두 개의
합성 Demo Profile을 제공합니다. 기존 Case Repository와 4개 Demo Case는 호환성을 위해
유지합니다. 외부 데이터 연결, 보완 평가와 상품 조건 조회는 후속 기능입니다.
