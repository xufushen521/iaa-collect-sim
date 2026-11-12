from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from engine.analytics import summarize_results, write_csv, write_json
from engine.loader import load_config
from engine.simulator import simulate_campaign, simulate_experiment


def build_report(summary: list[dict], campaign_summary: list[dict]) -> str:
    overall_by_policy_cap: dict[tuple[str, str], dict] = {}
    for row in summary:
        key = (row["policy"], row["scenario"])
        overall_by_policy_cap.setdefault(
            key,
            {"runs": 0, "wins": 0, "ad_watches": 0.0, "coins_end": 0.0},
        )
        bucket = overall_by_policy_cap[key]
        bucket["runs"] += int(row["runs"])
        bucket["wins"] += float(row["clear_rate"]) * int(row["runs"])
        bucket["ad_watches"] += float(row["ad_watch_rate"]) * int(row["runs"])
        bucket["coins_end"] += float(row["avg_coins_end"]) * int(row["runs"])

    lines = [
        "# IAA 七格收集三消实验报告",
        "",
        "优先级：U1",
        "",
        "本报告由 `scripts/run_simulation.py` 生成。数值是机器人基线与参数假设，不代表真实玩家或商业收入。",
        "",
        "## 核心结论",
        "",
    ]
    for (policy, scenario), bucket in sorted(overall_by_policy_cap.items()):
        runs = max(1, bucket["runs"])
        lines.append(
            f"- {policy} / {scenario}：通关率 {bucket['wins'] / runs:.1%}，"
            f"人均广告观看 {bucket['ad_watches'] / runs:.2f} 次，"
            f"平均期末金币 {bucket['coins_end'] / runs:.1f}。"
        )

    middle_rows = [
        row
        for row in summary
        if 3 <= int(row["level_id"]) <= 6
        and row["scenario"] == "广告上限1次"
        and row["policy"] == "mixed"
    ]
    if middle_rows:
        clear_rates = [float(row["clear_rate"]) for row in middle_rows]
        lines.extend(
            [
                "",
                "## 难度观察",
                "",
                f"- 混合操作策略下，第 3–6 关在单次广告救援时通关率范围 "
                f"{min(clear_rates):.1%}–{max(clear_rates):.1%}。",
                "- 若某一关通关率过低，优先检查层间遮挡和符号可达性，不用无限增加广告频次补偿。",
                "",
                "## 金币循环观察",
                "",
            ]
        )
        max_zero = max(float(row["coin_zero_rate"]) for row in campaign_summary)
        max_unaffordable = max(
            float(row["prop_unaffordable_rate"]) for row in campaign_summary
        )
        lines.append(
            f"- 关卡链最高期末零币率 {max_zero:.1%}，"
            f"最高道具买不起概率 {max_unaffordable:.1%}。"
        )
        lines.append(
            "- 金币只承担道具消费，不承担关卡入场；因此广告救援与金币压力可以分开评估。"
        )

    lines.extend(
        [
            "",
            "## 设计口径",
            "",
            "- 广告只出现在失败救援节点，首版每关最多 1 次。",
            "- 广告验收看“提供率、接受率、救援后通关率”，不只看观看次数。",
            "- 难度验收同时看通关率、平均操作数、死局原因和金币可负担性。",
            "- 结论用于作品集展示参数化方法和分析链，不宣称能预测任何具体产品收入。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--players", type=int, default=300)
    parser.add_argument("--campaign-players", type=int, default=500)
    parser.add_argument("--seed", type=int, default=20261110)
    parser.add_argument("--output-dir", type=Path, default=PROJECT_DIR / "outputs")
    args = parser.parse_args()

    config = load_config()
    raw_results = simulate_experiment(
        config,
        players_per_cell=args.players,
        seed=args.seed,
        policies=("random", "mixed", "lookahead"),
        ad_caps=(0, 1, 2),
    )
    level_summary = summarize_results(
        raw_results,
        ("scenario", "policy", "level_id", "level_name"),
    )

    campaign_rows = simulate_campaign(
        config,
        players=args.campaign_players,
        seed=args.seed,
    )
    campaign_summary = summarize_results(
        campaign_rows,
        ("scenario", "policy", "level_id", "level_name"),
    )

    output_dir = args.output_dir
    write_csv(output_dir / "level_summary.csv", level_summary)
    write_csv(output_dir / "campaign_level_summary.csv", campaign_summary)
    write_csv(output_dir / "campaign_runs.csv", campaign_rows)
    write_json(
        output_dir / "run_metadata.json",
        {
            "seed": args.seed,
            "players_per_cell": args.players,
            "campaign_players": args.campaign_players,
            "policies": ["random", "mixed", "lookahead"],
            "ad_caps": [0, 1, 2],
            "reference_note": config["meta"]["reference_note"],
        },
    )
    report = build_report(level_summary, campaign_summary)
    (output_dir / "EXPERIMENT_REPORT.md").write_text(report, encoding="utf-8")
    print(json.dumps({"rows": len(raw_results), "campaign_rows": len(campaign_rows)}))
    print(f"outputs: {output_dir}")


if __name__ == "__main__":
    main()
