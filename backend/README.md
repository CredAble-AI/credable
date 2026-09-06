# CredAble Backend

CredAble은 사업자금 대출을 탐색하는 등록 개인사업자와 법인사업자를 대상으로, 기존 CB·SCB 및
은행 평가 이후에도 남은 정책 경계의 불확실성을 최소 증빙으로 확인하는 보완 API 서버입니다.
새로운 신용점수를 생성하거나 기존 대출 신청·거절·보류 이력을 이용 조건으로 삼지 않습니다.
기존 평가가 하나의 정책 경로에 속하면 추가 정보를 요청하지 않고, 여러 경로에 걸릴 때만 현재
판단을 구분하는 데 필요한 증빙을 한 건씩 요청합니다. 검증된 정보만 보완평가에 사용하며 판단이
충분해지면 수집을 중단하고, 불확실성이나 이상 징후가 남으면 자동 결론 없이 심사역 검토로
연결합니다. 생성형 AI는 서버가 확정한 구조화 결과를 설명하는 역할로만 제한하며 신용점수·등급,
증빙 선택, 정책 경로, 승인·부결, 금리와 한도를 생성하거나 변경할 수 없습니다.

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

현재 MVP는 사업자금 대출을 탐색하는 등록 사업자만 대상으로 합니다. 대출·평가 주체는
`SOLE_PROPRIETOR`(개인사업자)와 `CORPORATION`(법인사업자)으로 구분하며 개인 생활자금 대출과
사업자등록 전 예비창업자는 포함하지 않습니다. 소상공인과 스타트업은 법적 유형이 아니라 각각
개업 초기 개인사업자와 설립 초기 법인사업자를 보여주는 합성 Demo 사례입니다.

세션 생성 요청은 `businessBorrowerType`으로 두 사업자 유형 중 하나를 선택할 수 있습니다.
기존 `demoProfileId`는 다른 Fixture가 참조하는 내부 시나리오 키와 기존 Frontend의 호환을 위해
유지하지만, 두 선택자를 동시에 보낼 수는 없습니다. 같은 유형이나 Profile을 다시 요청해도
새로운 세션을 생성하며 생성된 세션은 `sessionId`로 복구할 수 있습니다.

```bash
curl http://127.0.0.1:8000/v1/demo-profiles

curl -X POST http://127.0.0.1:8000/v1/sessions/demo \
  -H 'Content-Type: application/json' \
  -d '{"businessBorrowerType":"SOLE_PROPRIETOR"}'

curl http://127.0.0.1:8000/v1/sessions/<sessionId>
```

`GET /v1/demo-profiles`는 각 사례의 `businessBorrowerType`, 표시명과 설명을 제공합니다. 표시명은
개인사업자·법인사업자이며 소상공인·스타트업은 설명용 사례에만 나타납니다. 응답의
`demoProfileId`, `dataVersion`, `demoOnly`는 Demo 실행과 호환성 확인에만 사용합니다.

세션에는 서버가 확정한 `customerSubject`가 포함됩니다. 고객, 주사업체와 고객-사업체 관계를
각각 `borrowers`, `businesses`, `borrower_business_roles`에 정규화하고
`customer_session_subjects`로 세션과 연결합니다. 출처, 기준일, 데이터 버전과 `demoOnly`를
함께 보존하며 실제 주민·사업자등록번호는 저장하지 않습니다. 현재 값과 코드체계는 모두 합성
Fixture이므로 실제 은행 고객정보나 공식 업종코드로 해석하지 않습니다.

Demo Profile을 읽을 때 서버는 `businessBorrowerType`, 고객의 `borrowerType`, 주사업체의
`legalForm`과 고객-사업체 역할이 서로 일치하는지 검증합니다. 주사업체가 없는 사례는 현재 MVP
카탈로그에 등록할 수 없으므로 사업자등록 전 예비창업자 흐름이 섞이지 않습니다. 개인사업자는
`OWNER`, 법인사업자는 `BORROWER_ENTITY` 관계를 사용합니다. 대표자의 본인확인·동의 권한 모델은
은행 정책 확정이 필요한 후속 범위이며 현재 Demo가 임의로 판단하지 않습니다.

## 은행 보유 계좌·거래 Mock 데이터

`demo_bank_data.json`은 고객이 입력하는 자료가 아니라 은행 내부 Adapter가 제공하는 자행
계좌 데이터의 합성 Fixture입니다. 계좌 마스터, 시점별 잔액, 개별 거래와 세션별 Snapshot을
각각 `bank_accounts`, `bank_account_balances`, `bank_transactions`,
`bank_data_session_snapshots`에 저장합니다. 동일 계좌도 `dataVersion`별로 분리해 이전 세션이
참조한 입력을 보존합니다.

필드 구조는 금융결제원 오픈뱅킹의 잔액·거래내역 항목과 ISO 20022의 계좌 명세 구조에서
공통으로 확인되는 계좌 식별자, 계좌 유형, 통화, 기준시점, 입출금 구분, 금액, 거래 후 잔액을
참고했습니다. 은행별 내부 원장 구조는 같다고 가정하지 않으며 실제 도입 시 Adapter에서 해당
은행의 코드체계로 변환합니다.

