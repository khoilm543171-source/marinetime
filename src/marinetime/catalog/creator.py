from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


UNKNOWN_CREATOR_ID = "unknown"


@dataclass(frozen=True)
class CreatorEntry:
    creator_id: str
    display_name: str
    aliases: tuple[str, ...]
    platform_ids: tuple[str, ...]


@dataclass(frozen=True)
class CreatorResolution:
    creator_id: str
    display_name: str
    source: str
    confidence: str
    matched_value: str | None = None

    @property
    def is_deterministic(self) -> bool:
        return self.confidence == "deterministic"


class CreatorRegistryError(ValueError):
    """Raised when creator registry data is malformed or ambiguous."""


def normalize_creator_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.replace("đ", "d").replace("Đ", "D").lower()
    text = re.sub(r"[^a-z0-9@]+", " ", text)
    return " ".join(text.split())


def load_creator_registry(path: str | Path) -> tuple[CreatorEntry, ...]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != "1.0":
        raise CreatorRegistryError("INVALID_CREATOR_REGISTRY")
    raw_creators = payload.get("creators")
    if not isinstance(raw_creators, list):
        raise CreatorRegistryError("CREATORS_LIST_REQUIRED")

    entries: list[CreatorEntry] = []
    seen_ids: set[str] = set()
    for raw in raw_creators:
        if not isinstance(raw, dict):
            raise CreatorRegistryError("CREATOR_ENTRY_NOT_OBJECT")
        creator_id = raw.get("creator_id")
        display_name = raw.get("display_name")
        aliases = raw.get("aliases", [])
        platform_ids = raw.get("platform_ids", {})
        if not isinstance(creator_id, str) or not creator_id.strip():
            raise CreatorRegistryError("CREATOR_ID_REQUIRED")
        if creator_id in seen_ids:
            raise CreatorRegistryError(f"DUPLICATE_CREATOR_ID:{creator_id}")
        if not isinstance(display_name, str) or not display_name.strip():
            raise CreatorRegistryError(f"DISPLAY_NAME_REQUIRED:{creator_id}")
        if not isinstance(aliases, list) or not all(isinstance(v, str) for v in aliases):
            raise CreatorRegistryError(f"ALIASES_INVALID:{creator_id}")
        if not isinstance(platform_ids, dict):
            raise CreatorRegistryError(f"PLATFORM_IDS_INVALID:{creator_id}")

        flattened_ids: list[str] = []
        for values in platform_ids.values():
            if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
                raise CreatorRegistryError(f"PLATFORM_IDS_INVALID:{creator_id}")
            flattened_ids.extend(values)

        seen_ids.add(creator_id)
        entries.append(
            CreatorEntry(
                creator_id=creator_id,
                display_name=display_name,
                aliases=tuple(dict.fromkeys([display_name, *aliases])),
                platform_ids=tuple(dict.fromkeys(flattened_ids)),
            )
        )
    return tuple(entries)


def _unique_match(
    values: Iterable[str],
    entries: tuple[CreatorEntry, ...],
    *,
    use_platform_ids: bool,
) -> tuple[CreatorEntry, str] | None:
    normalized_values = [(value, normalize_creator_text(value)) for value in values if value]
    matches: list[tuple[CreatorEntry, str]] = []
    for entry in entries:
        candidates = entry.platform_ids if use_platform_ids else entry.aliases
        normalized_candidates = {normalize_creator_text(value) for value in candidates if value}
        for original, normalized in normalized_values:
            if normalized and normalized in normalized_candidates:
                matches.append((entry, original))
                break

    by_id = {entry.creator_id: (entry, matched) for entry, matched in matches}
    if len(by_id) == 1:
        return next(iter(by_id.values()))
    return None


def _filename_match(
    filename: str,
    entries: tuple[CreatorEntry, ...],
) -> tuple[CreatorEntry, str] | None:
    stem = Path(filename).stem
    normalized_stem = normalize_creator_text(stem)
    matches: list[tuple[CreatorEntry, str]] = []
    for entry in entries:
        for alias in entry.aliases:
            normalized_alias = normalize_creator_text(alias)
            if not normalized_alias:
                continue
            if normalized_stem == normalized_alias or normalized_stem.startswith(normalized_alias + " "):
                matches.append((entry, alias))
                break
    by_id = {entry.creator_id: (entry, matched) for entry, matched in matches}
    if len(by_id) == 1:
        return next(iter(by_id.values()))
    return None


def _ocr_candidate(
    ocr_texts: Iterable[str],
    entries: tuple[CreatorEntry, ...],
) -> tuple[CreatorEntry, str] | None:
    normalized_ocr = [(text, normalize_creator_text(text)) for text in ocr_texts if text]
    matches: list[tuple[CreatorEntry, str]] = []
    for entry in entries:
        aliases = [normalize_creator_text(alias) for alias in entry.aliases]
        for original, normalized_text in normalized_ocr:
            if any(alias and alias in normalized_text for alias in aliases):
                matches.append((entry, original))
                break
    by_id = {entry.creator_id: (entry, matched) for entry, matched in matches}
    if len(by_id) == 1:
        return next(iter(by_id.values()))
    return None


def resolve_creator(
    *,
    registry: tuple[CreatorEntry, ...],
    explicit_creator_id: str | None = None,
    filename: str | None = None,
    uploader: str | None = None,
    uploader_id: str | None = None,
    channel: str | None = None,
    channel_id: str | None = None,
    ocr_texts: Iterable[str] = (),
) -> CreatorResolution:
    if explicit_creator_id:
        explicit = [entry for entry in registry if entry.creator_id == explicit_creator_id]
        if len(explicit) == 1:
            entry = explicit[0]
            return CreatorResolution(
                creator_id=entry.creator_id,
                display_name=entry.display_name,
                source="explicit_batch_metadata",
                confidence="deterministic",
                matched_value=explicit_creator_id,
            )
        return CreatorResolution(
            creator_id=UNKNOWN_CREATOR_ID,
            display_name="UNKNOWN",
            source="invalid_explicit_creator_id",
            confidence="unknown",
            matched_value=explicit_creator_id,
        )

    identifier_match = _unique_match(
        [uploader_id or "", channel_id or ""],
        registry,
        use_platform_ids=True,
    )
    if identifier_match:
        entry, matched = identifier_match
        return CreatorResolution(
            creator_id=entry.creator_id,
            display_name=entry.display_name,
            source="platform_id",
            confidence="deterministic",
            matched_value=matched,
        )

    metadata_match = _unique_match(
        [uploader or "", channel or ""],
        registry,
        use_platform_ids=False,
    )
    if metadata_match:
        entry, matched = metadata_match
        return CreatorResolution(
            creator_id=entry.creator_id,
            display_name=entry.display_name,
            source="uploader_or_channel",
            confidence="deterministic",
            matched_value=matched,
        )

    if filename:
        filename_match = _filename_match(filename, registry)
        if filename_match:
            entry, matched = filename_match
            return CreatorResolution(
                creator_id=entry.creator_id,
                display_name=entry.display_name,
                source="filename_prefix",
                confidence="deterministic",
                matched_value=matched,
            )

    candidate = _ocr_candidate(ocr_texts, registry)
    if candidate:
        entry, matched = candidate
        return CreatorResolution(
            creator_id=entry.creator_id,
            display_name=entry.display_name,
            source="ocr_candidate",
            confidence="candidate",
            matched_value=matched,
        )

    return CreatorResolution(
        creator_id=UNKNOWN_CREATOR_ID,
        display_name="UNKNOWN",
        source="unresolved",
        confidence="unknown",
    )
