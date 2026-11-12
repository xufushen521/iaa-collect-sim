from __future__ import annotations

import copy
import random
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class Tile:
    id: int
    symbol: str
    x: float
    y: float
    layer: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _allocate_layer_counts(total: int, weights: list[float]) -> list[int]:
    raw = [total * float(weight) for weight in weights]
    counts = [int(value) for value in raw]
    remainder = total - sum(counts)
    order = sorted(
        range(len(raw)),
        key=lambda index: (raw[index] - counts[index], weights[index]),
        reverse=True,
    )
    for index in order[:remainder]:
        counts[index] += 1
    return counts


def _layer_positions(level: dict[str, Any], layer: int) -> list[tuple[float, float]]:
    rows = max(2, int(level["rows"]) - layer)
    cols = max(2, int(level["cols"]) - layer)
    offset_x = 0.5 if layer % 2 else 0.0
    offset_y = 0.5 if layer % 2 else 0.0
    return [
        (
            row - (rows - 1) / 2 + offset_y,
            col - (cols - 1) / 2 + offset_x,
        )
        for row in range(rows)
        for col in range(cols)
    ]


def generate_tiles(
    config: dict[str, Any],
    level: dict[str, Any],
    rng: random.Random,
) -> list[Tile]:
    tile_count = int(level["tile_count"])
    match_count = int(config["rules"]["match_count"])
    symbol_ids = [
        item["id"] for item in config["symbol_pool"][: int(level["symbol_count"])]
    ]

    symbols: list[str] = []
    triple_index = 0
    while len(symbols) < tile_count:
        symbol = symbol_ids[triple_index % len(symbol_ids)]
        symbols.extend([symbol] * match_count)
        triple_index += 1
    rng.shuffle(symbols)

    layer_counts = _allocate_layer_counts(tile_count, level["layer_weights"])
    positions: list[tuple[float, float, int]] = []
    for layer, count in enumerate(layer_counts):
        candidates = _layer_positions(level, layer)
        if count > len(candidates):
            raise ValueError(f"第 {layer + 1} 层的候选位置不足")
        selected = rng.sample(candidates, count)
        positions.extend((x, y, layer) for x, y in selected)

    rng.shuffle(positions)
    return [
        Tile(
            id=index,
            symbol=symbol,
            x=round(position[0], 3),
            y=round(position[1], 3),
            layer=position[2],
        )
        for index, (symbol, position) in enumerate(zip(symbols, positions))
    ]