Demo에는 2026년 3월부터 8월까지 프로필별 입출금 12건과 8월 말 잔액을 넣었습니다. 실제
계좌번호, 예금주명, 통장 인자내용, 상대방 정보는 저장하지 않습니다. 또한 입금 내역을 매출로
간주하는 `isSalesDeposit` 같은 파생 판단값은 두지 않았습니다. 매출 분류와 집계 규칙은 은행이
보유한 거래코드·가맹점 정산정보와 검증 기준이 확정된 뒤 별도 Feature 계층에서 구현해야 합니다.
현재 원천 Mock 데이터는 신용평가·한도·금리 계산에 사용되지 않습니다.

## 은행 보유 신청·심사·신용평가 이력

`demo_credit_history.json`은 은행 내부에 이미 존재하는 대출 신청, 심사결정과 기존 신용평가
결과를 합성한 Fixture입니다. 신청, 결정, 결정 사유, 신용평가와 평가 사유를 각각
`loan_applications`, `loan_decisions`, `loan_decision_reasons`, `bank_credit_assessments`,
`bank_credit_assessment_reasons`에 정규화하고 `credit_history_session_snapshots`로 세션에
연결합니다. 평가 기준시점, 모델·Feature Set·정책·데이터 버전을 함께 보존합니다.

개인사업자 Demo 사례에는 기존 신청과 결정 이력이 있고, 법인사업자 Demo 사례에는 신청 이력 없이 정기
신용평가 결과만 있습니다. 따라서 기존 거절·보류 고객은 Reason Code를 보조 입력으로 사용할
수 있지만, 신규 대출 탐색 고객도 신청 이력 없이 같은 서비스 흐름에 진입할 수 있습니다.

`DEMO_GRADE_*`, `DEMO_*` Reason Code와 모든 정책·모델 버전은 합성 식별자입니다. 기준평가는
평가 기준시점에 이용할 수 있는 가장 최근의 은행 기존 신용평가를 선택하고,
`sourceAssessment`에 신용평가 ID·등급·Reason Code·모델·Feature Set·정책·데이터 버전을
고정합니다. Demo 불확실성 결과도 프로필이 아닌 이 신용평가 ID에 연결됩니다.

이 연결은 실제 은행 내부점수, 승인 임계값, PD, 승인한도나 금리를 새로 만드는 계산이
아닙니다. 기존 평가가 없거나 선택된 평가에 대응하는 검증된 Demo 규칙이 없으면
불리한 평가를 추정하지 않고 명시적 미완료 상태를 반환합니다. 실제 도입 시 은행별 코드
사전과 신청·심사 원장을 Adapter에서 이 계약으로 변환하고, 신청별 신용정보 조회 목적과
범위는 해당 은행의 동의 정책으로 관리해야 합니다.

## 은행 보유 기존 대출·상환·연체 이력

`demo_loan_history.json`은 고객이 직접 입력하는 자료가 아니라 은행의 대출 원장과 상환 관리
시스템에 존재하는 사실 데이터를 표현한 합성 Fixture입니다. 대출계좌, 상환일정, 실제 상환,
연체 발생·해소 이력을 `loan_accounts`, `loan_repayment_schedules`,
`loan_repayment_events`, `loan_delinquency_events`로 분리하고
`loan_history_session_snapshots`가 세션에서 사용한 `dataVersion`과 기준시점을 고정합니다.

구조는 금융권에서 대출 잔액, 원금·이자 상환, 만기와 연체 상태를 별도 관리하는 원장 개념을
따릅니다. 다만 실제 은행마다 계정계와 여신 사후관리 코드가 다르므로, 운영 연동에서는 은행별
Adapter가 내부 식별자와 상태 코드를 이 공통 계약으로 변환해야 합니다. `productId`와
`sourceTransactionId`는 대응 관계를 확인할 수 있을 때만 연결하고, 알 수 없는 과거 원장의
관계를 임의로 추정하지 않습니다.

Demo의 기존 대출·상환·연체 값은 모두 합성 데이터입니다. 연체일수와 잔액은 발생 사실을
재현하기 위한 원장값일 뿐 위험등급·승인여부·금리·한도를 뜻하지 않습니다. 법인사업자 Demo 사례처럼
기존 대출이 없는 고객은 빈 이력을 그대로 저장하며, 데이터 부재를 불리한 신호로 바꾸지
않습니다. 이 Snapshot은 아직 현재 CredAble 평가에 자동 반영되지 않으며, 은행이 Feature 정의와
검증 기준을 확정한 뒤 별도 Feature 계층에서만 사용해야 합니다.

## 외부 신용정보 보유부채 Snapshot

