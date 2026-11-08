"""Hash de conteúdo do ledger: SHA-256 sobre JSON canônico do envelope imutável."""

import hashlib
import json
from typing import Any

from basho.evidence.contracts import NewEvidenceEvent

# Campos do envelope cobertos pelo hash. `id` e `created_at` ficam de fora.
HASHED_FIELDS: frozenset[str] = frozenset(
    {
        "tenant_id",
        "project_id",
        "kind",
        "source",
        "source_ref",
        "actor",
        "payload",
        "supersedes",
        "is_synthetic",
    }
)


def canonical_json(obj: Any) -> bytes:
    """Serializa de forma determinística: chaves ordenadas, sem espaços, UTF-8, sem NaN."""
    text = json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    return text.encode("utf-8")


def hashed_envelope(event: NewEvidenceEvent) -> dict[str, Any]:
    """Envelope de conteúdo imutável que o hash cobre."""
    dumped = event.model_dump(mode="json")
    return {name: dumped[name] for name in HASHED_FIELDS}


def compute_content_hash(event: NewEvidenceEvent) -> str:
    """SHA-256 (hex minúsculo) do JSON canônico do envelope."""
    return hashlib.sha256(canonical_json(hashed_envelope(event))).hexdigest()
