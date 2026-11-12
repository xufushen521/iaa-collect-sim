from __future__ import annotations

import random
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from engine.analytics import summarize_results
from engine.loader import load_config
from engine.model import GameState
from engine.simulator import simulate_experiment


PROJECT_DIR = Path(__file__).resolve().parent

st.set_page_config(
    page_title="IAA 七格收集三消",
    page_icon="🧩",
    layout="wide",
)

st.markdown(
    """
    <style>
    .block-container {padding-top: 1.6rem; padding-bottom: 2rem;}
    .hero {
        padding: 1.2rem 1.35rem;
        border-radius: 16px;
        background: linear-gradient(120deg, #f7f1e8 0%, #eef6f0 55%, #f3ecf7 100%);
        color: #25322b;
        margin-bottom: 1rem;
    }
    .hero h1 {font-size: 2rem; margin: 0 0 .35rem 0;}
    .hero p {margin: 0; color: #52605a;}
    .slot-card {
        min-height: 4.6rem;
        border: 1px solid #d9e0dc;
        border-radius: 12px;
        background: #fbfcfb;
        display: flex;
        align-items: center;
        justify-content: center;
        text-align: center;
        font-size: 1.8rem;
    }
    .small-note {color: #66736c; font-size: .9rem;}
    </style>
    """,
    unsafe_allow_html=True,
)


def load_game(
    level_id: int,
    seed: int,
    coins: float,
) -> GameState:
    config = load_config()
    level = next(item for item in config["levels"] if int(item["id"]) == level_id)
    return GameState(config, level, seed=seed, starting_coins=coins)


config = load_config()

if "game" not in st.session_state:
    st.session_state.seed = 20261110
    st.session_state.game = load_game(
        level_id=1,
        seed=st.session_state.seed,
        coins=float(config["economy"]["starting_coins"]),
    )
if "experiment" not in st.session_state:
    st.session_state.experiment = None

game: GameState = st.session_state.game

st.markdown(
    """
    <div class="hero">
      <h1>IAA 七格收集三消｜数值与广告经济</h1>
      <p>可玩规则、机器人模拟、广告救援和金币事件分析放在同一套参数下验证。</p>
    </div>
    """,
    unsafe_allow_html=True,
)

play_tab, analysis_tab, design_tab = st.tabs(["可玩原型", "数据分析", "设计说明"])

