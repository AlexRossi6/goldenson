from fastapi.testclient import TestClient


def test_workspace_crud_endpoints(api_client: TestClient) -> None:
    create_response = api_client.post("/api/workspaces", json={"name": "API Workspace"})
    assert create_response.status_code == 201
    created = create_response.json()

    list_response = api_client.get("/api/workspaces")
    assert list_response.status_code == 200
    listed = list_response.json()["items"]
    assert any(item["id"] == created["id"] for item in listed)

    get_response = api_client.get(f"/api/workspaces/{created['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["name"] == "API Workspace"


def test_get_missing_workspace_returns_404(api_client: TestClient) -> None:
    response = api_client.get("/api/workspaces/0198bcf0-2da3-7acc-8d2a-a5f356e09862")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
