from __future__ import annotations

from typing import Any, Mapping

from .base import SourceSnapshot


def snapshot_to_compatibility_payload(snapshot: SourceSnapshot) -> Mapping[str, Any]:
    return dict(snapshot.extracted_fields)
