from fastapi.testclient import TestClient

from app.adapters.assessment_adapter import (
    DemoAssessmentAdapter,
    DemoSupplementalAssessmentAdapter,
)
from app.adapters.data_source_adapter import DemoDataSourceAdapter
from app.adapters.product_catalog_adapter import DemoProductCatalogAdapter
from app.adapters.product_condition_adapter import DemoProductConditionAdapter
from app.core.config import settings
from app.repositories.session_repository import SqliteCustomerSessionRepository
from app.schemas.audit import AuditStage
from app.schemas.consent import ConsentSourceType
from app.services.assessment_service import AssessmentService, SupplementalAssessmentService
from app.services.data_source_service import DataSourceService
from app.services.product_catalog_service import ProductCatalogService
from app.services.product_condition_service import ProductConditionService


def configure_demo_adapters(
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    product_catalog_service: ProductCatalogService,
    product_condition_service: ProductConditionService,
) -> None:
    data_source_service.adapter = DemoDataSourceAdapter(settings.demo_data_sources_path)
    assessment_service.adapter = DemoAssessmentAdapter(settings.demo_assessments_path)
    product_catalog_service.adapter = DemoProductCatalogAdapter(settings.demo_products_path)
    product_condition_service.adapter = DemoProductConditionAdapter(
        settings.demo_product_conditions_path
    )


def create_session(client: TestClient, demo_profile_id: str) -> str:
    response = client.post(
        "/v1/sessions/demo",
        json={"demoProfileId": demo_profile_id},
    )
    assert response.status_code == 201
    return response.json()["sessionId"]


def grant_sources(
    client: TestClient,
    session_id: str,
    source_types: tuple[ConsentSourceType, ...],
) -> None:
    for source_type in source_types:
        response = client.post(f"/v1/sessions/{session_id}/consents/{source_type.value}/grant")
        assert response.status_code == 200


def test_small_business_demo_flow_reaches_partial_comparison(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    product_catalog_service: ProductCatalogService,
    product_condition_service: ProductConditionService,
    session_repository: SqliteCustomerSessionRepository,
) -> None:
    configure_demo_adapters(
        data_source_service,
        assessment_service,
        product_catalog_service,
        product_condition_service,
    )
    session_id = create_session(client, "small-business")
    grant_sources(
        client,
        session_id,
        (
            ConsentSourceType.BANK_INTERNAL,
            ConsentSourceType.CREDIT_INFORMATION,
        ),
    )

    data_response = client.post(f"/v1/sessions/{session_id}/data-sources/refresh")
    assessment_response = client.post(f"/v1/sessions/{session_id}/assessment/run")
    catalog_response = client.post(f"/v1/sessions/{session_id}/products/refresh")
    condition_response = client.post(f"/v1/sessions/{session_id}/product-conditions/query")
    comparison_response = client.get(f"/v1/sessions/{session_id}/comparison")

    assert data_response.status_code == 200
    data_sources = {item["sourceType"]: item for item in data_response.json()["dataSources"]}
    assert data_sources["BANK_INTERNAL"]["verificationStatus"] == "VERIFIED"
    assert data_sources["CREDIT_INFORMATION"]["verificationStatus"] == "VERIFIED"
    assert data_sources["CUSTOMER_SUBMITTED"]["retrievalStatus"] == "CONSENT_REQUIRED"

    assert assessment_response.json()["assessment"]["status"] == "COMPLETED"
    assert (
        assessment_response.json()["assessment"]["modelVersion"]
        == "demo-small-business-assessment-v1"
    )
    assert catalog_response.json()["catalog"]["status"] == "AVAILABLE"
    assert len(catalog_response.json()["catalog"]["products"]) == 4
    assert condition_response.json()["query"]["status"] == "PARTIAL"

    comparison = comparison_response.json()
    assert comparison["status"] == "PARTIAL"
    assert len(comparison["items"]) == 4
    items = {item["productId"]: item for item in comparison["items"]}
    assert items["demo-working-capital"]["personalizedConditions"]["maxAmount"] == {
        "amount": "24000000",
        "currency": "KRW",
    }
    assert items["demo-daily-bridge"]["conditionStatus"] == "PUBLIC_ONLY"
    assert items["demo-steady-business"]["conditionStatus"] == "INSUFFICIENT_DATA"
    assert items["demo-balance-partner"]["conditionStatus"] == "QUERY_FAILED"
    assert "recommend" not in comparison_response.text.lower()
    assert "rank" not in comparison_response.text.lower()
    assert "best" not in comparison_response.text.lower()

    events = session_repository.list_audit_events(session_id)
    assert [event.stage for event in events] == [
        AuditStage.SESSION_CREATED,
        AuditStage.CONSENT_GRANTED,
        AuditStage.CONSENT_GRANTED,
        AuditStage.DATA_SOURCE_REFRESHED,
        AuditStage.DATA_SOURCE_REFRESHED,
        AuditStage.ASSESSMENT_RUN,
        AuditStage.PRODUCT_CATALOG_REFRESHED,
        AuditStage.PRODUCT_CONDITIONS_QUERIED,
    ]
    assert events[-3].model_version == "demo-small-business-assessment-v1"
    assert events[-1].policy_version == "demo-policy-v1"
    assert all(event.output_summary["demoOnly"] is True for event in events)


