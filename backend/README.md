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

## 검증

```bash
uv run ruff format --check .
uv run ruff check .
uv run pytest
```

## 현재 범위

이번 초기 구성에서는 FastAPI 애플리케이션과 liveness/readiness API만 제공합니다.
Case Repository, Demo Case, 외부 Snapshot과 Agent 의존성은 후속 기능에서 `/ready` 검사에 추가합니다.