`demo_credit_exposures.json`은 신용정보회사·신용정보집중기관 조회 결과를 흉내 낸 합성
Fixture입니다. 조회 보고서와 금융기관별 대출잔액, 만기, 상품구분, 담보·보증 구분, 원금·이자
연체 사실을 `credit_exposure_session_snapshots`, `external_credit_exposures`,
`external_credit_delinquencies`, `external_credit_guarantees`에 버전별로 보존합니다.
[금융위원회 기업금융 데이터 인프라 개선방안](https://www.fsc.go.kr/po010106/79146)에서
확인되는 기업대출 잔액, 만기, 담보·보증, 원금·이자 연체 항목을 구조 설계의 기준으로
삼았습니다.

은행 내부 대출 원장과 외부 신용정보에는 동일 계좌가 함께 나타날 수 있으므로 현재 단계에서는
두 출처를 합산한 `totalDebt`를 만들지 않습니다. `sourceRecordId`도 원본 계좌번호가 아닌
제공기관의 불투명 레코드 식별자로 다루며, 실제 도입 시 은행과 신용정보 제공기관이 합의한
중복 식별 규칙이 있어야만 통합 Feature를 생성합니다. 조회 결과가 비어 있어도 위험 신호로
치환하지 않고 유효한 빈 Snapshot으로 보존합니다.

Demo의 금융기관·보증기관 코드, 금액과 연체 이력은 모두 합성 값입니다. 실제 CB 점수,
위험등급, 승인 임계값과 총부채 판단은 포함하지 않습니다. 운영 환경에서는 조회 목적,
제공받는 정보 항목과 동의 효력기간을 은행 정책 및 적용 법령에 맞게 확정해야 하며, 현재의
Demo 동의를 그대로 운영 동의로 사용할 수 없습니다.

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
개인사업자 사례의 출처는 조회·검증 완료, 법인사업자 사례의 고객 제출 자료는 `STALE`, 제휴 외부 데이터는
`FAILED`로 구분합니다. 동의하지 않은 출처는 Adapter를 호출하지 않으며, Fixture에 없는 상태는
값을 만들지 않고 `NO_DATA`로 반환합니다. 원시 금융데이터는 응답·상태·Audit에 저장하지
않습니다.

## Demo 모델 레지스트리와 실행 Guard

`demo_model_registry.json`은 기준평가와 보완평가 Adapter가 반환할 수 있는 모델 버전의 역할,
Feature Set·학습데이터·정책 버전, 검증 상태와 운영 상태를 관리합니다. 평가가 `COMPLETED`를
반환하더라도 모델이 레지스트리에 없거나 역할이 다르거나 `SUSPENDED`이면 결과를 저장하지 않고
명시적인 실패 Reason Code로 전환합니다. 적용한 레지스트리 버전과 상태는 평가 Audit 요약에
남습니다.

현재 모델은 모두 합성 Fixture를 조회하는 `DEMO_ONLY`이며 실제 학습·독립검증·Shadow Test를
완료했다는 뜻이 아닙니다. `RUNNING`/`SUSPENDED`는 수동 운영 상태만 표현합니다. 자동 Kill
Switch의 성능·Calibration·Drift 임계값과 승인권자는 실제 은행의 검증·운영 정책이 확정된 뒤
설정해야 하므로 현재 코드가 임의로 판단하지 않습니다.

## 평가 입력 데이터 계보

평가 실행 시 데이터 출처의 조회 상태만 저장하지 않고, 실제로 생성된 계좌·거래, 은행
신용평가 이력, 대출·상환 이력과 외부 신용정보 Snapshot의 유형, 기준시점, 적재시점,
`dataVersion`과 SHA-256 내용 해시를 `sourceSnapshots`에 함께 고정합니다. 따라서 동일한
`assessmentId`가 어떤 버전의 원천 Snapshot을 참조했는지 확인하고 입력 변경 여부를 추적할 수
있습니다. 평가 시작 시각은 `featureCutoffAt`으로 고정합니다. 기준시점 이후 관측되었거나
적재된 Snapshot은 평가 입력의 `sourceSnapshots`에서 제외하고, 해시·시점 참조만
`excludedSourceSnapshots`에 남겨 차단 사실을 추적합니다.

Snapshot 참조는 원천 데이터 전체를 API 응답이나 Audit 요약에 복제하지 않습니다. 기존 평가
저장 JSON에 `sourceSnapshots`가 없어도 빈 목록으로 복원되므로 DB 마이그레이션 없이 이전
실행 이력을 읽을 수 있습니다.

## 버전 관리형 중립 Feature Snapshot

평가 실행 시 실제 원천 Snapshot이 있으면 계좌·거래·기존 심사·대출·외부 신용정보에서
계산식이 명확한 건수와 금액 합계만 별도 Feature Snapshot으로 고정합니다. Feature마다 원천
유형과 계산 버전을 저장하고, 전체 Feature Snapshot의 내용 해시를 평가 입력에 연결해 같은
원천 버전에서 어떤 값이 계산됐는지 재현할 수 있습니다.

금액은 통화별로 분리하며 은행 내부 대출과 외부 신용정보를 하나의 총부채로 합치지 않습니다.
두 출처에 같은 대출이 중복될 가능성이 있지만 현재는 이를 식별할 은행 매칭 규칙이 정해지지
않았기 때문입니다. 원천이 없는 상태는 `SOURCE_NOT_AVAILABLE`, 조회된 원천에 해당 기록이 없는
상태는 `NO_RECORDS`, 계산 가능한 0건은 `AVAILABLE` 값 0으로 구분합니다. 기준시점 이후의
원천은 값을 계산하지 않고 `SOURCE_AFTER_CUTOFF`로 기록해 미래정보 유입과 사후 데이터 누수를
차단합니다.

이 Feature는 현재 Demo 평가 Adapter의 점수·등급·정책 판단에 사용하지 않습니다. 운영 전에는
은행이 관측기간, 출처 간 중복 제거, 사용 Feature, 위험 방향·변환·가중치를 확정하고 실제
성과라벨로 검증해야 합니다.

## Demo 보완평가 실행 기반

보완평가는 현재 데이터 출처 상태를 고정된 입력 Snapshot으로 저장한 뒤 별도 Adapter를
호출합니다. 은행 내부 데이터와 정식 조회 신용정보가 모두 검증된 경우 개인사업자 사례는
`COMPLETED`, 법인사업자 사례는 `INSUFFICIENT_DATA`를 반환합니다.

```bash
curl http://127.0.0.1:8000/v1/sessions/<sessionId>/assessment

curl -X POST \
  http://127.0.0.1:8000/v1/sessions/<sessionId>/assessment/run
```

실행 이력마다 `assessmentId`, 입력 `inputSnapshotId`, 실행시각, CredAble 모델 버전과
선택된 은행 기존 평가 `sourceAssessment`를 분리해 보존합니다. 두 필수 출처가 준비되지
않았으면 `DEMO_REQUIRED_DATA_NOT_VERIFIED`, 이용 가능한 기존 평가가 없으면
`EXISTING_BANK_ASSESSMENT_NOT_AVAILABLE`을 반환하며,
이는 신용상 불리한 결과가 아닙니다. 모든 분기는 합성 Demo 규칙이고 생성형 AI가 평가값을
생성하지 않습니다.

`COMPLETED` 응답은 단일 점수만 확정하지 않고 `uncertainty`를 함께 제공합니다. 이 계약은
선택적인 점추정치·상하한 구간 또는 가능한 등급 집합, `calibrationMode`와
`calibrationVersion`을 포함합니다. 현재 Demo는 실제 확률 보정을 주장하지 않으며
`RULE_TABLE` 방식의 합성 등급 집합만 반환합니다. 실제 은행 성과라벨로 독립 검증하기 전에는
`CONFORMAL_CALIBRATED`를 사용하지 않습니다. 이전 실행 이력에는 `uncertainty: null`이 적용돼
기존 SQLite JSON 상태를 그대로 읽을 수 있습니다.

## 고객 평가 결과 재확인 요청 API

고객은 완료된 최신 평가 결과에 대해 재확인을 요청할 수 있습니다. 요청 본문에서 평가 ID나
판단 사유를 받지 않고 서버가 최신 완료 결과를 선택하므로, 다른 세션의 평가를 지정하거나
클라이언트가 검토 대상을 바꿀 수 없습니다. 보완평가가 완료됐다면 보완평가를, 그렇지 않으면
기준평가를 대상으로 고정합니다.

```bash
curl http://127.0.0.1:8000/v1/sessions/<sessionId>/assessment/review-request

curl -X POST \
  http://127.0.0.1:8000/v1/sessions/<sessionId>/assessment/review-request
```

요청에는 대상 유형·평가 ID, 요청시각, 데이터·모델·요청 정책 버전과 Snapshot Hash를
보존하고 고객 행위로 Audit을 남깁니다. 같은 평가 결과에 반복 요청하면 기존 요청을 반환해
중복 큐와 중복 Audit을 만들지 않습니다. 완료된 평가가 없으면
`ASSESSMENT_REVIEW_TARGET_NOT_READY`로 차단합니다. 이 기능은 평가값을 다시 계산하거나 금융
판단을 변경하지 않고 은행 심사역 검토 큐에 요청을 추가하는 역할만 수행합니다. 응답의
`processing`은 `PENDING`, `IN_REVIEW`, `COMPLETED` 상태와 고객에게 공개 가능한 결과·처리시각을
제공하며 내부 심사역 식별자는 노출하지 않습니다.

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

최신 정책 경계 판정이 `AMBIGUOUS`이면 해당 경계와 은행 기존 평가의
`sourceAssessment.reasonCodes`에 둘 다 연결된 후보만 비교해 다음 Evidence 한 건을
선택합니다. 선택 결과에는 `sourceCreditAssessmentId`, `informationGapCodes`와
후보가 실제로 맞춰진 `matchedInformationGapCodes`를 남겨 요청 근거를 추적합니다.

`STABLE`이면 `PATH_STABLE`로 추가 요청 없이 종료하고, `POLICY_BLOCKED`이거나 기존
평가 계보·Reason Code 매핑·유효한 후보가 없으면 AI가 증빙을 추측하지 않고
`HUMAN_REVIEW`로 보냅니다. 실제 은행 Reason Code와 인정 증빙 간 매핑은 은행별 여신·정책
담당자가 확정해야 하며, 현재 매핑은 `DEMO_*` 합성 코드로만 구성됩니다.

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

첫 선택은 같은 `boundaryCheckId`, 반복 선택은 같은 `resolutionId`에 대해 저장된 결과를
반환하므로 중복 요청과 중복 Audit을 만들지 않습니다. 보완평가 후 수집 판단이
`MORE_EVIDENCE_REQUIRED`이면 같은 `POST /evidence/next`를 호출해 다음 후보를 선택할 수
있습니다. 서버는 이미 제출한 Evidence 유형을 제외하고 남은 후보 중 한 건만 선택하며,
새로운 유효 후보가 없으면 `NO_NEW_USEFUL_EVIDENCE`와 `HUMAN_REVIEW`로 자동 수집을
중단합니다. 반복 응답의 `resolutionId`는 어떤 수집 판단에서 요청이 발생했는지 나타냅니다.

최신 보완평가·전후 비교·수집 판단의 연결이 완성되기 전에는 이전 요청을 재사용하지 않고
`EVIDENCE_RESOLUTION_NOT_READY`를 반환합니다. 수집이 이미 `RESOLVED` 또는
`HUMAN_REVIEW`로 끝났다면 `EVIDENCE_COLLECTION_CLOSED`를 반환합니다. 실제 후보 목록과
가중치, 최대 요청 횟수는 은행 운영정책 확정이 필요한 항목이며 이번 구현은 임의의 최대
횟수를 두지 않습니다.

## Demo Evidence 제출 상태 API

선택 결과의 `collectionMode`가 `DEMO_FILE_UPLOAD`이면 서버가 제공하는 합성 PDF를 내려받아
실제로 업로드할 수 있습니다. `DEMO_CONNECTION`과 `UNAVAILABLE`도 서버가 반환하므로
Frontend가 Evidence 유형을 보고 수집 방식을 하드코딩하지 않습니다. 서버는 최신
`selectionId`에서 Evidence 유형·출처·수집 방식을 다시 확인하고 클라이언트 판단값을 신뢰하지
않습니다.

```bash
curl http://127.0.0.1:8000/v1/sessions/<sessionId>/evidence/submissions/latest

curl \
  http://127.0.0.1:8000/v1/sessions/<sessionId>/evidence/selections/<selectionId>/submission-option

curl \
  http://127.0.0.1:8000/v1/sessions/<sessionId>/evidence/selections/<selectionId>/consent

curl -X POST \
  http://127.0.0.1:8000/v1/sessions/<sessionId>/evidence/selections/<selectionId>/consent/grant

curl -X POST \
  http://127.0.0.1:8000/v1/sessions/<sessionId>/evidence/selections/<selectionId>/consent/withdraw

curl -OJ \
  http://127.0.0.1:8000/v1/sessions/<sessionId>/evidence/selections/<selectionId>/demo-file/download

curl -X POST \
  http://127.0.0.1:8000/v1/sessions/<sessionId>/evidence/submissions/upload \
  -F 'selectionId=<selectionId>' \
  -F 'file=@최근_매출_입금_요약서_DEMO.pdf;type=application/pdf'

curl -X POST \
  http://127.0.0.1:8000/v1/sessions/<sessionId>/evidence/submissions \
  -H 'Content-Type: application/json' \
  -d '{"selectionId":"<selectionId>","submissionMode":"DEMO_FIXTURE_REFERENCE"}'
```

제출 옵션 API는 현재 선택에 귀속된 Evidence 동의를 매번 다시 확인해 `READY`,
`CONSENT_REQUIRED`, `UNAVAILABLE` 중 하나를 반환하고 Demo 파일 메타데이터와 허용 형식·최대
5MB 정책을 함께 제공합니다. Evidence 동의 API는 서버가 선택한 한 건의 자료에 대해서만
이용 목적, 데이터 항목, 기간과 범위 버전을 제공합니다. 기존 출처 단위 동의와 별도로
관리되므로 `CUSTOMER_SUBMITTED` 출처 동의만으로 파일 다운로드·업로드가 허용되지 않습니다.

파일 다운로드는 동의를 자동 부여하지 않습니다. 현재 `selectionId`의 동의가 `GRANTED`이고
서버 정책의 `scopeVersion`과 일치할 때만 다운로드·업로드할 수 있으며, 아니면
`EVIDENCE_CONSENT_REQUIRED`로 차단합니다. 동의·철회는 Audit에 고객 행위로 기록됩니다.

업로드는 확장자·MIME·`%PDF-` magic bytes·5MB 제한을 먼저 확인하고 실제 binary의 SHA-256을
계산합니다. 형식 오류는 원문을 저장하지 않고 즉시 거부합니다. 형식은 유효하지만 서버 발급
PDF와 해시가 다른 파일은 메타데이터만 제출 이력으로 보존하고, 다음 품질 검증에서 자동평가가
아닌 심사역 검토 경로로 분리합니다. 원본 binary와 PDF 본문은 DB·Audit·로그에 저장하지 않고
서버가 확정한 파일명·크기·MIME·해시·문서 ID만 저장합니다. 같은 `selectionId`와 같은 해시는
기존 제출을 반환하며, 이미 제출된 뒤 다른 파일을 다시 올리면 `EVIDENCE_ALREADY_SUBMITTED`로
차단합니다. 기존 `DEMO_FIXTURE_REFERENCE` JSON API는 호환성을 위해 유지합니다.

## Demo Evidence 품질 검증 API

제출된 Evidence를 출처·최신성·진위·완전성·일관성·조작 위험의 여섯 차원으로 검증합니다.
모든 차원이 `PASSED`일 때만 `ACCEPTED`, `eligibleForReassessment: true`,
`nextAction: RUN_REASSESSMENT`를 반환합니다. 최신성·완전성·일관성 등이 통과하지 못하면
`REJECTED`와 `nextAction: EXCLUDE_EVIDENCE`로 분리합니다. 해시·진위 또는 조작 위험 검사가
명시적으로 `FAILED`이면 `REVIEW_REQUIRED`, `underwriterRequired: true`,
`nextAction: UNDERWRITER_REVIEW`를 반환하고 자동 보완평가를 중단합니다. 단순
`NOT_VERIFIED`는 이상 징후로 과장하지 않고 `REJECTED`로 처리합니다.

```bash
curl \
  http://127.0.0.1:8000/v1/sessions/<sessionId>/evidence/submissions/<submissionId>/quality

curl -X POST \
  http://127.0.0.1:8000/v1/sessions/<sessionId>/evidence/submissions/<submissionId>/quality
```

`DEMO_FILE_UPLOAD` 제출은 Evidence 유형만으로 고정 결과를 고르지 않습니다. 업로드 때 계산한
실제 파일 해시와 서버 발급 문서 ID를 manifest에 다시 연결한 뒤 출처, 기준시점, 필수 항목,
월별 매출·입금 차이와 전체 합계를 검증해 여섯 차원으로 변환합니다. 해시·manifest·제출
Snapshot 중 하나라도 일치하지 않으면 재평가 입력 자격을 주지 않습니다. 이때
`suspicionCodes`는 진위·조작 위험에서 실제로 실패한 코드만 제공하며 `rejectionCodes`에도 함께
포함됩니다. 원본을 폐기한 뒤에도 서버가 저장한 해시와 manifest로 같은 결과를 재현할 수
있습니다. 관리자 증빙부담 API도 `reviewRequiredCount`를 `rejectedCount`와 별도로 집계합니다.
새 품질 검증을 시작할 때 증빙별 동의가 철회됐거나 제출 Snapshot의 동의 ID·범위 버전과
일치하지 않으면 `EVIDENCE_CONSENT_NOT_ACTIVE`로 차단합니다. 이미 저장된 품질 결과는
감사 가능한 과거 이력으로 유지합니다.

기존 `DEMO_FIXTURE_REFERENCE` 제출은 하위 호환을 위해 기존 품질 Fixture를 사용합니다. 같은
`submissionId`를 다시 검증하면 저장된 결과를 반환해 중복 판정과 중복 Audit을 만들지 않습니다.
이번 binary 검증은 서버가 직접 발급한 합성 Demo PDF에 대한 실제 검증이며 임의의 실물
금융문서 진위 판별, 운영 수준 OCR 또는 악성파일 검사를 의미하지 않습니다.

실제 운영 규칙은 은행이 인정하는 발급처, 유효기간, 필수 필드, 교차검증 원천과 조작 탐지
방식이 확정된 뒤 Adapter로 교체해야 합니다. 품질 검증을 통과하지 못한 Evidence는 다음
보완평가 입력으로 사용할 수 없습니다.

## Demo Evidence 기반 보완평가 API

기준평가가 연결된 정책 경계에서 불확실하고, 서버가 선택한 Evidence가 제출·품질
검증을 모두 통과한 경우에만 보완평가를 실행합니다. 기준평가는 덮어쓰지 않고
보완평가를 별도 이력으로 보존합니다.

파일 업로드 제출은 제출 Snapshot에 `evidenceConsentId`와 `consentScopeVersion`을 함께
고정합니다. 보완평가를 새로 실행할 때 해당 동의가 철회됐거나 범위 버전이 달라졌다면
`EVIDENCE_CONSENT_NOT_ACTIVE`로 차단합니다. 이미 생성된 보완평가 Snapshot은 철회로
덮어쓰거나 삭제하지 않습니다. 기존 `DEMO_FIXTURE_REFERENCE` 제출 계약은 하위 호환을 위해
출처 단위 흐름을 유지합니다.

```bash
curl \
  http://127.0.0.1:8000/v1/sessions/<sessionId>/assessment/supplemental

curl -X POST \
  http://127.0.0.1:8000/v1/sessions/<sessionId>/assessment/supplemental/run \
  -H 'Content-Type: application/json' \
  -d '{"submissionId":"<submissionId>"}'
```

보완평가 입력 Snapshot에는 당시 기준평가의 고정된 데이터 출처 상태와 불확실성,
경계 판정·선택·제출·품질 검증 ID, Evidence Snapshot Hash와 버전을 결합합니다.
반복 수집에서는 같은 기준평가와 경계에 연결되고 품질 검증을 통과한 Evidence를 제출
순서대로 `acceptedEvidenceSet`에 누적합니다. `acceptedEvidence`는 이번 실행을 촉발한 최신
항목으로 유지하며, 2차 이후 항목에는 요청 근거인 `resolutionId`도 보존합니다. 응답의
`acceptedEvidenceCount`로 누적된 품질 통과 Evidence 건수를 확인할 수 있습니다.

보완평가도 실행 시작 시각을 별도 `featureCutoffAt`으로 고정합니다. Evidence의 관측·제출·품질
검증 시각 중 하나라도 기준시점 이후이면 `pointInTimeValid=false`로 기록하고 평가 Adapter를
호출하지 않습니다. 실행 결과는 `INSUFFICIENT_DATA/EVIDENCE_AFTER_FEATURE_CUTOFF`로 보존하며,
차단된 Evidence 수를 Audit 요약에 남깁니다. 품질 통과 여부가 시점 유효성을 대신하지 않습니다.

원본 Evidence는 평가 저장소나 Audit에 추가로 복제하지 않습니다. 같은 품질 검증 결과로
재호출하면 기존 보완평가를 반환합니다. 기존 단일 Evidence Snapshot은 조회 시 한 건짜리
누적 집합으로 복원되므로 과거 이력과 호환됩니다.

현재 Demo Fixture는 개인사업자 사례 기준평가의 가능 등급 집합 `DEMO_GRADE_B`, `DEMO_GRADE_C`를
추가 Evidence 반영 후 `DEMO_GRADE_B`로 축소하는 합성 결과만 제공합니다. 실제 등급 개선,
승인 가능성 또는 모델 성능을 의미하지 않으며, 실제 재평가 모델과 성과라벨 검증은 별도
작업입니다. Demo Adapter는 단일 `evidenceType`과 누적 `evidenceTypes` 조합을 구분해 고정된
Fixture 결과만 조회하며, 여러 Evidence를 수치적으로 결합하는 규칙을 임의로 생성하지
않습니다. 기본 외부 정산 Evidence는 품질 Fixture에서 거절되므로 두 건 누적 성공 시나리오는
테스트 전용 합성 Fixture로만 검증합니다.

## Demo 평가 전후 비교 API

기준평가와 보완평가의 불확실성을 비교해 `NARROWED`, `UNCHANGED`, `EXPANDED`,
`SHIFTED`, `NOT_COMPARABLE` 중 하나의 구조적 관계를 반환합니다. 등급 집합과 수치 구간은
각각 독립적으로 비교하며, 보정 방식과 버전이 같을 때만 비교 가능하다고 판단합니다.

```bash
curl \
  http://127.0.0.1:8000/v1/sessions/<sessionId>/assessment/comparison

curl -X POST \
  http://127.0.0.1:8000/v1/sessions/<sessionId>/assessment/comparison
```

응답은 비교 ID, 기준·보완평가 ID, 품질 검증 ID, 전후 불확실성, 모델·보정
버전과 설명 코드를 보존합니다. 같은 보완평가를 재비교하면 기존 결과를 반환해
중복 이력을 만들지 않습니다.

`NARROWED`는 가능한 결과의 범위가 줄었다는 뜻일 뿐, 신용도 개선·승인 가능성 상승을
의미하지 않습니다. 점수 변화, 정책 경로 변경과 최종 금융 판단은 이 API에서 생성하지
않습니다.

## Demo Evidence 수집 종료·이관 API

보완평가의 불확실성을 기존 Demo 정책 경계표로 다시 판정해 Evidence 수집을
종료할지, 계속할지, 심사역에게 이관할지를 결정합니다. 신규 수치 임계값을 추가하지
않고 기존 버전 정책만 사용합니다.

```bash
curl \
  http://127.0.0.1:8000/v1/sessions/<sessionId>/assessment/resolution

curl -X POST \
  http://127.0.0.1:8000/v1/sessions/<sessionId>/assessment/resolution
```

- 한 개 정책 경로로 안정: `RESOLVED`, Evidence 수집 종료, 갱신 결과 표시
- 여전히 두 개 이상 경로에 걸침: `MORE_EVIDENCE_REQUIRED`, 다음 Evidence 수집 필요
- 비교 불가 또는 정책 미설정: `HUMAN_REVIEW`, 자동 수집 중단 후 심사역 이관

결과에는 비교·보완평가 ID, 다음 행동, 수집 중단·심사역 필요 여부, 가능한
Demo 경로와 정책·보정 버전을 보존합니다. 신용 승인·거절을 판단하지 않으며 같은
비교 결과의 중복 판정과 Audit을 만들지 않습니다.

`REQUEST_NEXT_EVIDENCE`이면 기존 `POST /v1/sessions/{sessionId}/evidence/next`로 다음
최소 Evidence를 선택합니다. 이전 제출 유형은 다시 요청하지 않으며 남은 후보가 없으면
심사역 확인 상태로 종료합니다. 최대 요청 횟수는 은행 운영정책 확정이 필요하므로 아직
적용하지 않습니다.

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
`POLICY_NOT_CONFIGURED`를 반환합니다. Demo Adapter는 기존 Frontend Mock에 정의된 개인사업자
사례 조건만 파일에서 불러오며, 정의되지 않은 법인사업자 사례 조건은 값을 만들지 않고
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

## 은행 심사역 검토 큐 API

은행 관리자는 Evidence 품질 결과가 `REVIEW_REQUIRED`인 건과 고객이 평가 결과 재확인을
요청한 건을 최신순으로 조회할 수 있습니다. 이 API는 기존 품질 검증·재확인 요청 이력을 조회
시점에 합치므로 별도의 금융 판단이나 중복 검토 요청을 생성하지 않습니다.

```bash
curl \
  -H 'X-Admin-API-Key: <관리자용-비밀키>' \
  'http://127.0.0.1:8000/v1/admin/underwriter-reviews?limit=50&offset=0'
```

응답에는 결정 가능한 금융 원문 대신 `reviewId`, 세션·Trigger ID, Evidence 유형 또는 평가
대상, 사유 코드, 검토 요청 시점과 데이터·정책 버전만 포함합니다. 기본 조회 개수는 50개이고
최대 100개이며 `offset`으로 다음 구간을 조회합니다. Trigger는 `EVIDENCE_QUALITY`와
`CUSTOMER_ASSESSMENT_REVIEW`를 구분합니다.

심사역은 같은 관리자 인증으로 검토 상세 조회, 접수와 완료 처리를 수행합니다.

```bash
curl \
  -H 'X-Admin-API-Key: <관리자용-비밀키>' \
  http://127.0.0.1:8000/v1/admin/underwriter-reviews/<reviewId>

curl -X POST \
  -H 'X-Admin-API-Key: <관리자용-비밀키>' \
  http://127.0.0.1:8000/v1/admin/underwriter-reviews/<reviewId>/claim

curl -X POST \
  -H 'X-Admin-API-Key: <관리자용-비밀키>' \
  -H 'Content-Type: application/json' \
  -d '{"resultCode":"ASSESSMENT_CONFIRMED"}' \
  http://127.0.0.1:8000/v1/admin/underwriter-reviews/<reviewId>/complete
```

상태는 `PENDING → IN_REVIEW → COMPLETED` 순서만 허용합니다. Evidence Trigger에는
`EVIDENCE_CONFIRMED`, `EVIDENCE_EXCLUDED`, 고객 재확인 Trigger에는
`ASSESSMENT_CONFIRMED`, `CORRECTION_REQUIRED`를 사용할 수 있으며,
`ADDITIONAL_INFORMATION_REQUIRED`, `ESCALATED`는 공통 결과입니다. 유형이 다른 결과 코드는
차단하고 완료된 결과는 변경하지 않습니다. 접수·완료는 심사역 행위로 Audit에 기록되며
자유입력 메모와 원본 금융자료는 저장하지 않습니다.

처리 결과는 검토 이력일 뿐 기존 평가값·품질 결과·대출조건을 자동으로 변경하지 않습니다.
정정이나 추가자료 결과를 실제 평가 흐름에 반영하는 규칙은 은행 정책 확정 후 별도 기능으로
연결해야 합니다. 실제 운영 인증은 Demo API Key와 고정 Demo 심사역 주체가 아닌 SSO/RBAC,
실제 담당자 식별 및 조직별 접근통제로 교체해야 합니다.

## 은행 관리자 Evidence 부담 지표 API

은행 관리자는 세션별 Evidence 요청 부담을 기존 처리 이력에서 조회할 수 있습니다. 별도
집계값을 DB에 저장하지 않고 선택·제출·품질 검증·보완평가·수집 판단 이력을 요청 시점에
교차검증해 계산합니다.

```bash
curl \
  -H 'X-Admin-API-Key: <관리자용-비밀키>' \
  http://127.0.0.1:8000/v1/admin/sessions/<sessionId>/evidence-burden
```

응답은 전체·반복 요청 수, 준비 상태별 요청 수, 제출 대기 수, 품질 검증 통과·탈락 수,
통과하지 못한 품질 차원 수, 보완평가·수집 판단 횟수와 Evidence 유형별 상세를 제공합니다.
`asOf`는 집계에 포함된 가장 최근 이력 시점이며 `measurementVersion`으로 지표 계약을
식별합니다. 원본 Evidence, 내부 선택값과 고객 금융정보는 포함하지 않습니다.

이 API는 부담의 크기를 사실 지표로만 보여주며 과다 요청 여부를 판정하지 않습니다.
`policyThresholdApplied`는 항상 `false`이고, 경고 기준·허용 요청 횟수·고객군별 비교 기준은
은행 운영·공정성 정책이 정해진 후 별도로 적용해야 합니다.

## 검증

통합 검증은 기본 Demo Adapter와 임시 SQLite DB를 사용해 세션 생성부터 데이터 조회, 기준평가,
최소 Evidence 선택·품질 검증·보완평가·전후 비교·수집 종료, 상품 비교와 관리자 조회까지
연결합니다. 같은 DB로 애플리케이션을 다시 생성한 뒤 모든 최신 상태와 Audit·Evidence 부담
지표가 변경 없이 복구되는지도 확인합니다. 테스트의 재시작은 프로세스 재조립과 영속 상태
복구를 검증하며, 실제 배포 환경의 장애 복구·백업 복원 시험을 대신하지는 않습니다.

```bash
uv run ruff format --check .
uv run ruff check .
uv run pytest
```

## 현재 범위

현재 FastAPI 애플리케이션, liveness/readiness API, Demo 고객 세션, 데이터 출처별 기본 동의와 선택된 증빙별 동의,
조회·검증 상태, 기준평가, Demo 정책 경계 판정·반복 최소 증빙 선택·제출·품질 검증·보완평가·전후 비교·수집 종료 판단,
합성 자사 상품 카탈로그·비교 API, 고객 평가 재확인 요청과 관리자 Evidence 부담 지표·심사역 검토 큐를 제공합니다. 합성 데이터 출처 상태와 평가
상태, 개인사업자 사례용 개인화 상품 조건은 기존 Frontend Fixture와 일치합니다. Legacy
`/v1/cases/*` 흐름은 제거됐습니다. 실제 평가모델·은행 상품정책·Evidence 품질 검증·은행
연동은 별도 작업으로 진행합니다. 고객 재확인 요청 이후의 정정정보 수집·품질 검증·재평가 흐름과
생성형 AI 설명 Adapter도 아직 구현 범위에 포함되지 않았으므로, 현재 구조화 Reason Code와 화면
안내문을 실제 생성형 AI 설명 결과로 표현해서는 안 됩니다.

기존 SQLite 파일에 남아 있을 수 있는 Legacy Case 테이블과 데이터는 보존·삭제 정책이 정해질
때까지 애플리케이션이 자동으로 삭제하지 않습니다.
