from fastapi.testclient import TestClient


def _create_workspace(client: TestClient, name: str) -> str:
    response = client.post("/api/workspaces", json={"name": name})
    assert response.status_code == 201
    payload = response.json()
    assert isinstance(payload, dict)
    workspace_id = payload.get("id")
    assert isinstance(workspace_id, str)
    return workspace_id


def _create_page(
    client: TestClient,
    workspace_id: str,
    title: str,
    position: int,
    parent_page_id: str | None = None,
) -> dict[str, object]:
    response = client.post(
        f"/api/workspaces/{workspace_id}/pages",
        json={
            "title": title,
            "parent_page_id": parent_page_id,
            "position": position,
        },
    )
    assert response.status_code == 201
    payload = response.json()
    assert isinstance(payload, dict)
    return payload


def test_page_create_list_get_update_delete(api_client: TestClient) -> None:
    workspace_id = _create_workspace(api_client, "Pages API Workspace")
    root = _create_page(api_client, workspace_id, "Root", 0)
    root_id = root.get("id")
    assert isinstance(root_id, str)
    child = _create_page(api_client, workspace_id, "Child", 0, root_id)

    list_response = api_client.get(f"/api/workspaces/{workspace_id}/pages")
    assert list_response.status_code == 200
    titles = [item["title"] for item in list_response.json()["items"]]
    assert titles == ["Root", "Child"]

    child_id = child.get("id")
    assert isinstance(child_id, str)
    get_response = api_client.get(f"/api/pages/{child_id}")
    assert get_response.status_code == 200
    assert get_response.json()["parent_page_id"] == root_id

    child_version = child.get("version")
    assert isinstance(child_version, int)

    update_response = api_client.patch(
        f"/api/pages/{child_id}",
        json={"title": "Child Updated", "position": 1, "version": child_version},
    )
    assert update_response.status_code == 200
    updated_child = update_response.json()
    assert updated_child["title"] == "Child Updated"
    assert updated_child["version"] == child_version + 1

    updated_child_id = updated_child.get("id")
    assert isinstance(updated_child_id, str)
    delete_response = api_client.delete(f"/api/pages/{updated_child_id}")
    assert delete_response.status_code == 204


def test_invalid_parent_relationships(api_client: TestClient) -> None:
    workspace_id = _create_workspace(api_client, "Parent Validation")
    other_workspace_id = _create_workspace(api_client, "Other Workspace")

    parent = _create_page(api_client, workspace_id, "Parent", 0)
    foreign_parent = _create_page(api_client, other_workspace_id, "Foreign Parent", 0)
    parent_id = parent.get("id")
    parent_version = parent.get("version")
    foreign_parent_id = foreign_parent.get("id")
    assert isinstance(parent_id, str)
    assert isinstance(parent_version, int)
    assert isinstance(foreign_parent_id, str)

    bad_parent = api_client.post(
        f"/api/workspaces/{workspace_id}/pages",
        json={
            "title": "Bad Parent",
            "parent_page_id": "0198bcf0-2da3-7acc-8d2a-a5f356e09862",
            "position": 0,
        },
    )
    assert bad_parent.status_code == 400
    assert bad_parent.json()["error"]["code"] == "BAD_REQUEST"

    cross_workspace_parent = api_client.post(
        f"/api/workspaces/{workspace_id}/pages",
        json={"title": "Cross Workspace", "parent_page_id": foreign_parent_id, "position": 1},
    )
    assert cross_workspace_parent.status_code == 400
    assert cross_workspace_parent.json()["error"]["code"] == "BAD_REQUEST"

    self_parent = api_client.patch(
        f"/api/pages/{parent_id}",
        json={"parent_page_id": parent_id, "version": parent_version},
    )
    assert self_parent.status_code == 400
    assert self_parent.json()["error"]["code"] == "BAD_REQUEST"


def test_circular_hierarchy_is_rejected(api_client: TestClient) -> None:
    workspace_id = _create_workspace(api_client, "Cycle Validation")
    a_page = _create_page(api_client, workspace_id, "A", 0)
    a_page_id = a_page.get("id")
    assert isinstance(a_page_id, str)
    b_page = _create_page(api_client, workspace_id, "B", 0, a_page_id)
    b_page_id = b_page.get("id")
    assert isinstance(b_page_id, str)
    c_page = _create_page(api_client, workspace_id, "C", 0, b_page_id)
    c_page_id = c_page.get("id")
    assert isinstance(c_page_id, str)
    a_page_version = a_page.get("version")
    assert isinstance(a_page_version, int)

    cycle_response = api_client.patch(
        f"/api/pages/{a_page_id}",
        json={"parent_page_id": c_page_id, "version": a_page_version},
    )
    assert cycle_response.status_code == 400
    assert cycle_response.json()["error"]["code"] == "BAD_REQUEST"


def test_delete_page_with_children_conflicts(api_client: TestClient) -> None:
    workspace_id = _create_workspace(api_client, "Delete Conflict")
    parent = _create_page(api_client, workspace_id, "Parent", 0)
    parent_id = parent.get("id")
    assert isinstance(parent_id, str)
    _ = _create_page(api_client, workspace_id, "Child", 0, parent_id)

    response = api_client.delete(f"/api/pages/{parent_id}")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICT"


def test_page_concurrency_conflict(api_client: TestClient) -> None:
    workspace_id = _create_workspace(api_client, "Concurrency Pages")
    page = _create_page(api_client, workspace_id, "Page", 0)
    page_id = page.get("id")
    version = page.get("version")
    assert isinstance(page_id, str)
    assert isinstance(version, int)

    first_update = api_client.patch(
        f"/api/pages/{page_id}",
        json={"title": "First", "version": version},
    )
    assert first_update.status_code == 200

    stale_update = api_client.patch(
        f"/api/pages/{page_id}",
        json={"title": "Stale", "version": version},
    )
    assert stale_update.status_code == 409
    assert stale_update.json()["error"]["code"] == "CONCURRENCY_CONFLICT"

    latest = api_client.get(f"/api/pages/{page_id}")
    assert latest.status_code == 200
    assert latest.json()["title"] == "First"