def test_corporate_demo_flow_stops_collecting_once_the_route_is_stable(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    supplemental_assessment_service: SupplementalAssessmentService,
    product_catalog_service: ProductCatalogService,
    product_condition_service: ProductConditionService,
) -> None:
    configure_demo_adapters(
        data_source_service,
        assessment_service,
        product_catalog_service,
        product_condition_service,
    )
    supplemental_assessment_service.adapter = DemoSupplementalAssessmentAdapter(
        settings.demo_supplemental_assessments_path
    )
    session_id = create_session(client, "startup")
    grant_sources(client, session_id, tuple(ConsentSourceType))

    data_response = client.post(f"/v1/sessions/{session_id}/data-sources/refresh")
    assessment_response = client.post(f"/v1/sessions/{session_id}/assessment/run")
    boundary_response = client.post(f"/v1/sessions/{session_id}/assessment/boundary-check")
    selection_response = client.post(f"/v1/sessions/{session_id}/evidence/next")
    client.post(f"/v1/sessions/{session_id}/products/refresh")
    condition_response = client.post(f"/v1/sessions/{session_id}/product-conditions/query")
    comparison_response = client.get(f"/v1/sessions/{session_id}/comparison")

    data_sources = {item["sourceType"]: item for item in data_response.json()["dataSources"]}
    assert data_sources["CUSTOMER_SUBMITTED"]["verificationStatus"] == "STALE"
    assert data_sources["EXTERNAL_CONNECTED"]["retrievalStatus"] == "RETRIEVED"
    assert data_sources["EXTERNAL_CONNECTED"]["verificationStatus"] == "VERIFIED"
    assessment = assessment_response.json()["assessment"]
    assert assessment["status"] == "COMPLETED"
    assert assessment["modelVersion"] == "demo-corporate-assessment-v1"
    assert assessment["uncertainty"]["gradeSet"] == ["DEMO_GRADE_B", "DEMO_GRADE_C"]
    assert boundary_response.json()["boundaryCheck"]["decision"]["status"] == "AMBIGUOUS"
    selection = selection_response.json()["selection"]
    assert selection["status"] == "SELECTED"
    # Corporations are asked for corporate information, not a sole proprietor's
    # settlement feed, and more than one candidate applied.
    assert selection["selectedEvidence"]["evidenceType"] == (
        "EXTERNAL_CONNECTED_CORPORATE_ACCOUNT_ACTIVITY"
    )
    assert selection["evaluatedCandidateCount"] == 3

    submission_response = client.post(
        f"/v1/sessions/{session_id}/evidence/submissions",
        json={
            "selectionId": selection["selectionId"],
            "submissionMode": "DEMO_FIXTURE_REFERENCE",
        },
    )
    assert submission_response.status_code == 200
    submission = submission_response.json()["submission"]
    quality_response = client.post(
        f"/v1/sessions/{session_id}/evidence/submissions/{submission['submissionId']}/quality"
    )
    assert quality_response.status_code == 200
    assert quality_response.json()["quality"]["status"] == "ACCEPTED"

    supplemental_response = client.post(
        f"/v1/sessions/{session_id}/assessment/supplemental/run",
        json={"submissionId": submission["submissionId"]},
    )
    assert supplemental_response.status_code == 200
    assert client.post(f"/v1/sessions/{session_id}/assessment/comparison").status_code == 200
    resolution_response = client.post(f"/v1/sessions/{session_id}/assessment/resolution")

    assert resolution_response.status_code == 200
    resolution = resolution_response.json()["resolution"]
    assert resolution["status"] == "RESOLVED"
    assert resolution["stopEvidenceCollection"] is True
    assert resolution["underwriterRequired"] is False

    # 계약·주문 내역 후보가 남아 있어도 경로가 안정되면 더 요청하지 않는다.
    closed = client.post(f"/v1/sessions/{session_id}/evidence/next")
    assert closed.status_code == 409
    assert closed.json()["error"]["code"] == "EVIDENCE_COLLECTION_CLOSED"
    assert client.get("/v1/admin/underwriter-reviews").json()["totalCount"] == 0

    conditions = condition_response.json()["query"]
    assert conditions["status"] == "COMPLETED"
    assert {item["status"] for item in conditions["conditions"]} == {"POLICY_NOT_CONFIGURED"}
    assert all(item["personalizedMaxAmount"] is None for item in conditions["conditions"])

    comparison = comparison_response.json()
    assert comparison["status"] == "PUBLIC_ONLY"
    assert len(comparison["items"]) == 4
    assert all(item["personalizedConditions"] is None for item in comparison["items"])
    assert all(item["demoOnly"] is True for item in comparison["items"])


