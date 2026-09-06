from fastapi.testclient import TestClient


def test_list_demo_profiles_returns_supported_session_profiles(
    client: TestClient,
) -> None:
    response = client.get("/v1/demo-profiles")

    assert response.status_code == 200
    assert response.headers["X-Request-ID"].startswith("req_")
    assert response.json() == {
        "dataVersion": "demo-profiles-v4",
        "profiles": [
            {
                "demoProfileId": "small-business",
                "businessBorrowerType": "SOLE_PROPRIETOR",
                "displayName": "개인사업자",
                "description": "개업 초기 소상공인을 예시로 한 개인사업자 합성 Demo 사례",
                "scenarioLabel": "정책 경계에 걸린 사례",
                "scenarioSummary": (
                    "기존 평가 구간이 두 정책 경로에 걸쳐 있어 최소 증빙 한 건을 요청하는 흐름을 확인합니다."
                ),
            },
            {
                "demoProfileId": "small-business-stable",
                "businessBorrowerType": "SOLE_PROPRIETOR",
                "displayName": "개인사업자",
                "description": "기존 평가만으로 처리 경로가 확인되는 개인사업자 합성 Demo 사례",
                "scenarioLabel": "추가 증빙이 필요 없는 사례",
                "scenarioSummary": (
                    "기존 평가만으로 하나의 정책 경로가 확인되어 추가 자료를 요청하지 않는 흐름을 확인합니다."
                ),
            },
            {
                "demoProfileId": "startup",
                "businessBorrowerType": "CORPORATION",
                "displayName": "법인사업자",
                "description": "설립 초기 스타트업을 예시로 한 법인사업자 합성 Demo 사례",
                "scenarioLabel": "정책 경계에 걸린 사례",
                "scenarioSummary": (
                    "기존 평가 구간이 두 정책 경로에 걸쳐 있어 최소 증빙 한 건을 요청하는 흐름을 확인합니다."
                ),
            },
            {
                "demoProfileId": "startup-policy-blocked",
                "businessBorrowerType": "CORPORATION",
                "displayName": "법인사업자",
                "description": "대출정책상 제한이 확인된 법인사업자 합성 Demo 사례",
                "scenarioLabel": "대출정책상 제한 사례",
                "scenarioSummary": (
                    "추가 증빙으로 해소할 수 없는 정책상 제한을 안내하고 증빙 수집을 시작하지 않는 흐름을 확인합니다."
                ),
            },
        ],
        "demoOnly": True,
    }


def test_every_demo_profile_covers_a_distinct_policy_boundary_story(
    client: TestClient,
) -> None:
    """The start screen must be able to reach every policy boundary state."""
    profiles = client.get("/v1/demo-profiles").json()["profiles"]

    by_borrower_type: dict[str, set[str]] = {}
    for profile in profiles:
        by_borrower_type.setdefault(profile["businessBorrowerType"], set()).add(
            profile["scenarioLabel"]
        )

    assert set(by_borrower_type) == {"SOLE_PROPRIETOR", "CORPORATION"}
    labels = {label for labels in by_borrower_type.values() for label in labels}
    assert labels == {
        "정책 경계에 걸린 사례",
        "추가 증빙이 필요 없는 사례",
        "대출정책상 제한 사례",
    }
