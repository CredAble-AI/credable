from fastapi.testclient import TestClient


def test_list_demo_profiles_returns_supported_session_profiles(
    client: TestClient,
) -> None:
    response = client.get("/v1/demo-profiles")

    assert response.status_code == 200
    assert response.headers["X-Request-ID"].startswith("req_")
    assert response.json() == {
        "dataVersion": "demo-profiles-v2",
        "profiles": [
            {
                "demoProfileId": "small-business",
                "displayName": "소상공인 Demo",
                "description": "소상공인 고객 흐름을 확인하기 위한 합성 Demo Profile",
            },
            {
                "demoProfileId": "startup",
                "displayName": "스타트업 Demo",
                "description": "스타트업 고객 흐름을 확인하기 위한 합성 Demo Profile",
            },
        ],
        "demoOnly": True,
    }