def test_complete_demo_journey_connects_evidence_products_and_admin(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    supplemental_assessment_service: SupplementalAssessmentService,
    product_catalog_service: ProductCatalogService,
    product_condition_service: ProductConditionService,
) -> None:
    configure_demo_adapters(
        data_source_service,
        assessment_service,
        product_catalog_service,
        product_condition_service,
    )
    supplemental_assessment_service.adapter = DemoSupplementalAssessmentAdapter(
        settings.demo_supplemental_assessments_path
    )
    session_id = create_session(client, "small-business")
    grant_sources(
        client,
        session_id,
        (
            ConsentSourceType.BANK_INTERNAL,
            ConsentSourceType.CREDIT_INFORMATION,
        ),
    )

    assert client.post(f"/v1/sessions/{session_id}/data-sources/refresh").status_code == 200
    baseline_response = client.post(f"/v1/sessions/{session_id}/assessment/run")
    boundary_response = client.post(f"/v1/sessions/{session_id}/assessment/boundary-check")
    selection_response = client.post(f"/v1/sessions/{session_id}/evidence/next")

    assert baseline_response.status_code == 200
    assert baseline_response.json()["assessment"]["uncertainty"]["gradeSet"] == [
        "DEMO_GRADE_B",
        "DEMO_GRADE_C",
    ]
    assert boundary_response.status_code == 200
    assert boundary_response.json()["boundaryCheck"]["decision"]["status"] == "AMBIGUOUS"
    assert selection_response.status_code == 200
    selection = selection_response.json()["selection"]
    assert selection["iteration"] == 1
    assert selection["selectedEvidence"]["evidenceType"] == (
        "CUSTOMER_SUBMITTED_RECENT_REVENUE_SUMMARY"
    )

    submission_response = client.post(
        f"/v1/sessions/{session_id}/evidence/submissions",
        json={
            "selectionId": selection["selectionId"],
            "submissionMode": "DEMO_FIXTURE_REFERENCE",
        },
    )
    assert submission_response.status_code == 200
    submission = submission_response.json()["submission"]
    quality_response = client.post(
        f"/v1/sessions/{session_id}/evidence/submissions/{submission['submissionId']}/quality"
    )
    assert quality_response.status_code == 200
    assert quality_response.json()["quality"]["status"] == "ACCEPTED"

    supplemental_response = client.post(
        f"/v1/sessions/{session_id}/assessment/supplemental/run",
        json={"submissionId": submission["submissionId"]},
    )
    comparison_response = client.post(f"/v1/sessions/{session_id}/assessment/comparison")
    resolution_response = client.post(f"/v1/sessions/{session_id}/assessment/resolution")

    assert supplemental_response.status_code == 200
    supplemental = supplemental_response.json()["supplementalAssessment"]
    assert supplemental["acceptedEvidenceCount"] == 1
    assert supplemental["uncertainty"]["gradeSet"] == ["DEMO_GRADE_B"]
    assert comparison_response.status_code == 200
    assert comparison_response.json()["comparison"]["uncertaintyChange"] == "NARROWED"
    assert resolution_response.status_code == 200
    resolution = resolution_response.json()["resolution"]
    assert resolution["status"] == "RESOLVED"
    assert resolution["stopEvidenceCollection"] is True
    assert resolution["nextAction"] == "SHOW_UPDATED_RESULTS"

    assert client.post(f"/v1/sessions/{session_id}/products/refresh").status_code == 200
    conditions_response = client.post(f"/v1/sessions/{session_id}/product-conditions/query")
    products_response = client.get(f"/v1/sessions/{session_id}/comparison")
    assert conditions_response.status_code == 200
    assert conditions_response.json()["query"]["status"] == "PARTIAL"
    assert products_response.status_code == 200
    assert len(products_response.json()["items"]) == 4

    burden_response = client.get(
        f"/v1/admin/sessions/{session_id}/evidence-burden",
    )
    audit_response = client.get(
        f"/v1/admin/sessions/{session_id}/audit-events",
        params={"limit": 100},
    )
    assert burden_response.status_code == 200
    burden = burden_response.json()
    assert burden["evidenceRequestCount"] == 1
    assert burden["submissionCount"] == 1
    assert burden["acceptedCount"] == 1
    assert burden["supplementalAssessmentCount"] == 1
    assert burden["latestResolutionStatus"] == "RESOLVED"
    assert burden["collectionStopped"] is True
    assert burden["policyThresholdApplied"] is False

    assert audit_response.status_code == 200
    stages = [event["stage"] for event in reversed(audit_response.json()["events"])]
    assert stages == [
        "SESSION_CREATED",
        "CONSENT_GRANTED",
        "CONSENT_GRANTED",
        "DATA_SOURCE_REFRESHED",
        "DATA_SOURCE_REFRESHED",
        "ASSESSMENT_RUN",
        "POLICY_BOUNDARY_CHECKED",
        "EVIDENCE_SELECTED",
        "EVIDENCE_SUBMITTED",
        "EVIDENCE_QUALITY_CHECKED",
        "SUPPLEMENTAL_ASSESSMENT_RUN",
        "ASSESSMENT_COMPARED",
        "EVIDENCE_COLLECTION_RESOLVED",
        "PRODUCT_CATALOG_REFRESHED",
        "PRODUCT_CONDITIONS_QUERIED",
    ]