class GameState:
    def __init__(
        self,
        config: dict[str, Any],
        level: dict[str, Any],
        seed: int,
        starting_coins: float | None = None,
        record_events: bool = True,
    ) -> None:
        self.config = config
        self.level = level
        self.seed = int(seed)
        self.rng = random.Random(seed)
        self.tiles: dict[int, Tile] = {
            tile.id: tile for tile in generate_tiles(config, level, self.rng)
        }
        self.slots: list[Tile] = []
        self.status = "playing"
        self.failure_reason: str | None = None
        self.steps_remaining = int(level["steps"])
        initial = (
            float(starting_coins)
            if starting_coins is not None
            else float(config["economy"]["starting_coins"])
        )
        self.coins = initial
        self.ads_used = 0
        self.rescue_pending = False
        self._undo_snapshot: dict[str, Any] | None = None
        self.events: list[dict[str, Any]] = []
        self._event_seq = 0
        self.record_events = record_events
        self.stats: dict[str, Any] = {
            "tile_clicks": 0,
            "matches": 0,
            "tiles_cleared": 0,
            "slot_peak": 0,
            "shuffle_uses": 0,
            "undo_uses": 0,
            "ad_offers": 0,
            "ad_watches": 0,
            "ad_declines": 0,
            "rescues": 0,
            "prop_attempts": 0,
            "prop_unaffordable": 0,
            "coins_start": initial,
            "coins_earned": 0.0,
            "coins_spent": 0.0,
        }
        self._log("level_start", initial_coins=initial)

    @property
    def level_id(self) -> int:
        return int(self.level["id"])

    @property
    def slot_capacity(self) -> int:
        return int(self.config["rules"]["slot_capacity"])

    @property
    def match_count(self) -> int:
        return int(self.config["rules"]["match_count"])

    @property
    def board_remaining(self) -> int:
        return len(self.tiles)

    @property
    def slot_count(self) -> int:
        return len(self.slots)

    def _log(self, event_type: str, **payload: Any) -> None:
        if not self.record_events:
            return
        self._event_seq += 1
        event = {
            "event_seq": self._event_seq,
            "game_id": f"L{self.level_id}-S{self.seed}",
            "level_id": self.level_id,
            "level_name": self.level["name"],
            "event_type": event_type,
            "status": self.status,
            "steps_remaining": self.steps_remaining,
            "board_remaining": self.board_remaining,
            "slot_count": self.slot_count,
            "coins": round(self.coins, 2),
            "ads_used": self.ads_used,
        }
        event.update(payload)
        self.events.append(event)

    def symbol_details(self, symbol_id: str) -> dict[str, str]:
        for symbol in self.config["symbol_pool"]:
            if symbol["id"] == symbol_id:
                return symbol
        return {"id": symbol_id, "name": symbol_id, "glyph": "?"}

    def is_visible(self, tile: Tile) -> bool:
        if tile.id not in self.tiles:
            return False
        threshold = float(self.config["rules"]["overlap_threshold"])
        for other in self.tiles.values():
            if other.layer <= tile.layer:
                continue
            if abs(other.x - tile.x) < threshold and abs(other.y - tile.y) < threshold:
                return False
        return True

    def visible_tiles(self) -> list[Tile]:
        return sorted(
            (tile for tile in self.tiles.values() if self.is_visible(tile)),
            key=lambda tile: (-tile.layer, tile.y, tile.x, tile.id),
        )

    def slot_counts(self) -> Counter[str]:
        return Counter(tile.symbol for tile in self.slots)

    def _undo_state(self) -> dict[str, Any]:
        return {
            "active_ids": set(self.tiles),
            "slots": list(self.slots),
            "steps_remaining": self.steps_remaining,
        }

    def _award_coins(self, amount: float, source: str) -> None:
        amount = max(0.0, float(amount))
        self.coins += amount
        self.stats["coins_earned"] += amount
        self._log("coins_earned", amount=round(amount, 2), source=source)

    def _spend_coins(self, amount: float, sink: str) -> bool:
        amount = max(0.0, float(amount))
        if self.coins + 1e-9 < amount:
            return False
        self.coins -= amount
        self.stats["coins_spent"] += amount
        self._log("coins_spent", amount=round(amount, 2), sink=sink)
        return True

    def _insert_slot(self, tile: Tile) -> None:
        matching_indexes = [
            index for index, slot_tile in enumerate(self.slots) if slot_tile.symbol == tile.symbol
        ]
        if matching_indexes:
            self.slots.insert(matching_indexes[-1] + 1, tile)
        else:
            self.slots.append(tile)

    def select_tile(self, tile_id: int) -> bool:
        if self.status != "playing":
            return False
        tile = self.tiles.get(int(tile_id))
        if tile is None or not self.is_visible(tile):
            return False

        self._undo_snapshot = self._undo_state()
        del self.tiles[tile.id]
        self._insert_slot(tile)
        self.steps_remaining -= 1
        self.stats["tile_clicks"] += 1
        self.stats["slot_peak"] = max(self.stats["slot_peak"], self.slot_count)

        match_cleared = False
        symbol_count = sum(1 for slot_tile in self.slots if slot_tile.symbol == tile.symbol)
        if symbol_count >= self.match_count:
            removed = 0
            new_slots: list[Tile] = []
            for slot_tile in self.slots:
                if slot_tile.symbol == tile.symbol and removed < self.match_count:
                    removed += 1
                    continue
                new_slots.append(slot_tile)
            self.slots = new_slots
            self.stats["matches"] += 1
            self.stats["tiles_cleared"] += removed
            match_cleared = True
            self._undo_snapshot = None

        self._log(
            "tile_selected",
            tile_id=tile.id,
            symbol=tile.symbol,
            layer=tile.layer + 1,
            match_cleared=match_cleared,
        )
        self._evaluate_status()
        return True

    def _evaluate_status(self) -> None:
        if not self.tiles and not self.slots:
            self.status = "won"
            reward = float(self.config["economy"]["clear_reward_base"])
            reward += float(self.config["economy"]["clear_reward_per_step"]) * self.steps_remaining
            if self.stats["shuffle_uses"] == 0 and self.stats["undo_uses"] == 0:
                reward += float(self.config["economy"]["perfect_clear_bonus"])
            self._award_coins(reward, "clear_reward")
            self._log("level_end", result="won")
            return

        if self.slot_count >= self.slot_capacity:
            self._fail("slot_overflow")
            return
        if self.steps_remaining <= 0:
            self._fail("steps_exhausted")
            return
        if not self.visible_tiles():
            self._fail("no_accessible_tile")

    def _fail(self, reason: str) -> None:
        self.status = "failed"
        self.failure_reason = reason
        self.rescue_pending = self.can_rescue()
        if self.rescue_pending:
            self.stats["ad_offers"] += 1
            self._log("ad_offer", failure_reason=reason)
        else:
            self._log("level_end", result="failed", failure_reason=reason)

    def can_rescue(self) -> bool:
        return (
            self.status == "failed"
            and self.ads_used < int(self.config["rules"]["max_ads_per_level"])
            and (bool(self.slots) or self.steps_remaining <= 0)
        )

    def decline_rescue(self) -> bool:
        if not self.rescue_pending:
            return False
        self.rescue_pending = False
        self.stats["ad_declines"] += 1
        self._log("ad_declined", failure_reason=self.failure_reason)
        self._log("level_end", result="failed", failure_reason=self.failure_reason)
        return True

    def rescue_with_ad(self) -> bool:
        if not self.rescue_pending:
            return False
        remove_count = int(self.config["rules"]["rescue_remove_count"])
        returned = self.slots[-remove_count:]
        self.slots = self.slots[:-remove_count]
        for tile in returned:
            self.tiles[tile.id] = tile
        self.steps_remaining += int(self.config["rules"]["rescue_bonus_steps"])
        self.ads_used += 1
        self.stats["ad_watches"] += 1
        self.stats["rescues"] += 1
        self.status = "playing"
        self.failure_reason = None
        self.rescue_pending = False
        self._undo_snapshot = None
        ad_reward = float(self.config["economy"].get("ad_coin_reward", 0.0))
        self._log(
            "ad_completed",
            returned_tiles=len(returned),
            bonus_steps=int(self.config["rules"]["rescue_bonus_steps"]),
        )
        if ad_reward:
            self._award_coins(ad_reward, "rewarded_ad")
        if not self.visible_tiles() and self.tiles:
            self._fail("no_accessible_tile")
        return True

    def use_shuffle(self) -> bool:
        if self.status != "playing":
            return False
        cost = float(self.config["economy"]["shuffle_cost"])
        self.stats["prop_attempts"] += 1
        if self.coins + 1e-9 < cost:
            self.stats["prop_unaffordable"] += 1
            self._log("prop_unaffordable", prop="shuffle", cost=cost)
            return False
        if not self._spend_coins(cost, "shuffle"):
            return False
        symbols = [tile.symbol for tile in self.tiles.values()]
        self.rng.shuffle(symbols)
        for tile, symbol in zip(self.tiles.values(), symbols):
            tile.symbol = symbol
        self.stats["shuffle_uses"] += 1
        self._undo_snapshot = None
        self._log("prop_used", prop="shuffle", cost=cost)
        if not self.visible_tiles():
            self._fail("no_accessible_tile")
        return True

    def use_undo(self) -> bool:
        if self.status != "playing" or self._undo_snapshot is None:
            return False
        cost = float(self.config["economy"]["undo_cost"])
        self.stats["prop_attempts"] += 1
        if self.coins + 1e-9 < cost:
            self.stats["prop_unaffordable"] += 1
            self._log("prop_unaffordable", prop="undo", cost=cost)
            return False
        snapshot = copy.deepcopy(self._undo_snapshot)
        if not self._spend_coins(cost, "undo"):
            return False
        for tile_id in snapshot["active_ids"]:
            if tile_id not in self.tiles:
                tile = next((item for item in self.slots if item.id == tile_id), None)
                if tile is not None:
                    self.tiles[tile.id] = tile
        self.slots = snapshot["slots"]
        self.steps_remaining = snapshot["steps_remaining"]
        self.stats["undo_uses"] += 1
        self._undo_snapshot = None
        self._log("prop_used", prop="undo", cost=cost)
        return True

    def summary(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "level_id": self.level_id,
            "level_name": self.level["name"],
            "result": self.status,
            "failure_reason": self.failure_reason,
            "tile_clicks": self.stats["tile_clicks"],
            "matches": self.stats["matches"],
            "tiles_cleared": self.stats["tiles_cleared"],
            "board_remaining": self.board_remaining,
            "slots_remaining": self.slot_count,
            "slot_peak": self.stats["slot_peak"],
            "steps_remaining": self.steps_remaining,
            "shuffle_uses": self.stats["shuffle_uses"],
            "undo_uses": self.stats["undo_uses"],
            "ad_offers": self.stats["ad_offers"],
            "ad_watches": self.stats["ad_watches"],
            "ad_declines": self.stats["ad_declines"],
            "rescues": self.stats["rescues"],
            "prop_attempts": self.stats["prop_attempts"],
            "prop_unaffordable": self.stats["prop_unaffordable"],
            "coins_start": self.stats["coins_start"],
            "coins_earned": self.stats["coins_earned"],
            "coins_spent": self.stats["coins_spent"],
            "coins_end": round(self.coins, 2),
            "coin_zero_end": self.coins <= 0,
        }