with play_tab:
    control_a, control_b, control_c, control_d = st.columns([1.35, 1, 1, 1])
    with control_a:
        level_id = st.selectbox(
            "关卡",
            options=[int(item["id"]) for item in config["levels"]],
            index=[int(item["id"]) for item in config["levels"]].index(game.level_id),
            format_func=lambda value: next(
                f"{item['id']} · {item['name']}" for item in config["levels"] if int(item["id"]) == value
            ),
        )
    with control_b:
        seed = st.number_input("随机种子", min_value=1, max_value=99999999, value=st.session_state.seed, step=1)
    with control_c:
        current_coins = st.number_input(
            "带入金币",
            min_value=0.0,
            value=float(game.coins),
            step=5.0,
        )
    with control_d:
        st.write("")
        st.write("")
        if st.button("载入新局", use_container_width=True, type="primary"):
            st.session_state.seed = int(seed)
            st.session_state.game = load_game(level_id, int(seed), float(current_coins))
            st.rerun()

    status_left, status_mid, status_right, status_far = st.columns(4)
    status_left.metric("剩余牌数", game.board_remaining)
    status_mid.metric("剩余步数", game.steps_remaining)
    status_right.metric("金币", f"{game.coins:.1f}")
    status_far.metric("广告救援", f"{game.ads_used}/{config['rules']['max_ads_per_level']}")

    if game.status == "playing":
        st.success(f"进行中 · 第 {game.level_id} 关 {game.level['name']}")
    elif game.status == "won":
        st.success(
            f"通关 · 操作 {game.stats['tile_clicks']} 次，"
            f"消除 {game.stats['matches']} 组，剩余金币 {game.coins:.1f}"
        )
    else:
        reason_names = {
            "slot_overflow": "七格槽已满",
            "steps_exhausted": "步数耗尽",
            "no_accessible_tile": "没有可点击牌面",
            "action_limit": "达到模拟动作上限",
        }
        st.error(f"失败 · {reason_names.get(game.failure_reason, game.failure_reason)}")

    slot_cols = st.columns(7)
    for index, column in enumerate(slot_cols):
        if index < len(game.slots):
            tile = game.slots[index]
            detail = game.symbol_details(tile.symbol)
            label = f"{detail['glyph']} {detail['name']}"
        else:
            label = "空"
        column.markdown(
            f"<div class='slot-card'>{label}</div>",
            unsafe_allow_html=True,
        )

    action_left, action_mid, action_right, action_end = st.columns(4)
    with action_left:
        shuffle_disabled = game.status != "playing" or game.coins < config["economy"]["shuffle_cost"]
        if st.button(
            f"洗牌 · {config['economy']['shuffle_cost']} 金币",
            use_container_width=True,
            disabled=shuffle_disabled,
        ):
            game.use_shuffle()
            st.rerun()
    with action_mid:
        undo_disabled = (
            game.status != "playing"
            or game._undo_snapshot is None
            or game.coins < config["economy"]["undo_cost"]
        )
        if st.button(
            f"撤销 · {config['economy']['undo_cost']} 金币",
            use_container_width=True,
            disabled=undo_disabled,
        ):
            game.use_undo()
            st.rerun()
    with action_right:
        if game.rescue_pending:
            if st.button("观看广告救援", use_container_width=True, type="primary"):
                game.rescue_with_ad()
                st.rerun()
        else:
            st.button("广告待失败后触发", use_container_width=True, disabled=True)
    with action_end:
        if game.status == "won" and game.level_id < max(int(item["id"]) for item in config["levels"]):
            if st.button("下一关", use_container_width=True):
                st.session_state.game = load_game(
                    game.level_id + 1,
                    random.randint(1, 99_999_999),
                    game.coins,
                )
                st.rerun()
        else:
            retry_coins = game.coins
            if st.button("重开本关", use_container_width=True):
                st.session_state.game = load_game(
                    game.level_id,
                    random.randint(1, 99_999_999),
                    retry_coins,
                )
                st.rerun()

    if game.rescue_pending:
        st.warning("失败节点：可观看一次激励视频，移出槽内最多 3 张牌并获得 2 步。")

    st.subheader("可点击牌面")
    st.caption("只显示当前没有被更高层遮挡的牌；点击后进入七格槽，三张同类自动消除。")
    visible = game.visible_tiles()
    if not visible:
        st.info("当前没有可点击牌面。")
    else:
        by_layer: dict[int, list] = {}
        for tile in visible:
            by_layer.setdefault(tile.layer, []).append(tile)
        for layer in sorted(by_layer, reverse=True):
            layer_tiles = by_layer[layer]
            st.markdown(f"**可点击 · 第 {layer + 1} 层**")
            columns = st.columns(min(5, len(layer_tiles)))
            for index, tile in enumerate(layer_tiles):
                detail = game.symbol_details(tile.symbol)
                key = f"tile-{game.level_id}-{game.seed}-{tile.id}-{game.stats['tile_clicks']}"
                if columns[index % len(columns)].button(
                    f"{detail['glyph']} {detail['name']}",
                    key=key,
                    use_container_width=True,
                    disabled=game.status != "playing",
                ):
                    game.select_tile(tile.id)
                    st.rerun()

    st.subheader("本局摘要")
    summary_cols = st.columns(5)
    summary_cols[0].metric("点击次数", game.stats["tile_clicks"])
    summary_cols[1].metric("消除组数", game.stats["matches"])
    summary_cols[2].metric("最高槽位", game.stats["slot_peak"])
    summary_cols[3].metric("洗牌次数", game.stats["shuffle_uses"])
    summary_cols[4].metric("广告观看", game.stats["ad_watches"])

    event_frame = pd.DataFrame(game.events)
    if not event_frame.empty:
        csv_bytes = event_frame.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "下载本局事件日志",
            data=csv_bytes,
            file_name=f"iaa_events_L{game.level_id}_S{game.seed}.csv",
            mime="text/csv",
        )