def test_stable_demo_case_finishes_without_requesting_evidence(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    product_catalog_service: ProductCatalogService,
    product_condition_service: ProductConditionService,
) -> None:
    configure_demo_adapters(
        data_source_service,
        assessment_service,
        product_catalog_service,
        product_condition_service,
    )
    session_id = create_session(client, "small-business-stable")
    grant_sources(
        client,
        session_id,
        (ConsentSourceType.BANK_INTERNAL, ConsentSourceType.CREDIT_INFORMATION),
    )
    assert client.post(f"/v1/sessions/{session_id}/data-sources/refresh").status_code == 200
    assert client.post(f"/v1/sessions/{session_id}/assessment/run").status_code == 200

    response = client.post(f"/v1/sessions/{session_id}/assessment/boundary-check")

    assert response.status_code == 200
    decision = response.json()["boundaryCheck"]["decision"]
    assert decision["status"] == "STABLE"
    assert decision["possibleRoutes"] == ["DEMO_PATH_1"]
    assert decision["stopReason"] == "PATH_STABLE"
    assert decision["underwriterRequired"] is False

    selection = client.post(f"/v1/sessions/{session_id}/evidence/next").json()["selection"]
    assert selection["status"] == "NOT_REQUIRED"
    assert selection["selectedEvidence"] is None
    assert selection["underwriterRequired"] is False


def test_policy_blocked_demo_case_explains_the_restriction_without_collecting_evidence(
    client: TestClient,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    product_catalog_service: ProductCatalogService,
    product_condition_service: ProductConditionService,
) -> None:
    configure_demo_adapters(
        data_source_service,
        assessment_service,
        product_catalog_service,
        product_condition_service,
    )
    session_id = create_session(client, "startup-policy-blocked")
    grant_sources(
        client,
        session_id,
        (ConsentSourceType.BANK_INTERNAL, ConsentSourceType.CREDIT_INFORMATION),
    )
    assert client.post(f"/v1/sessions/{session_id}/data-sources/refresh").status_code == 200
    assert client.post(f"/v1/sessions/{session_id}/assessment/run").status_code == 200

    response = client.post(f"/v1/sessions/{session_id}/assessment/boundary-check")

    assert response.status_code == 200
    decision = response.json()["boundaryCheck"]["decision"]
    assert decision["status"] == "POLICY_BLOCKED"
    assert decision["restrictionCode"] == "DEMO_POLICY_RESTRICTION_ACTIVE_DELINQUENCY"
    assert decision["followUpCodes"] == [
        "DEMO_FOLLOW_UP_RESOLVE_DELINQUENCY",
        "DEMO_FOLLOW_UP_BRANCH_CONSULTATION",
    ]
    # A confirmed restriction is explained to the customer, not queued for review.
    assert decision["underwriterRequired"] is False

    selection = client.post(f"/v1/sessions/{session_id}/evidence/next").json()["selection"]
    assert selection["status"] == "POLICY_BLOCKED"
    assert selection["selectedEvidence"] is None
    assert selection["evaluatedCandidateCount"] == 0
    assert selection["underwriterRequired"] is False
