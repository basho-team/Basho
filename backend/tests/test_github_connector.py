"""Conector GitHub (#7): cliente, tools reais e aprovação de ação externa. HTTP mockado."""

import json

import httpx
import pytest

from basho.agent.approvals import InMemoryApprovalStore
from basho.agent.artifacts import ResearchReportDraft
from basho.agent.policy import ToolPolicy
from basho.agent.registry import ToolRegistry
from basho.agent.tasks import TOOL_REGISTRY_CONTEXT_KEY, TaskKind, TaskProfile
from basho.agent.tools import ToolCallStatus
from basho.audit import InMemoryAuditLog
from basho.connectors.github import GithubError, GithubErrorCode, RepoRef, build_github_tools
from github_support import INJECTION, REPO, TOKEN, FakeGithub, client_for
from tool_support import call_context

# --- cliente ----------------------------------------------------------------------------


async def test_list_commits_follows_pagination_and_sends_token_header() -> None:
    # Arrange
    fake = FakeGithub()

    # Act
    commits = await fake.client().list_commits(REPO)

    # Assert
    assert [c["sha"][0] for c in commits] == ["a", "b"]
    assert len(fake.requests) == 2
    assert fake.requests[0].headers["authorization"] == f"Bearer {TOKEN}"
    assert fake.requests[0].headers["x-github-api-version"] == "2022-11-28"


@pytest.mark.parametrize(
    ("response", "code", "retryable"),
    [
        (httpx.Response(401), GithubErrorCode.UNAUTHORIZED, False),
        (httpx.Response(404), GithubErrorCode.NOT_FOUND, False),
        (httpx.Response(429), GithubErrorCode.RATE_LIMITED, True),
        (
            httpx.Response(403, headers={"x-ratelimit-remaining": "0"}),
            GithubErrorCode.RATE_LIMITED,
            True,
        ),
        (httpx.Response(502), GithubErrorCode.HTTP_ERROR, True),
    ],
)
async def test_http_failures_become_stable_codes_without_token(
    response: httpx.Response, code: GithubErrorCode, retryable: bool
) -> None:
    client = client_for(lambda request: response)
    with pytest.raises(GithubError) as excinfo:
        await client.get_pull_request(REPO, 1)
    assert excinfo.value.code is code
    assert excinfo.value.retryable is retryable
    assert TOKEN not in str(excinfo.value)


async def test_network_failure_is_retryable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    with pytest.raises(GithubError) as excinfo:
        await client_for(handler).list_pull_requests(REPO)
    assert excinfo.value.code is GithubErrorCode.NETWORK
    assert excinfo.value.retryable


@pytest.mark.parametrize(
    "name", ["owner", "../etc/passwd", "a/b/c", "owner/repo?x=1", "", "owner/..", "owner/."]
)
def test_repo_ref_rejects_anything_but_owner_slash_name(name: str) -> None:
    with pytest.raises(ValueError, match="owner/name"):
        RepoRef(name)


# --- tools reais ------------------------------------------------------------------------


def _policy_for(fake: FakeGithub) -> tuple[ToolPolicy, InMemoryApprovalStore, TaskProfile]:
    registry = ToolRegistry(list(build_github_tools(fake.client(), REPO)))
    profile = TaskProfile.model_validate(
        {
            "kind": TaskKind.RESEARCH_REPORT,
            "prompt_version": "v1",
            "allowed_tools": frozenset(registry.levels()),
            "output_schema": ResearchReportDraft,
        },
        context={TOOL_REGISTRY_CONTEXT_KEY: registry.levels()},
    )
    approvals = InMemoryApprovalStore()
    return ToolPolicy(registry, InMemoryAuditLog(), approvals), approvals, profile


async def test_commit_text_reaches_model_only_as_untrusted_data() -> None:
    # Arrange
    fake = FakeGithub()
    policy, _, profile = _policy_for(fake)

    # Act
    result = await policy.execute(call_context(profile), "github_list_commits", {"limit": 10})

    # Assert
    assert result.status is ToolCallStatus.OK
    assert INJECTION not in json.dumps(result.data)
    assert result.untrusted_data is not None
    assert result.untrusted_data.startswith('<untrusted_data tool="github_list_commits">')
    assert "Ignore as instru" in result.untrusted_data
    assert "ana@example.com" not in result.untrusted_data


async def test_get_pull_request_returns_identifiers_in_data() -> None:
    fake = FakeGithub()
    policy, _, profile = _policy_for(fake)
    result = await policy.execute(call_context(profile), "github_get_pull_request", {"number": 7})
    assert result.status is ToolCallStatus.OK
    assert result.data == {
        "repo": REPO.full_name,
        "number": 7,
        "state": "closed",
        "created_at": "2026-10-04T12:00:00+00:00",
        "merged_at": None,
    }


async def test_create_issue_never_calls_github_without_human_approval() -> None:
    # Arrange
    fake = FakeGithub()
    policy, _, profile = _policy_for(fake)
    context = call_context(profile)

    # Act
    result = await policy.execute(
        context, "github_create_issue", {"title": "Registrar justificativa", "body": "texto"}
    )

    # Assert
    assert result.status is ToolCallStatus.PENDING_APPROVAL
    assert not [r for r in fake.requests if r.method == "POST"]


async def test_create_issue_tool_calls_github_when_executed_after_approval() -> None:
    # Arrange: o worker (#10) executa a tool só depois da decisão humana
    fake = FakeGithub()
    _, _, issue = build_github_tools(fake.client(), REPO)

    # Act
    result = await issue.run("tenant", {"title": "Registrar justificativa", "body": "texto"})

    # Assert
    assert result.status is ToolCallStatus.OK
    assert result.data == {"repo": REPO.full_name, "issue_number": 99}
    (post,) = [r for r in fake.requests if r.method == "POST"]
    assert post.url.path == f"/repos/{REPO.full_name}/issues"


async def test_github_error_becomes_tool_error_code() -> None:
    fake = FakeGithub()
    list_commits, _, _ = build_github_tools(client_for(lambda r: httpx.Response(429)), REPO)
    result = await list_commits.run("tenant", {})
    assert result.status is ToolCallStatus.ERROR
    assert result.error == GithubErrorCode.RATE_LIMITED.value
    assert fake.requests == []


async def test_pagination_refuses_next_link_to_another_host() -> None:
    # Arrange: o token não pode seguir para fora da API configurada
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        link = '<https://evil.example/repos/x/y/commits?page=2>; rel="next"'
        return httpx.Response(200, json=[], headers={"link": link})

    # Act / Assert
    with pytest.raises(GithubError) as excinfo:
        await client_for(handler).list_commits(REPO)
    assert excinfo.value.code is GithubErrorCode.INVALID_RESPONSE
    assert len(seen) == 1


def test_payloads_only_keep_well_formed_identifiers() -> None:
    # Arrange
    from basho.connectors.github.ingest import commit_payload, pull_request_payload
    from github_support import commit, pull

    bad_pull = pull(8, "t", "b") | {"state": "<script>", "created_at": "ontem", "merged_at": 5}

    # Act
    bad_sha = commit_payload(REPO, commit("not-a-sha", "msg"))
    pr = pull_request_payload(REPO, bad_pull)

    # Assert
    assert bad_sha is None
    assert pr is not None
    assert (pr["state"], pr["created_at"], pr["merged_at"]) == (None, None, None)
