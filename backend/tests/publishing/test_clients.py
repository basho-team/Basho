"""Clientes do Drive e do Notion contra transportes simulados (sem rede)."""

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from basho.publishing.clients.drive import FOLDER_MIME, DriveClient
from basho.publishing.clients.errors import ProviderError, ProviderErrorCode
from basho.publishing.clients.notion import NotionClient, rich_text
from basho.resilience import RetryPolicy

FOLDER = "1AbCdEfGhIjKlMnOpQrStUvWxYz012345"
BASHO = "2BbCdEfGhIjKlMnOpQrStUvWxYz012345"
PAGE = "01234567-89ab-cdef-0123-456789abcdef"
NO_WAIT = RetryPolicy(max_attempts=3, base_delay=0.0, max_delay=0.0, jitter=0.0)


class FixedToken:
    async def token(self) -> str:
        return "token-sintetico"


async def _no_sleep(_: float) -> None:
    return None


def _drive(handler: Callable[[httpx.Request], httpx.Response]) -> DriveClient:
    return DriveClient(
        tokens=FixedToken(),
        http=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        retry=NO_WAIT,
        sleep=_no_sleep,
    )


def _notion(handler: Callable[[httpx.Request], httpx.Response]) -> NotionClient:
    return NotionClient(
        token=SecretStr("secret-sintetico"),
        http=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        retry=NO_WAIT,
        sleep=_no_sleep,
    )


# --- Drive ---


async def test_get_folder_reports_whether_basho_can_add_children() -> None:
    # Arrange
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer token-sintetico"
        return httpx.Response(
            200,
            json={
                "id": FOLDER,
                "name": "Projetos",
                "mimeType": FOLDER_MIME,
                "capabilities": {"canAddChildren": True},
            },
        )

    # Act
    folder = await _drive(handler).get_folder(FOLDER)

    # Assert
    assert (folder.name, folder.can_add_children) == ("Projetos", True)


async def test_get_folder_rejects_a_file_that_is_not_a_folder() -> None:
    # Arrange
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": FOLDER, "mimeType": "application/pdf"})

    # Act / Assert
    with pytest.raises(ProviderError) as caught:
        await _drive(handler).get_folder(FOLDER)
    assert caught.value.code is ProviderErrorCode.NOT_A_FOLDER


async def test_folder_not_shared_with_the_account_is_not_found() -> None:
    # Act / Assert
    with pytest.raises(ProviderError) as caught:
        await _drive(lambda _: httpx.Response(404, json={"error": {}})).get_folder(FOLDER)
    assert caught.value.code is ProviderErrorCode.NOT_FOUND
    assert caught.value.retryable is False


async def test_ensure_folder_reuses_an_existing_basho_folder() -> None:
    # Arrange
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"files": [{"id": BASHO, "name": "BASHO"}]})

    # Act
    folder_id = await _drive(handler).ensure_folder(FOLDER)

    # Assert: só consultou, não criou
    assert folder_id == BASHO
    assert [c.method for c in calls] == ["GET"]
    assert "name = 'BASHO'" in calls[0].url.params["q"]
    assert f"'{FOLDER}' in parents" in calls[0].url.params["q"]


async def test_ensure_folder_creates_basho_inside_the_shared_folder() -> None:
    # Arrange
    created: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json={"files": []})
        created.append(json.loads(request.content))
        return httpx.Response(200, json={"id": BASHO})

    # Act
    folder_id = await _drive(handler).ensure_folder(FOLDER)

    # Assert
    assert folder_id == BASHO
    assert created == [{"name": "BASHO", "mimeType": FOLDER_MIME, "parents": [FOLDER]}]


async def test_create_document_uploads_html_as_a_google_doc() -> None:
    # Arrange
    uploads: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json={"files": []})
        uploads.append(request)
        return httpx.Response(
            200, json={"id": "doc1", "name": "Relatório", "webViewLink": "https://docs/doc1"}
        )

    # Act
    doc = await _drive(handler).create_document(BASHO, "Relatório", "<p>olá</p>")

    # Assert
    assert doc.url == "https://docs/doc1"
    body = uploads[0].content.decode()
    assert "application/vnd.google-apps.document" in body
    assert "<p>olá</p>" in body
    assert uploads[0].headers["content-type"].startswith("multipart/related; boundary=")


async def test_create_document_is_idempotent_when_the_file_already_exists() -> None:
    # Arrange: depois de uma falha, repetir não pode duplicar o documento
    methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        return httpx.Response(
            200, json={"files": [{"id": "doc1", "name": "R", "webViewLink": "https://docs/doc1"}]}
        )

    # Act
    doc = await _drive(handler).create_document(BASHO, "R", "<p>x</p>")

    # Assert
    assert doc.id == "doc1"
    assert methods == ["GET"]


