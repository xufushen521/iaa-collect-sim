from __future__ import annotations

import unittest
from pathlib import Path
import sys


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from engine.loader import load_config, validate_config
from engine.simulator import simulate_experiment, simulate_level


class SimulatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_config()
        self.level = self.config["levels"][2]

    def test_same_seed_is_reproducible(self) -> None:
        first = simulate_level(self.config, self.level, seed=77)
        second = simulate_level(self.config, self.level, seed=77)
        first.pop("events")
        second.pop("events")
        self.assertEqual(first, second)

    def test_ad_cap_zero_prevents_ad_offer(self) -> None:
        config = load_config()
        config["rules"]["max_ads_per_level"] = 0
        result = simulate_level(
            config,
            self.level,
            seed=5,
            ad_accept_probability=1.0,
        )
        self.assertEqual(result["ad_offers"], 0)
        self.assertEqual(result["ad_watches"], 0)

    def test_experiment_returns_all_cells(self) -> None:
        results = simulate_experiment(
            self.config,
            players_per_cell=2,
            seed=8,
            policies=("random",),
            ad_caps=(0, 1),
        )
        self.assertEqual(len(results), len(self.config["levels"]) * 2 * 2)
        self.assertEqual(
            {row["scenario"] for row in results},
            {"广告上限0次", "广告上限1次"},
        )

    def test_invalid_config_is_rejected(self) -> None:
        config = load_config()
        config["levels"][0]["tile_count"] = 28
        with self.assertRaises(ValueError):
            validate_config(config)

    def test_steps_below_tile_count_are_rejected(self) -> None:
        config = load_config()
        config["levels"][0]["steps"] = config["levels"][0]["tile_count"] - 1
        with self.assertRaises(ValueError):
            validate_config(config)


if __name__ == "__main__":
    unittest.main()
