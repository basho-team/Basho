"""Links colados pelo usuário → fonte ou destino autorizado (ADR-0010).

O link é só um identificador: **nunca** é buscado. Extraímos o ID com host e formato estritos
(https, sem credenciais, host em allowlist), então o conteúdo da URL não vira requisição
arbitrária do servidor (SSRF, ADR-0006). O acesso real exige que o dono tenha compartilhado a
pasta/página com a conta do Basho (service account do Google, integração do Notion); isso é
verificado depois, pelo cliente do provedor.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

from basho.connectors.github import RepoRef

MAX_URL_LENGTH = 2048
_DRIVE_ID = re.compile(r"[A-Za-z0-9_-]{10,128}")
_DRIVE_FOLDER_PATH = re.compile(r"/drive/(?:u/\d+/)?folders/([A-Za-z0-9_-]+)/?$")
_NOTION_ID = re.compile(r"(?:^|[-/])([0-9a-fA-F]{32})$")
_GITHUB_HOSTS = frozenset({"github.com", "www.github.com"})
_DRIVE_HOSTS = frozenset({"drive.google.com"})


class LinkKind(StrEnum):
    GITHUB_REPO = "github_repo"
    DRIVE_FOLDER = "drive_folder"
    NOTION_PAGE = "notion_page"


class InvalidLinkError(ValueError):
    """Link que não é de uma fonte/destino suportado; a mensagem é segura para o usuário."""


@dataclass(frozen=True, slots=True)
class ParsedLink:
    kind: LinkKind
    external_id: str
    display_name: str
    url: str
    """URL canônica reconstruída a partir do ID (nunca a string original)."""


def _split(url: str) -> tuple[str, list[str], dict[str, list[str]]]:
    if len(url) > MAX_URL_LENGTH:
        raise InvalidLinkError("link longo demais")
    try:
        parts = urlsplit(url.strip())
        port = parts.port
    except ValueError:
        raise InvalidLinkError("link inválido") from None
    if parts.scheme != "https" or not parts.hostname:
        raise InvalidLinkError("use um link https completo")
    if parts.username or parts.password or port not in (None, 443):
        raise InvalidLinkError("link com credenciais ou porta não é aceito")
    segments = [segment for segment in parts.path.split("/") if segment]
    return parts.hostname.lower(), segments, parse_qs(parts.query)


def _parse_drive(host: str, path: str, query: dict[str, list[str]]) -> ParsedLink:
    match = _DRIVE_FOLDER_PATH.search(path)
    folder_id = match.group(1) if match else (query.get("id") or [""])[0]
    if host not in _DRIVE_HOSTS or not _DRIVE_ID.fullmatch(folder_id):
        raise InvalidLinkError("não achei o ID da pasta; cole o link de uma pasta do Google Drive")
    return ParsedLink(
        kind=LinkKind.DRIVE_FOLDER,
        external_id=folder_id,
        display_name="Pasta do Google Drive",
        url=f"https://drive.google.com/drive/folders/{folder_id}",
    )


def _parse_notion(segments: list[str]) -> ParsedLink:
    last = segments[-1] if segments else ""
    match = _NOTION_ID.search(last)
    if match is None:
        raise InvalidLinkError("não achei o ID da página; cole o link de uma página do Notion")
    page_id = str(UUID(match.group(1)))
    return ParsedLink(
        kind=LinkKind.NOTION_PAGE,
        external_id=page_id,
        display_name="Página do Notion",
        url=f"https://www.notion.so/{page_id.replace('-', '')}",
    )


def _parse_github(segments: list[str]) -> ParsedLink:
    if len(segments) < 2:
        raise InvalidLinkError("cole o link de um repositório: github.com/dono/nome")
    owner, name = segments[0], segments[1].removesuffix(".git")
    try:
        repo = RepoRef(f"{owner}/{name}")
    except ValueError:
        raise InvalidLinkError("repositório inválido") from None
    return ParsedLink(
        kind=LinkKind.GITHUB_REPO,
        external_id=repo.full_name,
        display_name=repo.full_name,
        url=f"https://github.com/{repo.full_name}",
    )


def parse_link(url: str) -> ParsedLink:
    """Reconhece Drive (pasta), Notion (página) e GitHub (repositório); o resto é recusado."""
    host, segments, query = _split(url)
    if host in _DRIVE_HOSTS:
        return _parse_drive(host, "/" + "/".join(segments), query)
    if host == "notion.so" or host.endswith((".notion.so", ".notion.site")):
        return _parse_notion(segments)
    if host in _GITHUB_HOSTS:
        return _parse_github(segments)
    raise InvalidLinkError("link não suportado: use Google Drive, Notion ou GitHub")
