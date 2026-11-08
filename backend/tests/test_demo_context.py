"""Disponibilidade da IA vem da configuração, não é fixa."""

from basho.demo.api import _configured


def test_not_configured_placeholder_means_unavailable() -> None:
    assert not _configured("not-configured")
    assert not _configured("  ")
    assert _configured("sk-ant-real-looking-value")
