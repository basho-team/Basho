"""Conectores Google Drive e Notion (ADR-0010): clientes, payload e configuração. HTTP mockado."""

import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from basho.connectors.documents import MAX_TEXT_CHARS, DocumentSnapshot, document_payload
from basho.connectors.google_drive import FolderRef
from basho.connectors.http import ConnectorError
from basho.connectors.notion import NotionRef
from basho.connectors.sources import document_sources
from document_support import (
    DATABASE,
    DOC_ID,
    DRIVE_ACCESS,
    DRIVE_REFRESH,
    DRIVE_SECRET,
    FOLDER,
    INJECTION,
    NOTION_TOKEN,
    PAGE_A,
    PDF_ID,
    Clock,
    FakeDrive,
    FakeNotion,
)

# --- Google Drive ---------------------------------------------------------------------------


async def test_drive_snapshots_export_docs_and_keep_pdf_as_metadata_only() -> None:
    # Arrange
    fake = FakeDrive()

    # Act
    snapshots = await fake.client().snapshots(FOLDER)

    # Assert
    by_id = {s.doc_id: s for s in snapshots}
    assert set(by_id) == {DOC_ID, PDF_ID}  # subpasta fica de fora
    doc, pdf = by_id[DOC_ID], by_id[PDF_ID]
    assert doc.revision == "7"
    assert doc.source_ref == f"{DOC_ID}@7"
    assert doc.text is not None and INJECTION in doc.text
    assert pdf.text is None
    assert pdf.checksum == "abc123"


async def test_drive_sends_folder_query_and_access_token_only_to_api() -> None:
    # Arrange
    fake = FakeDrive()

    # Act
    await fake.client().list_files(FOLDER, since=datetime(2026, 10, 1, tzinfo=UTC))

    # Assert
    listing = next(r for r in fake.requests if r.url.path == "/drive/v3/files")
    query = listing.url.params["q"]
    assert f"'{FOLDER.folder_id}' in parents" in query
    assert "trashed = false" in query
    assert "modifiedTime > '2026-10-01T00:00:00+00:00'" in query
    assert listing.headers["authorization"] == f"Bearer {DRIVE_ACCESS}"
    token_call = next(r for r in fake.requests if r.url.host == "oauth.test")
    assert "authorization" not in token_call.headers


async def test_drive_reuses_access_token_until_expiry() -> None:
    # Arrange
    fake, clock = FakeDrive(), Clock()
    client = fake.client(clock)

    # Act
    await client.list_files(FOLDER)
    await client.list_files(FOLDER)
    clock.now += 3600
    await client.list_files(FOLDER)

    # Assert
    assert fake.token_requests == 2


async def test_drive_revoked_refresh_token_is_unauthorized_without_secrets() -> None:
    # Arrange
    fake = FakeDrive()
    fake.token_status = 400

    # Act
    with pytest.raises(ConnectorError) as excinfo:
        await fake.client().list_files(FOLDER)

    # Assert
    assert excinfo.value.code == "google_drive_unauthorized"
    assert excinfo.value.retryable is False
    for secret in (DRIVE_SECRET, DRIVE_REFRESH, DRIVE_ACCESS):
        assert secret not in str(excinfo.value)


async def test_drive_retries_rate_limit_then_succeeds() -> None:
    # Arrange
    fake = FakeDrive()
    fake.list_failures = [httpx.Response(429, headers={"retry-after": "2"})]

    # Act
    files = await fake.client().list_files(FOLDER)

    # Assert
    assert {f["id"] for f in files} >= {DOC_ID, PDF_ID}


async def test_drive_persistent_server_error_is_retryable_code() -> None:
    fake = FakeDrive()
    fake.list_failures = [httpx.Response(503)] * 3
    with pytest.raises(ConnectorError) as excinfo:
        await fake.client().list_files(FOLDER)
    assert excinfo.value.code == "google_drive_http_error"
    assert excinfo.value.retryable is True


@pytest.mark.parametrize("bad", ["x' or 'a'='a", "curto", "pasta com espaço 123"])
def test_drive_folder_id_rejects_query_injection(bad: str) -> None:
    with pytest.raises(ValueError, match="pasta"):
        FolderRef(bad)


# --- Notion ---------------------------------------------------------------------------------


async def test_notion_database_follows_cursor_skips_archived_and_reads_blocks() -> None:
    # Arrange
    fake = FakeNotion()

    # Act
    snapshots = await fake.client().snapshots(DATABASE, since=datetime(2026, 10, 1, tzinfo=UTC))

    # Assert
    assert [s.title for s in snapshots] == ["Diário do experimento", "Notas de bench"]
    first = snapshots[0]
    assert first.doc_id == PAGE_A.replace("-", "")
    assert first.revision == "2026-10-06T10:00:00+00:00"
    assert first.text is not None
    assert first.text.splitlines()[0] == "## Hipótese"
    assert "[x] Rodar bench" in first.text
    assert INJECTION in first.text
    query = next(r for r in fake.requests if r.url.path.endswith("/query"))
    assert query.headers["authorization"] == f"Bearer {NOTION_TOKEN}"
    assert query.headers["notion-version"] == "2022-06-28"
    sent = json.loads(query.content)
    assert sent["filter"]["last_edited_time"] == {"on_or_after": "2026-10-01T00:00:00+00:00"}


