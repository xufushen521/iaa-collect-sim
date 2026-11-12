from __future__ import annotations

import random
import unittest
from pathlib import Path
import sys


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from engine.loader import load_config
from engine.model import GameState, Tile


class GameStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_config()
        self.level = self.config["levels"][0]

    def game_with_tiles(self, tiles: list[Tile], steps: int = 12) -> GameState:
        level = dict(self.level)
        level["steps"] = steps
        game = GameState(self.config, level, seed=1, record_events=True)
        game.tiles = {tile.id: tile for tile in tiles}
        game.slots = []
        game.steps_remaining = steps
        game.status = "playing"
        return game

    def test_higher_layer_blocks_lower_tile(self) -> None:
        tiles = [
            Tile(1, "coffee", 0.0, 0.0, 0),
            Tile(2, "cake", 0.0, 0.0, 1),
        ]
        game = self.game_with_tiles(tiles)
        self.assertFalse(game.is_visible(game.tiles[1]))
        self.assertTrue(game.is_visible(game.tiles[2]))

    def test_three_matching_tiles_clear(self) -> None:
        tiles = [
            Tile(index, "coffee", float(index), 0.0, 0)
            for index in range(1, 4)
        ]
        game = self.game_with_tiles(tiles)
        for tile_id in (1, 2, 3):
            self.assertTrue(game.select_tile(tile_id))
        self.assertEqual(game.slot_count, 0)
        self.assertEqual(game.stats["matches"], 1)
        self.assertEqual(game.status, "won")

    def test_slot_overflow_offers_ad(self) -> None:
        symbols = ["coffee", "cake", "bread", "tea", "flower", "book", "gift"]
        tiles = [
            Tile(index, symbol, float(index), 0.0, 0)
            for index, symbol in enumerate(symbols)
        ]
        game = self.game_with_tiles(tiles, steps=20)
        for tile_id in range(7):
            game.select_tile(tile_id)
        self.assertEqual(game.status, "failed")
        self.assertEqual(game.failure_reason, "slot_overflow")
        self.assertTrue(game.rescue_pending)

    def test_ad_rescue_returns_slot_tiles_and_resumes(self) -> None:
        symbols = ["coffee", "cake", "bread", "tea", "flower", "book", "gift"]
        tiles = [
            Tile(index, symbol, float(index), 0.0, 0)
            for index, symbol in enumerate(symbols)
        ]
        game = self.game_with_tiles(tiles, steps=20)
        for tile_id in range(7):
            game.select_tile(tile_id)
        before_board = game.board_remaining
        self.assertTrue(game.rescue_with_ad())
        self.assertEqual(game.status, "playing")
        self.assertEqual(game.board_remaining, before_board + 3)
        self.assertEqual(game.slot_count, 4)
        self.assertEqual(game.ads_used, 1)

    def test_undo_restores_last_selection_and_charges_coins(self) -> None:
        tiles = [
            Tile(1, "coffee", 0.0, 0.0, 0),
            Tile(2, "cake", 1.0, 0.0, 0),
        ]
        game = self.game_with_tiles(tiles)
        start_coins = game.coins
        start_steps = game.steps_remaining
        game.select_tile(1)
        self.assertTrue(game.use_undo())
        self.assertEqual(game.board_remaining, 2)
        self.assertEqual(game.slot_count, 0)
        self.assertEqual(game.steps_remaining, start_steps)
        self.assertEqual(
            game.coins,
            start_coins - self.config["economy"]["undo_cost"],
        )

    def test_shuffle_preserves_remaining_symbol_multiset(self) -> None:
        game = GameState(self.config, self.level, seed=9)
        before = sorted(tile.symbol for tile in game.tiles.values())
        self.assertTrue(game.use_shuffle())
        after = sorted(tile.symbol for tile in game.tiles.values())
        self.assertEqual(before, after)
        self.assertEqual(game.stats["shuffle_uses"], 1)

    def test_same_seed_generates_same_board(self) -> None:
        first = GameState(self.config, self.level, seed=44)
        second = GameState(self.config, self.level, seed=44)
        first_layout = [(tile.symbol, tile.x, tile.y, tile.layer) for tile in first.tiles.values()]
        second_layout = [(tile.symbol, tile.x, tile.y, tile.layer) for tile in second.tiles.values()]
        self.assertEqual(first_layout, second_layout)


if __name__ == "__main__":
    unittest.main()
