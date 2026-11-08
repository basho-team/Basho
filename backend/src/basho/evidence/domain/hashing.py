"""Hash de conteúdo do ledger: SHA-256 sobre JSON canônico do envelope imutável."""

import hashlib
import json
from typing import Any

from basho.evidence.contracts import NewEvidenceEvent

# Versão do algoritmo de hash. Mude ao alterar o envelope ou a canonicalização;
# a coluna `hash_version` permite recalcular/verificar linhas antigas.
HASH_VERSION = 1


def canonical_json(obj: Any) -> bytes:
    """Serializa de forma determinística: chaves ordenadas, sem espaços, UTF-8, sem NaN."""
    text = json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    return text.encode("utf-8")


def hashed_envelope(event: NewEvidenceEvent) -> dict[str, Any]:
    """Envelope de conteúdo imutável (v1), montado campo a campo e de forma explícita."""
    return {
        "tenant_id": str(event.tenant_id),
        "project_id": str(event.project_id),
        "kind": event.kind.value,
        "source": event.source.value,
        "source_ref": event.source_ref,
        "actor": {
            "type": event.actor.type.value,
            "id": event.actor.id,
            "model": event.actor.model,
        },
        "payload": event.payload,
        "supersedes": None if event.supersedes is None else str(event.supersedes),
        "is_synthetic": event.is_synthetic,
    }


def compute_content_hash(event: NewEvidenceEvent) -> str:
    """SHA-256 (hex minúsculo) do JSON canônico do envelope."""
    return hashlib.sha256(canonical_json(hashed_envelope(event))).hexdigest()