with analysis_tab:
    st.subheader("机器人基线实验")
    st.write(
        "比较随机、混合和同符号优先三种操作策略，并测试广告上限 0/1/2 次。"
        "数据用于检查参数与失败原因，不代表真人留存或广告收入。"
    )
    sample_col, seed_col, run_col = st.columns([1, 1, 1])
    players_per_cell = sample_col.number_input(
        "每个策略 × 广告档 × 关卡样本数",
        min_value=20,
        max_value=300,
        value=60,
        step=20,
    )
    experiment_seed = seed_col.number_input(
        "实验种子",
        min_value=1,
        max_value=99_999_999,
        value=20261110,
        step=1,
    )
    run_col.write("")
    run_col.write("")
    if run_col.button("运行实验", type="primary", use_container_width=True):
        with st.spinner("正在运行模拟..."):
            raw_results = simulate_experiment(
                config,
                players_per_cell=int(players_per_cell),
                seed=int(experiment_seed),
                policies=("random", "mixed", "lookahead"),
                ad_caps=(0, 1, 2),
            )
            summary_rows = summarize_results(
                raw_results,
                ("scenario", "policy", "level_id", "level_name"),
            )
            st.session_state.experiment = pd.DataFrame(summary_rows)

    experiment = st.session_state.experiment
    if experiment is None:
        st.info("点击“运行实验”生成本轮结果。")
    else:
        policy = st.segmented_control(
            "操作策略",
            options=["random", "mixed", "lookahead"],
            default="mixed",
        )
        selected = experiment[experiment["policy"] == policy].copy()
        selected["scenario"] = selected["scenario"].str.replace("广告上限", "上限 ", regex=False)
        fig = px.line(
            selected,
            x="level_id",
            y="clear_rate",
            color="scenario",
            markers=True,
            labels={
                "level_id": "关卡",
                "clear_rate": "通关率",
                "scenario": "广告救援",
            },
            title=f"{policy} 策略下的通关率曲线",
        )
        fig.update_yaxes(tickformat=".0%")
        st.plotly_chart(fig, use_container_width=True)

        display_columns = [
            "scenario",
            "level_id",
            "clear_rate",
            "avg_tile_clicks",
            "slot_overflow_rate",
            "ad_offer_rate",
            "ad_accept_rate",
            "rescue_clear_rate",
            "avg_coins_end",
            "coin_zero_rate",
        ]
        display = selected[display_columns].copy()
        for column in (
            "clear_rate",
            "slot_overflow_rate",
            "ad_offer_rate",
            "ad_accept_rate",
            "rescue_clear_rate",
            "coin_zero_rate",
        ):
            display[column] = display[column].map(lambda value: f"{float(value):.1%}")
        st.dataframe(display, use_container_width=True, hide_index=True)
        st.download_button(
            "下载完整实验汇总 CSV",
            data=experiment.to_csv(index=False).encode("utf-8-sig"),
            file_name="iaa_experiment_summary.csv",
            mime="text/csv",
        )

with design_tab:
    st.subheader("核心闭环")
    st.write(
        "点击可访问牌面 → 进入七格槽 → 三同消除 → 槽满则失败 → "
        "可选广告救援 → 通关获得金币 → 金币购买洗牌与撤销。"
    )
    st.subheader("三条设计边界")
    st.write(
        "1. 每选一张牌消耗一步，因此步数不能低于牌数，否则关卡数学上不可完成。"
    )
    st.write(
        "2. 广告只出现在失败救援节点，首版每关最多一次，避免在成功路径上强行打断。"
    )
    st.write(
        "3. 金币只承担局内道具消费，不承担关卡入场，因此广告体验与金币压力可以分开验证。"
    )
    st.subheader("分析指标")
    st.write(
        "通关率、平均操作数、最高槽位、七槽溢出率、广告提供率、广告接受率、"
        "救援后通关率、金币收支、零币率和道具买不起概率。"
    )
    with st.expander("当前配置摘要"):
        st.json(
            {
                "rules": config["rules"],
                "economy": config["economy"],
                "simulation": config["simulation"],
                "levels": [
                    {
                        "id": level["id"],
                        "name": level["name"],
                        "tiles": level["tile_count"],
                        "symbols": level["symbol_count"],
                        "layers": level["layers"],
                        "steps": level["steps"],
                    }
                    for level in config["levels"]
                ],
            }
        )
