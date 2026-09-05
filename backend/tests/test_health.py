from fastapi.testclient import TestClient


def test_health_returns_process_status(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "credible-backend",
    }


def test_ready_returns_current_dependency_checks(client: TestClient) -> None:
    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": [
            {
                "name": "application",
                "status": "ok",
            },
            {
                "name": "session_repository",
                "status": "ok",
            },
            {
                "name": "demo_profiles",
                "status": "ok",
            },
            {
                "name": "bank_data_repository",
                "status": "ok",
            },
            {
                "name": "bank_data_catalog",
                "status": "ok",
            },
            {
                "name": "credit_history_repository",
                "status": "ok",
            },
            {
                "name": "credit_history_catalog",
                "status": "ok",
            },
            {
                "name": "loan_history_repository",
                "status": "ok",
            },
            {
                "name": "loan_history_catalog",
                "status": "ok",
            },
            {
                "name": "credit_exposure_repository",
                "status": "ok",
            },
            {
                "name": "credit_exposure_catalog",
                "status": "ok",
            },
            {
                "name": "consent_repository",
                "status": "ok",
            },
            {
                "name": "demo_consent_scopes",
                "status": "ok",
            },
            {
                "name": "data_source_repository",
                "status": "ok",
            },
            {
                "name": "data_source_adapter",
                "status": "ok",
            },
            {
                "name": "feature_snapshot_repository",
                "status": "ok",
            },
            {
                "name": "model_registry_catalog",
                "status": "ok",
            },
            {
                "name": "assessment_repository",
                "status": "ok",
            },
            {
                "name": "assessment_adapter",
                "status": "ok",
            },
            {
                "name": "supplemental_assessment_repository",
                "status": "ok",
            },
            {
                "name": "supplemental_assessment_adapter",
                "status": "ok",
            },
            {
                "name": "assessment_comparison_repository",
                "status": "ok",
            },
            {
                "name": "policy_boundary_repository",
                "status": "ok",
            },
            {
                "name": "policy_boundary_catalog",
                "status": "ok",
            },
            {
                "name": "evidence_resolution_repository",
                "status": "ok",
            },
            {
                "name": "evidence_selection_repository",
                "status": "ok",
            },
            {
                "name": "evidence_candidate_catalog",
                "status": "ok",
            },
            {
                "name": "evidence_submission_repository",
                "status": "ok",
            },
            {
                "name": "evidence_submission_catalog",
                "status": "ok",
            },
            {
                "name": "evidence_quality_repository",
                "status": "ok",
            },
            {
                "name": "evidence_quality_catalog",
                "status": "ok",
            },
            {
                "name": "product_catalog_repository",
                "status": "ok",
            },
            {
                "name": "product_catalog_adapter",
                "status": "ok",
            },
            {
                "name": "product_condition_repository",
                "status": "ok",
            },
            {
                "name": "product_condition_adapter",
                "status": "ok",
            },
        ],
    }


def test_openapi_exposes_health_routes(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/health" in paths
    assert "/ready" in paths
    assert all(not path.startswith("/v1/cases") for path in paths)
    assert "/v1/demo-profiles" in paths
    assert "/v1/sessions/demo" in paths
    assert "/v1/sessions/{session_id}" in paths
    assert "/v1/sessions/{session_id}/consents" in paths
    assert "/v1/sessions/{session_id}/consents/{source_type}/grant" in paths
    assert "/v1/sessions/{session_id}/consents/{source_type}/withdraw" in paths
    assert "/v1/sessions/{session_id}/data-sources" in paths
    assert "/v1/sessions/{session_id}/data-sources/refresh" in paths
    assert "/v1/sessions/{session_id}/assessment" in paths
    assert "/v1/sessions/{session_id}/assessment/run" in paths
    assert "/v1/sessions/{session_id}/assessment/supplemental" in paths
    assert "/v1/sessions/{session_id}/assessment/supplemental/run" in paths
    assert "/v1/sessions/{session_id}/assessment/comparison" in paths
    assert "/v1/sessions/{session_id}/assessment/resolution" in paths
    assert "/v1/admin/sessions/{session_id}/evidence-burden" in paths
    assert "/v1/sessions/{session_id}/assessment/boundary-check" in paths
    assert "/v1/sessions/{session_id}/evidence/next" in paths
    assert "/v1/sessions/{session_id}/evidence/submissions" in paths
    assert "/v1/sessions/{session_id}/evidence/submissions/latest" in paths
    assert "/v1/sessions/{session_id}/evidence/submissions/{submission_id}/quality" in paths
    assert "/v1/sessions/{session_id}/products" in paths
    assert "/v1/sessions/{session_id}/products/refresh" in paths
    assert "/v1/sessions/{session_id}/product-conditions" in paths
    assert "/v1/sessions/{session_id}/product-conditions/query" in paths
    assert "/v1/sessions/{session_id}/comparison" in paths
    assert "/v1/admin/sessions/{session_id}/audit-events" in paths

    security_schemes = response.json()["components"]["securitySchemes"]
    assert security_schemes["AdminApiKey"] == {
        "type": "apiKey",
        "in": "header",
        "name": "X-Admin-API-Key",
    }


def test_removed_legacy_case_routes_return_not_found(client: TestClient) -> None:
    create_response = client.post("/v1/cases/demo", json={"demoCaseId": "borderline"})
    get_response = client.get("/v1/cases/case-demo-borderline")

    assert create_response.status_code == 404
    assert get_response.status_code == 404
