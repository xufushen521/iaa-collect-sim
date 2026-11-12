from __future__ import annotations

import copy
import random
from collections import Counter
from typing import Any

from .model import GameState, Tile


def choose_tile(
    game: GameState,
    policy: str,
    rng: random.Random,
    mixed_random_probability: float = 0.28,
) -> Tile | None:
    visible = game.visible_tiles()
    if not visible:
        return None
    if policy == "random":
        return rng.choice(visible)
    if policy == "mixed" and rng.random() < mixed_random_probability:
        return rng.choice(visible)

    slot_counts = Counter(tile.symbol for tile in game.slots)
    visible_counts = Counter(tile.symbol for tile in visible)

    def score(tile: Tile) -> tuple[float, float]:
        in_slot = slot_counts.get(tile.symbol, 0)
        visible_same = visible_counts.get(tile.symbol, 0)
        if policy == "same_symbol":
            score_value = in_slot * 10.0 + tile.layer * 0.1
        else:
            score_value = (
                in_slot * 100.0
                + min(visible_same, game.match_count) * 12.0
                + tile.layer * 0.2
            )
        return score_value, rng.random()

    return max(visible, key=score)


def _maybe_use_shuffle(
    game: GameState,
    decision_rng: random.Random,
    probability: float,
) -> None:
    if probability <= 0 or game.status != "playing":
        return
    if game.slot_count < game.slot_capacity - 2:
        return
    slot_counts = Counter(tile.symbol for tile in game.slots)
    visible = game.visible_tiles()
    can_extend_group = any(slot_counts.get(tile.symbol, 0) > 0 for tile in visible)
    if game.slot_count < game.slot_capacity - 1 and can_extend_group:
        return
    if decision_rng.random() >= probability:
        return
    game.use_shuffle()


def simulate_level(
    config: dict[str, Any],
    level: dict[str, Any],
    seed: int,
    policy: str | None = None,
    ad_accept_probability: float | None = None,
    starting_coins: float | None = None,
    record_events: bool = False,
    scenario: str = "default",
) -> dict[str, Any]:
    simulation_config = config["simulation"]
    policy = policy or simulation_config["default_policy"]
    accept_probability = (
        float(simulation_config["ad_accept_probability"])
        if ad_accept_probability is None
        else float(ad_accept_probability)
    )
    decision_rng = random.Random(int(seed) ^ 0x5F3759DF)
    game = GameState(
        config=config,
        level=level,
        seed=seed,
        starting_coins=starting_coins,
        record_events=record_events,
    )
    max_actions = int(simulation_config["max_actions_per_run"])
    actions = 0

    while game.status in {"playing", "failed"} and actions < max_actions:
        actions += 1
        if game.status == "failed":
            if game.rescue_pending and decision_rng.random() < accept_probability:
                game.rescue_with_ad()
                continue
            if game.rescue_pending:
                game.decline_rescue()
            break

        _maybe_use_shuffle(
            game,
            decision_rng,
            float(simulation_config["shuffle_probability_when_at_risk"]),
        )
        selected = choose_tile(
            game,
            policy,
            decision_rng,
            float(simulation_config.get("mixed_random_probability", 0.28)),
        )
        if selected is None:
            game._fail("no_accessible_tile")
            continue
        game.select_tile(selected.id)

    if game.status == "playing":
        game._fail("action_limit")

    summary = game.summary()
    summary.update(
        {
            "scenario": scenario,
            "policy": policy,
            "ad_accept_probability": accept_probability,
            "max_ads_per_level": int(config["rules"]["max_ads_per_level"]),
            "events": game.events,
        }
    )
    return summary


def simulate_experiment(
    config: dict[str, Any],
    players_per_cell: int = 300,
    seed: int = 20261110,
    policies: tuple[str, ...] = ("lookahead",),
    ad_caps: tuple[int, ...] = (0, 1, 2),
    record_events: bool = False,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for policy_index, policy in enumerate(policies):
        for cap_index, ad_cap in enumerate(ad_caps):
            scenario_config = copy.deepcopy(config)
            scenario_config["rules"]["max_ads_per_level"] = int(ad_cap)
            scenario = f"广告上限{ad_cap}次"
            for level in config["levels"]:
                for player_index in range(players_per_cell):
                    run_seed = (
                        int(seed)
                        + int(level["id"]) * 100_003
                        + policy_index * 10_007
                        + cap_index * 1_009
                        + player_index
                    )
                    result = simulate_level(
                        scenario_config,
                        level,
                        run_seed,
                        policy=policy,
                        scenario=scenario,
                        record_events=record_events,
                    )
                    result.pop("events", None)
                    results.append(result)
    return results


def simulate_campaign(
    config: dict[str, Any],
    players: int = 500,
    seed: int = 20261110,
    policy: str | None = None,
    scenario: str = "默认关卡链",
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    policy = policy or config["simulation"]["default_policy"]
    for player_index in range(players):
        coins = float(config["economy"]["starting_coins"])
        player_id = f"P{player_index + 1:05d}"
        for level in config["levels"]:
            run_seed = int(seed) + player_index * 10_007 + int(level["id"])
            result = simulate_level(
                config,
                level,
                run_seed,
                policy=policy,
                starting_coins=coins,
                record_events=False,
                scenario=scenario,
            )
            result["player_id"] = player_id
            coins = float(result["coins_end"])
            results.append(result)
    return results
