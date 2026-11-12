from __future__ import annotations

import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


def _rate(rows: Iterable[dict[str, Any]], predicate) -> float:
    rows = list(rows)
    if not rows:
        return 0.0
    return sum(1 for row in rows if predicate(row)) / len(rows)


def summarize_results(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[tuple(row[key] for key in keys)].append(row)

    summaries: list[dict[str, Any]] = []
    for group_key, group_rows in sorted(groups.items()):
        output = dict(zip(keys, group_key))
        output.update(
            {
                "runs": len(group_rows),
                "clear_rate": _rate(group_rows, lambda row: row["result"] == "won"),
                "avg_tile_clicks": statistics.fmean(
                    float(row["tile_clicks"]) for row in group_rows
                ),
                "avg_steps_remaining": statistics.fmean(
                    float(row["steps_remaining"]) for row in group_rows
                ),
                "avg_slot_peak": statistics.fmean(
                    float(row["slot_peak"]) for row in group_rows
                ),
                "slot_overflow_rate": _rate(
                    group_rows, lambda row: row["failure_reason"] == "slot_overflow"
                ),
                "steps_exhausted_rate": _rate(
                    group_rows, lambda row: row["failure_reason"] == "steps_exhausted"
                ),
                "no_move_fail_rate": _rate(
                    group_rows, lambda row: row["failure_reason"] == "no_accessible_tile"
                ),
                "ad_offer_rate": _rate(group_rows, lambda row: float(row["ad_offers"]) > 0),
                "ad_watch_rate": statistics.fmean(
                    float(row["ad_watches"]) for row in group_rows
                ),
                "ad_accept_rate": (
                    sum(float(row["ad_watches"]) for row in group_rows)
                    / max(1.0, sum(float(row["ad_offers"]) for row in group_rows))
                ),
                "rescue_clear_rate": (
                    sum(
                        1
                        for row in group_rows
                        if float(row["rescues"]) > 0 and row["result"] == "won"
                    )
                    / max(1, sum(1 for row in group_rows if float(row["rescues"]) > 0))
                ),
                "avg_shuffle_uses": statistics.fmean(
                    float(row["shuffle_uses"]) for row in group_rows
                ),
                "avg_coins_earned": statistics.fmean(
                    float(row["coins_earned"]) for row in group_rows
                ),
                "avg_coins_spent": statistics.fmean(
                    float(row["coins_spent"]) for row in group_rows
                ),
                "avg_coins_end": statistics.fmean(
                    float(row["coins_end"]) for row in group_rows
                ),
                "coin_zero_rate": _rate(group_rows, lambda row: bool(row["coin_zero_end"])),
                "prop_unaffordable_rate": _rate(
                    group_rows, lambda row: float(row["prop_unaffordable"]) > 0
                ),
            }
        )
        summaries.append(output)
    return summaries


def write_csv(path: str | Path, rows: list[dict[str, Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0])
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: str | Path, payload: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
