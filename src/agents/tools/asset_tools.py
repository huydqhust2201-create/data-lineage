"""Read-only asset metadata capability for root-cause analysis."""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.agents.chat.base import CapabilityResult
from src.agents.chat.resolve import known_tables, resolve_table
from src.config import get_settings
from src.models.schemas import AssetProfile
from src.services import review_service, storage_service

_MAX_TABLES = 20


class GetAssetParams(BaseModel):
    tables: list[str] = Field(..., min_length=1)


def _timestamp(value) -> str | None:
    return value.isoformat() if value is not None else None


class GetAssetCapability:
    """Fetch complete profiles for multiple assets without interrupting a batch."""

    name = "get_asset"
    description = (
        "Get full profiles for one or more tables at once: when each last changed, whether it was renamed "
        "or dropped, what defines it, and its columns. Pass every table you want to compare in a single call."
    )
    Params = GetAssetParams

    def run(self, params: GetAssetParams, database_id: int) -> CapabilityResult:
        mentions = params.tables[:_MAX_TABLES]
        candidates = sorted(set(known_tables(database_id)) | set(storage_service.all_node_names(database_id)))
        names: list[str] = []
        skipped: list[dict[str, str]] = []
        for mention in mentions:
            resolution = resolve_table(mention, candidates)
            if resolution.status == "resolved" and resolution.table is not None:
                if resolution.table not in names:
                    names.append(resolution.table)
            else:
                skipped.append({"mention": mention, "reason": resolution.status})

        profiles_by_name = storage_service.load_asset_profiles(database_id, names)
        descriptions = {}
        if get_settings().description_enabled:
            try:
                descriptions = storage_service.load_descriptions_by_names(database_id, names)
            except Exception:
                # Asset metadata remains useful when optional descriptions are unavailable.
                descriptions = {}
        pending = review_service.list_pending(database_id)
        assets: list[AssetProfile] = []
        for name in names:
            profile = profiles_by_name.get(name)
            if profile is None:
                skipped.append({"mention": name, "reason": "not_found"})
                continue
            pending_count = sum(name in (edge.source_table, edge.target_table) for edge in pending)
            assets.append(
                AssetProfile(
                    name=profile.current_name,
                    defined_in=profile.defined_in,
                    is_defined=profile.defined_in is not None,
                    has_description=name in descriptions,
                    columns_produced=profile.columns_produced,
                    columns_consumed=profile.columns_consumed,
                    source_types=profile.source_types,
                    confidence_min=profile.confidence_min,
                    confidence_max=profile.confidence_max,
                    transform_types=profile.transform_types,
                    last_modified=_timestamp(profile.last_modified),
                    first_seen=_timestamp(profile.first_seen),
                    modified_count=profile.modified_count,
                    previous_names=[
                        {"name": previous_name, "changed_at": changed_at.isoformat()}
                        for previous_name, changed_at in profile.previous_names
                    ],
                    is_dropped=profile.dropped_at is not None,
                    dropped_at=_timestamp(profile.dropped_at),
                    pending_count=pending_count,
                )
            )
        return CapabilityResult(
            extra={"assets": assets, "skipped": skipped, "truncated": len(params.tables) > _MAX_TABLES}
        )

    def vocabulary(self, result: CapabilityResult) -> set[str]:
        vocabulary: set[str] = set()
        for asset in result.extra.get("assets", []):
            vocabulary.add(asset.name)
            vocabulary.update(asset.columns_produced)
            vocabulary.update(asset.columns_consumed)
            vocabulary.update(item["name"] for item in asset.previous_names)
        vocabulary.update(item["mention"] for item in result.extra.get("skipped", []))
        return vocabulary

    def prompt_rules(self) -> str:
        return (
            "For a root-cause question, find upstream tables first, then call get_asset once with the entire "
            "list to compare change times; do not spend one tool call per table."
        )

    def template(self, result: CapabilityResult) -> str:
        assets = sorted(
            result.extra.get("assets", []),
            key=lambda asset: (asset.last_modified is not None, asset.last_modified or ""),
            reverse=True,
        )
        lines = []
        for asset in assets:
            if asset.last_modified is None:
                lines.append(
                    f"{asset.name}: không rõ thời điểm thay đổi — "
                    "không file nào trong dữ liệu đã ingest định nghĩa bảng này."
                )
            else:
                lines.append(
                    f"{asset.name}: last modified {asset.last_modified} ({asset.modified_count} modification(s))"
                )
        if result.extra.get("skipped"):
            lines.append("Skipped: " + ", ".join(item["mention"] for item in result.extra["skipped"]))
        if result.extra.get("truncated"):
            lines.append("Only the first 20 tables were returned.")
        return "\n".join(lines)


GET_ASSET_CAPABILITY = GetAssetCapability()
