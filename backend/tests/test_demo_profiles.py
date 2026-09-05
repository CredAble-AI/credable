from fastapi.testclient import TestClient


def test_list_demo_profiles_returns_supported_session_profiles(
    client: TestClient,
) -> None:
    response = client.get("/v1/demo-profiles")

    assert response.status_code == 200
    assert response.headers["X-Request-ID"].startswith("req_")
    assert response.json() == {
        "dataVersion": "demo-profiles-v3",
        "profiles": [
            {
                "demoProfileId": "small-business",
                "businessBorrowerType": "SOLE_PROPRIETOR",
                "displayName": "개인사업자",
                "description": "개업 초기 소상공인을 예시로 한 개인사업자 합성 Demo 사례",
            },
            {
                "demoProfileId": "startup",
                "businessBorrowerType": "CORPORATION",
                "displayName": "법인사업자",
                "description": "설립 초기 스타트업을 예시로 한 법인사업자 합성 Demo 사례",
            },
        ],
        "demoOnly": True,
    }
