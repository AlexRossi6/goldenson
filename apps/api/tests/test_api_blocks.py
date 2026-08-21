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


def _create_block(
    client: TestClient,
    page_id: str,
    payload: dict[str, object],
) -> dict[str, object]:
    response = client.post(f"/api/pages/{page_id}/blocks", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert isinstance(body, dict)
    return body


def test_block_create_list_update_delete(api_client: TestClient) -> None:
    workspace_id = _create_workspace(api_client, "Blocks API Workspace")
    page_id = _create_page(api_client, workspace_id, "Blocks Page")

    _ = _create_block(
        api_client,
        page_id,
        {"type": "todo", "position": 1, "content": {"text": "Later", "checked": False}},
    )
    first = _create_block(
        api_client,
        page_id,
        {"type": "paragraph", "position": 0, "content": {"text": "First content"}},
    )

    list_response = api_client.get(f"/api/pages/{page_id}/blocks")
    assert list_response.status_code == 200
    blocks = list_response.json()["items"]
    assert [block["position"] for block in blocks] == [0, 1]
    assert blocks[0]["content"] == {"text": "First content"}

    update_response = api_client.patch(
        f"/api/blocks/{first['id']}",
        json={
            "type": "quote",
            "position": 2,
            "content": {"text": "Updated"},
            "version": first["version"],
        },
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["type"] == "quote"
    assert updated["position"] == 2
    assert updated["content"] == {"text": "Updated"}

    delete_response = api_client.delete(f"/api/blocks/{updated['id']}")
    assert delete_response.status_code == 204


def test_block_concurrency_conflict(api_client: TestClient) -> None:
    workspace_id = _create_workspace(api_client, "Block Concurrency")
    page_id = _create_page(api_client, workspace_id, "Blocks")
    block = _create_block(
        api_client,
        page_id,
        {"type": "paragraph", "position": 0, "content": {"text": "v1"}},
    )
    block_id = block.get("id")
    version = block.get("version")
    assert isinstance(block_id, str)
    assert isinstance(version, int)

    first_update = api_client.patch(
        f"/api/blocks/{block_id}",
        json={"content": {"text": "v2"}, "version": version},
    )
    assert first_update.status_code == 200

    stale_update = api_client.patch(
        f"/api/blocks/{block_id}",
        json={"content": {"text": "stale"}, "version": version},
    )
    assert stale_update.status_code == 409
    assert stale_update.json()["error"]["code"] == "CONCURRENCY_CONFLICT"

    list_response = api_client.get(f"/api/pages/{page_id}/blocks")
    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["content"] == {"text": "v2"}
