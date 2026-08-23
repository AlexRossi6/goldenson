import pytest
from fastapi.testclient import TestClient

from goldenson_api.retrieval.service import (
    RetrievalResult,
    RetrievedSource,
    WorkspaceRetrievalService,
)


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


def test_workspace_search_preserves_result_provenance(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = api_client.post("/api/workspaces", json={"name": "Search Workspace"}).json()

    async def search(
        _service: WorkspaceRetrievalService,
        workspace_id: str,
        query: str,
        limit: int,
    ) -> RetrievalResult:
        assert workspace_id == workspace["id"]
        assert query == "local inference notes"
        assert limit == 8
        return RetrievalResult(
            context="Local inference details",
            sources=[
                RetrievedSource(
                    kind="block",
                    title="Local AI",
                    snippet="Compare Ollama and llama.cpp.",
                    page_id="0198bcf0-2da3-7acc-8d2a-a5f356e09862",
                    block_id="0198bcf0-2da3-7acc-8d2a-a5f356e09863",
                    score=0.9,
                ),
                RetrievedSource(
                    kind="file",
                    title="benchmarks.md",
                    snippet="benchmarks.md",
                    page_id=None,
                    file_id="0198bcf0-2da3-7acc-8d2a-a5f356e09864",
                    score=0.4,
                ),
            ],
        )

    monkeypatch.setattr(WorkspaceRetrievalService, "search", search)

    response = api_client.get(
        f"/api/workspaces/{workspace['id']}/search",
        params={"query": "local inference notes"},
    )

    assert response.status_code == 200
    sources = response.json()["sources"]
    assert sources[0]["block_id"] == "0198bcf0-2da3-7acc-8d2a-a5f356e09863"
    assert sources[1]["file_id"] == "0198bcf0-2da3-7acc-8d2a-a5f356e09864"


def test_workspace_search_validates_query_and_workspace(api_client: TestClient) -> None:
    workspace = api_client.post("/api/workspaces", json={"name": "Search Workspace"}).json()

    invalid_query = api_client.get(
        f"/api/workspaces/{workspace['id']}/search",
        params={"query": ""},
    )
    missing_workspace = api_client.get(
        "/api/workspaces/0198bcf0-2da3-7acc-8d2a-a5f356e09862/search",
        params={"query": "notes"},
    )

    assert invalid_query.status_code == 422
    assert missing_workspace.status_code == 404


def test_workspace_index_health_retries_failures_without_counting_pdf(
    api_client: TestClient,
) -> None:
    workspace = api_client.post("/api/workspaces", json={"name": "Recovery"}).json()
    page = api_client.post(
        f"/api/workspaces/{workspace['id']}/pages",
        json={"title": "Needs local model", "parent_page_id": None, "position": 0},
    )
    broken_file = api_client.post(
        f"/api/workspaces/{workspace['id']}/files",
        files={"upload": ("broken.txt", b"\xff\xfe", "text/plain")},
    )
    pdf = api_client.post(
        f"/api/workspaces/{workspace['id']}/files",
        files={"upload": ("reference.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert page.status_code == 201
    assert broken_file.status_code == 201
    assert pdf.status_code == 201

    health = api_client.get(f"/api/workspaces/{workspace['id']}/index-health")
    assert health.status_code == 200
    assert health.json()["status"] == "failed"
    assert health.json()["pages"]["failed"] == 1
    assert health.json()["files"]["failed"] == 1
    assert health.json()["files"]["metadata_only"] == 1

    retry = api_client.post(f"/api/workspaces/{workspace['id']}/index/retry-failed")
    assert retry.status_code == 200
    assert retry.json() == {"queued": 2}
