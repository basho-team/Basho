"""Parser de links colados: só extrai IDs de hosts conhecidos; nunca vira requisição."""

import pytest

from basho.publishing.links import InvalidLinkError, LinkKind, parse_link

DRIVE_ID = "1AbCdEfGhIjKlMnOpQrStUvWxYz012345"
NOTION_ID = "0123456789abcdef0123456789abcdef"
NOTION_UUID = "01234567-89ab-cdef-0123-456789abcdef"


@pytest.mark.parametrize(
    "url",
    [
        f"https://drive.google.com/drive/folders/{DRIVE_ID}",
        f"https://drive.google.com/drive/folders/{DRIVE_ID}?usp=sharing",
        f"https://drive.google.com/drive/u/1/folders/{DRIVE_ID}?usp=drive_link",
        f"https://drive.google.com/open?id={DRIVE_ID}",
        f"  https://drive.google.com/drive/folders/{DRIVE_ID}/  ",
    ],
)
def test_drive_folder_links_yield_the_folder_id(url: str) -> None:
    # Act
    parsed = parse_link(url)

    # Assert
    assert parsed.kind is LinkKind.DRIVE_FOLDER
    assert parsed.external_id == DRIVE_ID
    assert parsed.url == f"https://drive.google.com/drive/folders/{DRIVE_ID}"


@pytest.mark.parametrize(
    "url",
    [
        f"https://www.notion.so/Meu-Projeto-{NOTION_ID}",
        f"https://www.notion.so/workspace/Meu-Projeto-{NOTION_ID}?pvs=4",
        f"https://notion.so/{NOTION_ID}",
        f"https://time-basho.notion.site/Relatorios-{NOTION_ID}",
    ],
)
def test_notion_page_links_yield_a_uuid(url: str) -> None:
    # Act
    parsed = parse_link(url)

    # Assert
    assert parsed.kind is LinkKind.NOTION_PAGE
    assert parsed.external_id == NOTION_UUID
    assert parsed.url == f"https://www.notion.so/{NOTION_ID}"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://github.com/basho-team/Basho", "basho-team/Basho"),
        ("https://github.com/basho-team/Basho.git", "basho-team/Basho"),
        ("https://github.com/basho-team/Basho/pull/12", "basho-team/Basho"),
        ("https://www.github.com/a/b/", "a/b"),
    ],
)
def test_github_links_yield_owner_and_name(url: str, expected: str) -> None:
    # Act
    parsed = parse_link(url)

    # Assert
    assert parsed.kind is LinkKind.GITHUB_REPO
    assert parsed.external_id == expected
    assert parsed.url == f"https://github.com/{expected}"


@pytest.mark.parametrize(
    "url",
    [
        "",
        "not a url",
        f"http://drive.google.com/drive/folders/{DRIVE_ID}",  # sem https
        f"https://user:pass@drive.google.com/drive/folders/{DRIVE_ID}",  # credenciais
        f"https://drive.google.com:8443/drive/folders/{DRIVE_ID}",  # porta
        f"https://evil.example/drive/folders/{DRIVE_ID}",  # host fora da allowlist
        f"https://drive.google.com.evil.example/drive/folders/{DRIVE_ID}",
        f"https://evil.example/notion.so/{NOTION_ID}",
        "https://169.254.169.254/latest/meta-data/",  # SSRF clássico
        "https://localhost:8000/admin",
        "https://drive.google.com/drive/folders/curto",  # ID inválido
        "https://drive.google.com/drive/my-drive",  # sem ID de pasta
        "https://www.notion.so/sem-id-aqui",
        "https://github.com/so-o-dono",
        "https://github.com/dono/../etc",
        "javascript:alert(1)",
        "https://drive.google.com/drive/folders/" + "A" * 3000,
    ],
)
def test_unsupported_or_unsafe_links_are_rejected(url: str) -> None:
    # Act / Assert
    with pytest.raises(InvalidLinkError):
        parse_link(url)
