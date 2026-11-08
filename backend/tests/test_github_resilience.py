"""Confiabilidade do conector GitHub (#25): retry de leitura e criação de issue idempotente.

Regra central: após timeout/5xx numa escrita, o efeito é desconhecido. O cliente **consulta o
destino** antes de reenviar; um retry cego duplicaria a issue (teste abaixo falharia).
"""

import httpx
import pytest

from basho.agent.tools import ToolCallStatus
from basho.connectors.github import GithubError, GithubErrorCode, build_github_tools
from basho.connectors.github.client import IDEMPOTENCY_MARKER
from basho.connectors.github.tools import issue_idempotency_key
from basho.resilience import RetryPolicy
from github_support import FIRST_ISSUE_NUMBER, REPO, FakeGithub, client_for

KEY = "a" * 32
TITLE = "Registrar justificativa técnica do experimento"

# --- leituras: retry com backoff ----------------------------------------------------------


async def test_read_recovers_from_transient_5xx_with_backoff() -> None:
    # Arrange
    fake = FakeGithub()
    fake.get_failures = [httpx.Response(502), httpx.Response(503)]

    # Act
    commits = await fake.client().list_commits(REPO)

    # Assert
    assert len(commits) == 2
    assert fake.sleeps.delays == [1.0, 2.0]


async def test_read_recovers_from_network_failure() -> None:
    fake = FakeGithub()
    fake.get_failures = [httpx.ConnectError("boom")]
    assert await fake.client().list_pull_requests(REPO)
    assert len(fake.sleeps.delays) == 1


@pytest.mark.parametrize("status", [401, 404, 422])
async def test_read_does_not_retry_permanent_4xx(status: int) -> None:
    fake = FakeGithub()
    fake.get_failures = [httpx.Response(status)]
    with pytest.raises(GithubError) as excinfo:
        await fake.client().get_pull_request(REPO, 7)
    assert not excinfo.value.retryable
    assert excinfo.value.attempts == 1
    assert fake.sleeps.delays == []


async def test_read_gives_up_after_max_attempts_and_reports_them() -> None:
    fake = FakeGithub()
    fake.get_failures = [httpx.Response(500)] * 5
    with pytest.raises(GithubError) as excinfo:
        await fake.client().get_pull_request(REPO, 7)
    assert excinfo.value.attempts == 3
    assert len(fake.requests) == 3


async def test_rate_limit_waits_for_retry_after_header() -> None:
    fake = FakeGithub()
    fake.get_failures = [httpx.Response(429, headers={"retry-after": "30"})]
    await fake.client().get_pull_request(REPO, 7)
    assert fake.sleeps.delays == [30.0]


async def test_rate_limit_longer_than_budget_is_not_waited_out() -> None:
    # O erro leva `retry_after`: o worker (#10) reagenda o run em vez de segurar o processo.
    fake = FakeGithub()
    fake.get_failures = [httpx.Response(429, headers={"retry-after": "900"})]
    with pytest.raises(GithubError) as excinfo:
        await fake.client().get_pull_request(REPO, 7)
    assert excinfo.value.code is GithubErrorCode.RATE_LIMITED
    assert excinfo.value.retry_after == 900.0
    assert fake.sleeps.delays == []
    assert len(fake.requests) == 1


# --- escrita: issue idempotente -----------------------------------------------------------


async def test_ensure_issue_creates_once_and_marks_the_key() -> None:
    fake = FakeGithub()
    issue = await fake.client().ensure_issue(REPO, title=TITLE, body="texto", idempotency_key=KEY)
    assert (issue.number, issue.reused) == (FIRST_ISSUE_NUMBER, False)
    assert IDEMPOTENCY_MARKER.format(key=KEY) in fake.issues[0]["body"]
    assert fake.issues[0]["body"].startswith("texto")


async def test_ensure_issue_reuses_existing_issue_on_replay() -> None:
    # Arrange: o run caiu depois de criar e foi reexecutado com a mesma intenção
    fake = FakeGithub()
    client = fake.client()
    first = await client.ensure_issue(REPO, title=TITLE, body="texto", idempotency_key=KEY)

    # Act
    again = await client.ensure_issue(REPO, title=TITLE, body="texto", idempotency_key=KEY)

    # Assert
    assert again.number == first.number
    assert again.reused
    assert len(fake.posts) == 1


async def test_lost_response_after_create_does_not_duplicate_issue() -> None:
    # Arrange: o GitHub criou a issue, mas a resposta se perdeu (timeout depois do efeito)
    fake = FakeGithub()
    fake.lose_response_after_create = 1

    # Act
    issue = await fake.client().ensure_issue(REPO, title=TITLE, body="t", idempotency_key=KEY)

    # Assert: consultou o destino, achou a issue e não reenviou
    assert issue.reused
    assert len(fake.issues) == 1
    assert len(fake.posts) == 1