async def test_query_literal_escapes_quotes_in_the_document_name() -> None:
    # Arrange
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.params["q"])
        return httpx.Response(200, json={"files": [{"id": "d", "name": "n"}]})

    # Act
    await _drive(handler).create_document(BASHO, "O'Brien \\ teste", "<p>x</p>")

    # Assert
    assert "name = 'O\\'Brien \\\\ teste'" in seen[0]


async def test_reads_retry_transient_failures_but_writes_do_not() -> None:
    # Arrange
    attempts = {"GET": 0, "POST": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts[request.method] += 1
        if request.method == "GET":
            if attempts["GET"] < 3:
                return httpx.Response(503)
            return httpx.Response(200, json={"files": []})
        return httpx.Response(503)

    client = _drive(handler)

    # Act / Assert: leitura se recupera no terceiro GET; a escrita falha na primeira
    with pytest.raises(ProviderError) as caught:
        await client.ensure_folder(FOLDER)
    assert caught.value.retryable is True
    assert attempts == {"GET": 3, "POST": 1}


async def test_malicious_folder_id_never_reaches_the_url() -> None:
    # Act / Assert
    with pytest.raises(ProviderError) as caught:
        await _drive(lambda _: httpx.Response(200, json={})).get_folder("../../etc/passwd")
    assert caught.value.code is ProviderErrorCode.BAD_REQUEST


# --- Notion ---


def _children(*titles: str) -> dict[str, Any]:
    return {
        "results": [
            {"id": f"block-{i}", "type": "child_page", "child_page": {"title": t}}
            for i, t in enumerate(titles)
        ],
        "has_more": False,
    }


async def test_notion_get_page_returns_title_and_url() -> None:
    # Arrange
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["notion-version"] == "2022-06-28"
        assert request.headers["authorization"] == "Bearer secret-sintetico"
        return httpx.Response(
            200,
            json={
                "id": PAGE,
                "url": "https://notion.so/p",
                "properties": {"title": {"type": "title", "title": [{"plain_text": "Projeto"}]}},
            },
        )

    # Act
    page = await _notion(handler).get_page(PAGE)

    # Assert
    assert (page.title, page.url) == ("Projeto", "https://notion.so/p")


async def test_notion_ensure_page_creates_basho_once() -> None:
    # Arrange
    posts: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json=_children("Outra página"))
        posts.append(json.loads(request.content))
        return httpx.Response(200, json={"id": "basho-page", "url": "https://notion.so/b"})

    # Act
    page_id = await _notion(handler).ensure_page(PAGE)

    # Assert
    assert page_id == "basho-page"
    assert posts[0]["parent"] == {"page_id": PAGE}
    assert posts[0]["properties"]["title"]["title"][0]["text"]["content"] == "BASHO"


async def test_notion_ensure_page_reuses_existing_basho_page() -> None:
    # Arrange
    methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        return httpx.Response(200, json=_children("BASHO"))

    # Act
    page_id = await _notion(handler).ensure_page(PAGE)

    # Assert
    assert page_id == "block-0"
    assert methods == ["GET"]


async def test_notion_report_page_is_not_duplicated_when_title_exists() -> None:
    # Arrange
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/children"):
            return httpx.Response(200, json=_children("Relatório X"))
        assert request.method == "GET"
        return httpx.Response(200, json={"id": "block-0", "url": "https://notion.so/r"})

    # Act
    page = await _notion(handler).create_report_page("basho", "Relatório X", [])

    # Assert
    assert page.url == "https://notion.so/r"


async def test_notion_splits_more_than_100_blocks_across_requests() -> None:
    # Arrange
    requests: list[tuple[str, int]] = []
    blocks = [
        {"object": "block", "type": "paragraph", "paragraph": {"rich_text": rich_text("x")}}
    ] * 230

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json=_children())
        body = json.loads(request.content)
        requests.append((request.method, len(body.get("children", []))))
        return httpx.Response(200, json={"id": "new", "url": "https://notion.so/n"})

    # Act
    await _notion(handler).create_report_page("basho", "Grande", blocks)

    # Assert
    assert requests == [("POST", 100), ("PATCH", 100), ("PATCH", 30)]


def test_rich_text_chunks_stay_under_the_notion_limit() -> None:
    # Act
    parts = rich_text("a" * 5000)

    # Assert
    assert all(len(p["text"]["content"]) <= 2000 for p in parts)
    assert "".join(p["text"]["content"] for p in parts) == "a" * 5000


async def test_provider_error_never_carries_the_response_body() -> None:
    # Arrange
    secret_body = {"message": "token=SEGREDO-NO-CORPO"}

    # Act / Assert
    with pytest.raises(ProviderError) as caught:
        await _notion(lambda _: httpx.Response(401, json=secret_body)).get_page(PAGE)
    assert "SEGREDO" not in str(caught.value)
    assert caught.value.code is ProviderErrorCode.UNAUTHORIZED
