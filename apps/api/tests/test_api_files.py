from pathlib import Path

import pytest
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


def test_upload_download_list_and_delete_file(api_client: TestClient, tmp_path: Path) -> None:
    workspace_id = _create_workspace(api_client, "Files API Workspace")
    page_id = _create_page(api_client, workspace_id, "Attachments")
    content = b"local notes\n"

    create_response = api_client.post(
        f"/api/workspaces/{workspace_id}/files",
        files={"upload": ("notes.md", content, "text/markdown")},
        data={"page_id": page_id},
    )
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["name"] == "notes.md"
    assert created["size"] == len(content)
    assert created["mime_type"] == "text/markdown"
    assert "storage_key" not in created

    list_response = api_client.get(f"/api/workspaces/{workspace_id}/files")
    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["name"] == "notes.md"

    file_id = created["id"]
    download_response = api_client.get(f"/api/files/{file_id}/download")
    assert download_response.status_code == 200
    assert download_response.content == content
    assert download_response.headers["content-type"].startswith("text/markdown")
    assert "notes.md" in download_response.headers["content-disposition"]

    delete_response = api_client.delete(f"/api/files/{file_id}")
    assert delete_response.status_code == 204
    assert api_client.get(f"/api/files/{file_id}").status_code == 404
    assert not any(path.is_file() for path in (tmp_path / "files").rglob("*"))


def test_file_download_isolated_by_file_id_and_missing_content_is_reported(
    api_client: TestClient,
) -> None:
    workspace_a = _create_workspace(api_client, "A")
    workspace_b = _create_workspace(api_client, "B")
    upload_response = api_client.post(
        f"/api/workspaces/{workspace_a}/files",
        files={"upload": ("private.txt", b"private", "text/plain")},
    )
    file_id = upload_response.json()["id"]

    assert api_client.get(f"/api/workspaces/{workspace_b}/files").json()["items"] == []
    assert api_client.get(f"/api/files/{file_id}/download").content == b"private"


def test_file_upload_rejects_oversized_content(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from goldenson_api.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "max_upload_size", 3)
    workspace_id = _create_workspace(api_client, "Limited Files")

    response = api_client.post(
        f"/api/workspaces/{workspace_id}/files",
        files={"upload": ("large.txt", b"1234", "text/plain")},
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"


def test_file_upload_rejects_cross_workspace_page(api_client: TestClient) -> None:
    workspace_a = _create_workspace(api_client, "A")
    workspace_b = _create_workspace(api_client, "B")
    page_in_b = _create_page(api_client, workspace_b, "B page")

    response = api_client.post(
        f"/api/workspaces/{workspace_a}/files",
        files={"upload": ("bad.txt", b"bad", "text/plain")},
        data={"page_id": page_in_b},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "BAD_REQUEST"


def test_page_attachments_are_scoped_and_survive_page_deletion(api_client: TestClient) -> None:
    workspace_id = _create_workspace(api_client, "Attachment Scope")
    page_a = _create_page(api_client, workspace_id, "A")
    page_b = _create_page(api_client, workspace_id, "B")

    upload_a = api_client.post(
        f"/api/workspaces/{workspace_id}/files",
        files={"upload": ("a.txt", b"A", "text/plain")},
        data={"page_id": page_a},
    )
    upload_b = api_client.post(
        f"/api/workspaces/{workspace_id}/files",
        files={"upload": ("b.txt", b"B", "text/plain")},
        data={"page_id": page_b},
    )
    assert upload_a.status_code == 201
    assert upload_b.status_code == 201

    page_a_files = api_client.get(f"/api/pages/{page_a}/files")
    page_b_files = api_client.get(f"/api/pages/{page_b}/files")
    assert [item["name"] for item in page_a_files.json()["items"]] == ["a.txt"]
    assert [item["name"] for item in page_b_files.json()["items"]] == ["b.txt"]

    file_id = upload_a.json()["id"]
    assert api_client.delete(f"/api/pages/{page_a}").status_code == 204
    detached = api_client.get(f"/api/files/{file_id}")
    assert detached.status_code == 200
    assert detached.json()["page_id"] is None
    assert api_client.get(f"/api/files/{file_id}/download").content == b"A"
