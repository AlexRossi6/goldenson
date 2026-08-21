from fastapi.testclient import TestClient


def _create_workspace(client: TestClient, name: str) -> str:
    response = client.post("/api/workspaces", json={"name": name})
    assert response.status_code == 201
    payload = response.json()
    assert isinstance(payload, dict)
    workspace_id = payload.get("id")
    assert isinstance(workspace_id, str)
    return workspace_id


def _create_page(client: TestClient, workspace_id: str, title: str) -> str:
    response = client.post(
        f"/api/workspaces/{workspace_id}/pages",
        json={"title": title, "parent_page_id": None, "position": 0},
    )
    assert response.status_code == 201
    payload = response.json()
    assert isinstance(payload, dict)
    page_id = payload.get("id")
    assert isinstance(page_id, str)
    return page_id


def test_file_metadata_create_list_get_delete(api_client: TestClient) -> None:
    workspace_id = _create_workspace(api_client, "Files API Workspace")
    page_id = _create_page(api_client, workspace_id, "Attachments")

    create_response = api_client.post(
        f"/api/workspaces/{workspace_id}/files",
        json={
            "name": "notes.pdf",
            "storage_key": f"{workspace_id}/notes.pdf",
            "mime_type": "application/pdf",
            "size": 123456,
            "page_id": page_id,
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()

    list_response = api_client.get(f"/api/workspaces/{workspace_id}/files")
    assert list_response.status_code == 200
    assert len(list_response.json()["items"]) == 1

    get_response = api_client.get(f"/api/files/{created['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["storage_key"] == f"{workspace_id}/notes.pdf"

    delete_response = api_client.delete(f"/api/files/{created['id']}")
    assert delete_response.status_code == 204


def test_file_metadata_rejects_cross_workspace_page(api_client: TestClient) -> None:
    workspace_a = _create_workspace(api_client, "A")
    workspace_b = _create_workspace(api_client, "B")
    page_in_b = _create_page(api_client, workspace_b, "B page")

    response = api_client.post(
        f"/api/workspaces/{workspace_a}/files",
        json={
            "name": "bad.pdf",
            "storage_key": f"{workspace_a}/bad.pdf",
            "mime_type": "application/pdf",
            "size": 42,
            "page_id": page_in_b,
        },
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "BAD_REQUEST"