async def test_notion_single_page_source() -> None:
    snapshots = await FakeNotion().client().snapshots(NotionRef.parse(f"page:{PAGE_A}"))
    assert [s.doc_id for s in snapshots] == [PAGE_A.replace("-", "")]


async def test_notion_unauthorized_has_stable_code_without_token() -> None:
    fake = FakeNotion()
    fake.query_failures = [httpx.Response(401)]
    with pytest.raises(ConnectorError) as excinfo:
        await fake.client().snapshots(DATABASE)
    assert excinfo.value.code == "notion_unauthorized"
    assert NOTION_TOKEN not in str(excinfo.value)


@pytest.mark.parametrize("bad", ["database:../../users", "workspace:" + "1" * 32, "page:xyz"])
def test_notion_ref_rejects_invalid_values(bad: str) -> None:
    with pytest.raises(ValueError, match="Notion"):
        NotionRef.parse(bad)


# --- payload e configuração -----------------------------------------------------------------


def test_document_payload_hashes_full_text_and_truncates_stored_copy() -> None:
    # Arrange
    body = "a" * (MAX_TEXT_CHARS + 10)
    snapshot = DocumentSnapshot("d1", "1", "t", None, "text/plain", None, body)

    # Act
    payload = document_payload(snapshot)

    # Assert
    assert payload["content_sha256"] == hashlib.sha256(body.encode()).hexdigest()
    assert payload["text_truncated"] is True
    assert isinstance(payload["text"], str) and len(payload["text"]) == MAX_TEXT_CHARS


class _Settings:
    """Só os campos lidos por `document_sources`."""

    def __init__(self, **values: object) -> None:
        self.google_drive_client_id = ""
        self.google_drive_client_secret = None
        self.google_drive_refresh_token = None
        self.google_drive_project_folders: dict[object, list[str]] = {}
        self.notion_token = None
        self.notion_project_sources: dict[object, list[str]] = {}
        self.__dict__.update(values)


def test_document_sources_are_off_without_full_configuration() -> None:
    project = uuid4()
    only_map = _Settings(google_drive_project_folders={project: [FOLDER.folder_id]})
    sources = document_sources(only_map, httpx.AsyncClient())  # type: ignore[arg-type]
    assert sources.configured is False


def test_document_sources_wire_drive_and_notion_per_project() -> None:
    # Arrange
    project = uuid4()
    settings = _Settings(
        google_drive_client_id="cid",
        google_drive_client_secret=SecretStr("s"),
        google_drive_refresh_token=SecretStr("r"),
        google_drive_project_folders={project: [FOLDER.folder_id]},
        notion_token=SecretStr("n"),
        notion_project_sources={project: [f"database:{DATABASE.object_id}"]},
    )

    # Act
    sources = document_sources(settings, httpx.AsyncClient())  # type: ignore[arg-type]

    # Assert
    assert sources.configured is True
    assert sources.drive is not None and sources.notion is not None
    assert list(sources.drive_folders[project]) == [FOLDER]
    assert list(sources.notion_refs[project]) == [DATABASE]


def test_document_sources_fail_fast_on_invalid_ids() -> None:
    project = uuid4()
    settings = _Settings(
        notion_token=SecretStr("n"), notion_project_sources={project: ["page:nao-e-id"]}
    )
    with pytest.raises(ValueError, match="Notion"):
        document_sources(settings, httpx.AsyncClient())  # type: ignore[arg-type]


def test_notion_page_text_includes_structured_properties_but_not_people() -> None:
    # Arrange
    from basho.connectors.notion.client import _with_properties

    page = {
        "properties": {
            "Status": {"type": "select", "select": {"name": "Em andamento"}},
            "Prazo Previsto": {
                "type": "date",
                "date": {"start": "2026-10-12", "end": "2026-11-27"},
            },
            "Sintético": {"type": "checkbox", "checkbox": True},
            "Responsável": {"type": "rich_text", "rich_text": [{"plain_text": "Ana Ribeiro"}]},
            "Pessoas": {"type": "people", "people": [{"id": "u1", "name": "Ana"}]},
        }
    }

    # Act
    text = _with_properties(page, "corpo")

    # Assert
    assert "- Status: Em andamento" in text
    assert "- Prazo Previsto: 2026-10-12 → 2026-11-27" in text
    assert "- Sintético: sim" in text
    assert "Ana" not in text
    assert text.endswith("corpo")
