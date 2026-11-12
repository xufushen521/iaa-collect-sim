from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = PROJECT_DIR / "config.json"


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    with config_path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    validate_config(config)
    return config


def validate_config(config: dict[str, Any]) -> None:
    required = {"meta", "rules", "economy", "simulation", "symbol_pool", "levels"}
    missing = required.difference(config)
    if missing:
        raise ValueError(f"配置缺少字段: {sorted(missing)}")

    rules = config["rules"]
    if int(rules["slot_capacity"]) < int(rules["match_count"]):
        raise ValueError("槽容量不能小于消除数量")
    if int(rules["match_count"]) < 2:
        raise ValueError("消除数量至少为 2")
    if int(rules["max_ads_per_level"]) < 0:
        raise ValueError("广告次数不能为负数")

    economy = config["economy"]
    for key in ("starting_coins", "shuffle_cost", "undo_cost"):
        if float(economy[key]) < 0:
            raise ValueError(f"{key} 不能为负数")

    pool_size = len(config["symbol_pool"])
    level_ids: set[int] = set()
    for level in config["levels"]:
        level_id = int(level["id"])
        if level_id in level_ids:
            raise ValueError(f"关卡 ID 重复: {level_id}")
        level_ids.add(level_id)

        if int(level["tile_count"]) % int(rules["match_count"]) != 0:
            raise ValueError(f"关卡 {level_id} 的牌数必须能被消除数量整除")
        if not 1 <= int(level["symbol_count"]) <= pool_size:
            raise ValueError(f"关卡 {level_id} 的符号数超出 symbol_pool")
        if int(level["layers"]) < 1:
            raise ValueError(f"关卡 {level_id} 至少需要一层")
        if int(level["steps"]) < int(level["tile_count"]):
            raise ValueError(
                f"关卡 {level_id} 的步数小于牌数；当前规则每选一张牌消耗一步，"
                "因此该配置数学上不可能清空牌面"
            )
        if len(level["layer_weights"]) != int(level["layers"]):
            raise ValueError(f"关卡 {level_id} 的 layer_weights 数量必须与层数一致")
        if abs(sum(float(value) for value in level["layer_weights"]) - 1.0) > 1e-6:
            raise ValueError(f"关卡 {level_id} 的 layer_weights 之和必须为 1")