async def test_transient_post_failure_without_effect_is_retried_after_verifying() -> None:
    # Arrange: 503 antes de criar nada
    fake = FakeGithub()
    fake.post_failures = [httpx.Response(503)]

    # Act
    issue = await fake.client().ensure_issue(REPO, title=TITLE, body="t", idempotency_key=KEY)

    # Assert: verificou (GET de issues), viu que não existia e só então reenviou
    assert not issue.reused
    assert len(fake.issues) == 1
    assert len(fake.posts) == 2
    order = [r.method for r in fake.requests if r.url.path.endswith("/issues")]
    assert order == ["GET", "POST", "GET", "POST"]


async def test_post_is_never_resent_when_verification_fails() -> None:
    # Arrange: POST falha e a consulta também: sem como saber se criou
    fake = FakeGithub()
    fake.post_failures = [httpx.Response(503)]
    original_handler = fake.handler
    state = {"posted": False}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            state["posted"] = True
        elif state["posted"]:
            return httpx.Response(401)  # a verificação pós-falha não consegue ler
        return original_handler(request)

    client = client_for(handler, RetryPolicy(max_attempts=3, jitter=0.0))

    # Act / Assert
    with pytest.raises(GithubError) as excinfo:
        await client.ensure_issue(REPO, title=TITLE, body="t", idempotency_key=KEY)
    assert excinfo.value.code is GithubErrorCode.UNAUTHORIZED
    assert len(fake.posts) == 1


async def test_permanent_post_failure_is_raised_without_retry() -> None:
    fake = FakeGithub()
    fake.post_failures = [httpx.Response(422)]
    with pytest.raises(GithubError) as excinfo:
        await fake.client().ensure_issue(REPO, title=TITLE, body="t", idempotency_key=KEY)
    assert not excinfo.value.retryable
    assert len(fake.posts) == 1


async def test_exhausted_post_attempts_raise_with_attempt_count() -> None:
    fake = FakeGithub()
    fake.post_failures = [httpx.Response(503)] * 5
    with pytest.raises(GithubError) as excinfo:
        await fake.client().ensure_issue(REPO, title=TITLE, body="t", idempotency_key=KEY)
    assert excinfo.value.attempts == 3
    assert len(fake.posts) == 3
    assert fake.issues == []


async def test_pull_requests_in_issue_listing_are_not_matched() -> None:
    fake = FakeGithub()
    assert await fake.client().find_issue_by_key(REPO, KEY) is None


@pytest.mark.parametrize("key", ["", "curta", "tem espaço no meio 123", "x" * 200, "../etc/passwd"])
async def test_invalid_idempotency_key_is_rejected_before_any_request(key: str) -> None:
    fake = FakeGithub()
    with pytest.raises(ValueError, match="idempotency_key"):
        await fake.client().ensure_issue(REPO, title=TITLE, body="t", idempotency_key=key)
    assert fake.requests == []


async def test_writes_are_spaced_by_the_configured_interval() -> None:
    # Arrange: relógio fixo, intervalo de 1s entre escritas
    fake = FakeGithub()
    client = fake.client()
    client._write_interval = 1.0
    client._clock = lambda: 100.0

    # Act
    await client.create_issue(REPO, title=TITLE, body="a")
    await client.create_issue(REPO, title=TITLE, body="b")

    # Assert: a segunda escrita esperou o intervalo inteiro
    assert fake.sleeps.delays == [1.0]


# --- tool ---------------------------------------------------------------------------------


async def test_tool_replay_with_same_intent_returns_existing_issue() -> None:
    # Arrange
    fake = FakeGithub()
    _, _, issue_tool = build_github_tools(fake.client(), REPO)
    args = {"title": TITLE, "body": "texto"}

    # Act
    first = await issue_tool.run("tenant", args)
    second = await issue_tool.run("tenant", args)

    # Assert
    assert first.data is not None and second.data is not None
    assert first.data["already_existed"] is False
    assert second.data["already_existed"] is True
    assert second.data["issue_number"] == first.data["issue_number"]
    assert len(fake.issues) == 1


async def test_tool_with_other_content_creates_another_issue() -> None:
    fake = FakeGithub()
    _, _, issue_tool = build_github_tools(fake.client(), REPO)
    await issue_tool.run("tenant", {"title": TITLE, "body": "um"})
    await issue_tool.run("tenant", {"title": TITLE, "body": "dois"})
    assert len(fake.issues) == 2


async def test_tool_failure_returns_stable_code_without_secret_or_body() -> None:
    fake = FakeGithub()
    fake.post_failures = [httpx.Response(503)] * 5
    _, _, issue_tool = build_github_tools(fake.client(), REPO)
    result = await issue_tool.run("tenant", {"title": TITLE, "body": "segredo-no-corpo"})
    assert result.status is ToolCallStatus.ERROR
    assert result.error == GithubErrorCode.HTTP_ERROR.value
    assert "segredo-no-corpo" not in result.model_dump_json()


def test_idempotency_key_is_stable_and_scoped_by_tenant_repo_and_content() -> None:
    base = issue_idempotency_key("t1", REPO, "titulo", "corpo")
    assert base == issue_idempotency_key("t1", REPO, "titulo", "corpo")
    assert base != issue_idempotency_key("t2", REPO, "titulo", "corpo")
    assert base != issue_idempotency_key("t1", REPO, "titulo", "outro corpo")
    assert len(base) == 32
