# CredAble Backend

CredAble의 추가 증빙 기반 신용 재심사 API 서버입니다.

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

## Demo Case API

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

현재 FastAPI 애플리케이션, liveness/readiness API, Case Repository와 4개 Demo Case를
제공합니다. 외부 Snapshot과 Agent 의존성은 후속 기능에서 `/ready` 검사에 추가합니다.
