#!/usr/bin/env python3
"""
Generate a static GitHub Pages site from the season comparison analysis.

Produces a self-contained HTML file in docs/index.html with:
- Interactive sortable tables
- Chart.js visualizations
- All comparison data embedded as JSON
- No server required (pure static HTML/CSS/JS)

Usage:
    # From split-season data (default):
    python generate_gh_pages.py --db data/mlb_stats.db --split-season

    # From two separate season databases:
    python generate_gh_pages.py --db1 data/mlb_stats_2023.db --db2 data/mlb_stats_2024.db --label1 2023 --label2 2024
"""
import argparse
import json
import os
import sys
import numpy as np
import pandas as pd
from datetime import datetime
from scipy import stats as scipy_stats
from collections import defaultdict

from src.database.db_manager import DatabaseManager
from src.database.models import Game, Player, PlayerGame, get_session, create_database
from src.analytics.weekly_analyzer import WeeklyAnalyzer
from sqlalchemy import func
from datetime import timedelta


def split_database_by_half(source_db_path, h1_db_path, h2_db_path):
    """Split a single-season database into first/second half."""
    from compare_seasons import split_database_by_half as split_fn
    split_fn(source_db_path, h1_db_path, h2_db_path)


def compute_weekly_metrics(db_path, stats_type, min_games=15):
    """Compute weekly analyzer metrics for qualifying players."""
    db = DatabaseManager(db_path=db_path)
    analyzer = WeeklyAnalyzer(db, scoring_system='draftkings')
    session = db.get_session()
    try:
        player_query = session.query(
            PlayerGame.player_id, func.count(PlayerGame.id).label('games')
        ).filter(
            PlayerGame.stats_type == stats_type
        ).group_by(PlayerGame.player_id
        ).having(func.count(PlayerGame.id) >= min_games).all()

        game_counts = {pid: count for pid, count in player_query}
        results = {}
        for pid, _ in player_query:
            try:
                metrics = analyzer.calculate_weekly_volatility(pid, stats_type, min_games=min_games)
                if metrics and metrics.get('bestball_score', 0) > 0:
                    player = session.query(Player).filter_by(player_id=pid).first()
                    if player:
                        metrics['player_name'] = player.player_name
                        metrics['player_id'] = pid
                        metrics['games_played'] = game_counts.get(pid, 0)
                        results[pid] = metrics
            except Exception:
                continue
        return results
    finally:
        session.close()


def compute_game_shape_metrics(db_path, stats_type='batting', min_games=15):
    """Compute game-level distribution shape metrics (Gini, CV, skew, etc.)."""
    db = DatabaseManager(db_path=db_path)
    session = db.get_session()

    players = session.query(
        PlayerGame.player_id, func.count(PlayerGame.id).label('games')
    ).filter(PlayerGame.stats_type == stats_type
    ).group_by(PlayerGame.player_id
    ).having(func.count(PlayerGame.id) >= min_games).all()

    results = {}
    for pid, gc in players:
        games = db.get_player_games(pid, stats_type)

        game_data = []
        for pg in games:
            game = session.query(Game).filter_by(game_pk=pg.game_pk).first()
            if game:
                game_data.append((game.game_date, pg.dk_points))
        game_data.sort(key=lambda x: x[0])
        points = np.array([p for _, p in game_data])

        if len(points) < min_games:
            continue
        mean_pts = np.mean(points)
        if mean_pts <= 0:
            continue

        std_pts = float(np.std(points, ddof=1))
        cv = float(std_pts / mean_pts)
        skew = float(scipy_stats.skew(points))
        kurt = float(scipy_stats.kurtosis(points))

        sorted_pts = np.sort(points)[::-1]
        top5_pct = float(np.sum(sorted_pts[:5]) / np.sum(points) * 100) if np.sum(points) > 0 else 0

        # Gini coefficient
        sorted_abs = np.sort(np.abs(points))
        n = len(sorted_abs)
        index = np.arange(1, n + 1)
        gini = float((2 * np.sum(index * sorted_abs) - (n + 1) * np.sum(sorted_abs)) / (n * np.sum(sorted_abs))) if np.sum(sorted_abs) > 0 else 0

        boom_threshold = 15.0 if stats_type == 'batting' else 20.0
        abs_boom_rate = float(np.sum(points >= boom_threshold) / len(points) * 100)

        player = session.query(Player).filter_by(player_id=pid).first()
        results[pid] = {
            'player_name': player.player_name if player else str(pid),
            'games': gc, 'mean': float(mean_pts), 'std': std_pts,
            'cv': cv, 'gini': gini, 'skew': skew, 'kurtosis': kurt,
            'top5_game_pct': top5_pct, 'abs_boom_rate': abs_boom_rate,
        }

    session.close()
    return results


def build_comparison_data(m1, m2, s1, s2, label1, label2, stats_type):
    """Build all comparison tables and stats."""
    common_ids = set(m1.keys()) & set(m2.keys())

    # Player comparison rows
    players = []
    for pid in common_ids:
        a, b = m1[pid], m2[pid]
        sa = s1.get(pid, {})
        sb = s2.get(pid, {})

        players.append({
            'player_id': int(pid),
            'player_name': a.get('player_name', str(pid)),
            'games_p1': a.get('games_played', 0),
            'games_p2': b.get('games_played', 0),
            'bb_score_p1': round(a.get('bestball_score', 0), 1),
            'bb_score_p2': round(b.get('bestball_score', 0), 1),
            'bb_change': round(b.get('bestball_score', 0) - a.get('bestball_score', 0), 1),
            'tear3_p1': round(a.get('tear3_rate', 0), 1),
            'tear3_p2': round(b.get('tear3_rate', 0), 1),
            'boom_rate_p1': round(a.get('boom_week_rate', 0), 1),
            'boom_rate_p2': round(b.get('boom_week_rate', 0), 1),
            'iv_p1': round(a.get('implied_volatility', 0), 2),
            'iv_p2': round(b.get('implied_volatility', 0), 2),
            'iv_tier_p1': a.get('iv_tier', 'N/A'),
            'iv_tier_p2': b.get('iv_tier', 'N/A'),
            'best_week_p1': round(a.get('best_week', 0), 1),
            'best_week_p2': round(b.get('best_week', 0), 1),
            'top3_avg_p1': round(a.get('top3_weeks_avg', 0), 1),
            'top3_avg_p2': round(b.get('top3_weeks_avg', 0), 1),
            'mean_week_p1': round(a.get('mean_week_points', 0), 1),
            'mean_week_p2': round(b.get('mean_week_points', 0), 1),
            'std_week_p1': round(a.get('std_week_points', 0), 2),
            'std_week_p2': round(b.get('std_week_points', 0), 2),
            'useful_pct_p1': round(a.get('useful_weeks_pct', 0), 1),
            'useful_pct_p2': round(b.get('useful_weeks_pct', 0), 1),
            'useful_ppw_p1': round(a.get('useful_points_per_week', 0), 1),
            'useful_ppw_p2': round(b.get('useful_points_per_week', 0), 1),
            'gini_p1': round(sa.get('gini', 0), 3),
            'gini_p2': round(sb.get('gini', 0), 3),
            'cv_game_p1': round(sa.get('cv', 0), 2),
            'cv_game_p2': round(sb.get('cv', 0), 2),
            'abs_boom_p1': round(sa.get('abs_boom_rate', 0), 1),
            'abs_boom_p2': round(sb.get('abs_boom_rate', 0), 1),
        })

    df = pd.DataFrame(players)

    # Correlations
    corr_metrics = [
        ('Best Ball Score', 'bb_score'), ('Mean Weekly Pts', 'mean_week'),
        ('Best Week', 'best_week'), ('Top 3 Weeks Avg', 'top3_avg'),
        ('Implied Volatility', 'iv'), ('Weekly Std Dev', 'std_week'),
        ('TEAR3 Rate', 'tear3'), ('Boom Week %', 'boom_rate'),
        ('USEFUL Week %', 'useful_pct'), ('USEFUL Pts/Week', 'useful_ppw'),
        ('Gini Coefficient', 'gini'), ('Game-Level CV', 'cv_game'),
        ('Abs Boom Rate (15+ DK)', 'abs_boom'),
    ]

    correlations = []
    for name, prefix in corr_metrics:
        c1, c2 = f'{prefix}_p1', f'{prefix}_p2'
        if c1 not in df.columns:
            continue
        valid = df[[c1, c2]].dropna()
        valid = valid[(valid[c1] != 0) | (valid[c2] != 0)]
        if len(valid) < 10:
            continue

        raw_r = float(valid[c1].corr(valid[c2]))

        # Talent-adjusted
        adj_r = None
        if prefix not in ('mean_week', 'bb_score'):
            needed = list(set(['mean_week_p1', 'mean_week_p2', c1, c2]))
            talent_cols = df[needed].dropna().copy()
            talent_cols = talent_cols[(talent_cols['mean_week_p1'] > 0) & (talent_cols['mean_week_p2'] > 0)]
            if len(talent_cols) >= 15:
                try:
                    s1r, i1r, _, _, _ = scipy_stats.linregress(talent_cols['mean_week_p1'], talent_cols[c1])
                    r1 = talent_cols[c1] - (s1r * talent_cols['mean_week_p1'] + i1r)
                    s2r, i2r, _, _, _ = scipy_stats.linregress(talent_cols['mean_week_p2'], talent_cols[c2])
                    r2 = talent_cols[c2] - (s2r * talent_cols['mean_week_p2'] + i2r)
                    adj_r = float(r1.corr(r2))
                except Exception:
                    adj_r = None

        correlations.append({
            'name': name, 'raw_r': round(raw_r, 3),
            'adj_r': round(adj_r, 3) if adj_r is not None else None,
            'n': len(valid),
        })

    # IV Tier transitions
    tier_order = ['Nuclear', 'Gamma', 'High-IV', 'Normal', 'Low-Vol']
    tier_matrix = {}
    for from_t in tier_order:
        tier_matrix[from_t] = {}
        for to_t in tier_order:
            tier_matrix[from_t][to_t] = 0

    for _, row in df.iterrows():
        t1 = row.get('iv_tier_p1', 'N/A')
        t2 = row.get('iv_tier_p2', 'N/A')
        if t1 in tier_order and t2 in tier_order:
            tier_matrix[t1][t2] += 1

    # Consistent stars
    top_n = min(30, len(df) // 3)
    top_p1 = set(df.sort_values('bb_score_p1', ascending=False).head(top_n)['player_id'].values)
    top_p2 = set(df.sort_values('bb_score_p2', ascending=False).head(top_n)['player_id'].values)
    consistent = [int(x) for x in top_p1 & top_p2]
    p1_only = [int(x) for x in top_p1 - top_p2]
    p2_only = [int(x) for x in top_p2 - top_p1]

    return {
        'label1': label1,
        'label2': label2,
        'stats_type': stats_type,
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'total_p1': len(m1),
        'total_p2': len(m2),
        'common': len(common_ids),
        'players': sorted(players, key=lambda x: x['bb_score_p1'], reverse=True),
        'correlations': correlations,
        'tier_matrix': tier_matrix,
        'tier_order': tier_order,
        'consistent_stars': consistent,
        'p1_only_stars': p1_only,
        'p2_only_stars': p2_only,
        'top_n': top_n,
    }


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MLB Best Ball: Year-Over-Year Streakiness Analysis</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
:root {
    --primary: #041E42;
    --accent: #C8102E;
    --bg: #f5f5f5;
    --card: #ffffff;
    --text: #333;
    --text2: #666;
    --border: #e0e0e0;
    --green: #2e7d32;
    --red: #c62828;
}
body { font-family: 'Segoe UI', system-ui, sans-serif; background: var(--bg); color: var(--text); line-height: 1.5; }
.container { max-width: 1400px; margin: 0 auto; padding: 20px; }
.header { background: linear-gradient(135deg, var(--primary) 0%, #062a52 100%); color: white; padding: 40px 30px; border-radius: 10px; margin-bottom: 24px; }
.header h1 { font-size: 2em; margin-bottom: 6px; }
.header .sub { opacity: 0.85; font-size: 1.05em; }
.header .meta { margin-top: 12px; display: flex; gap: 24px; font-size: 0.95em; opacity: 0.75; }
.tabs { display: flex; gap: 0; margin-bottom: 24px; border-bottom: 3px solid var(--primary); }
.tab { padding: 12px 24px; cursor: pointer; font-weight: 600; color: var(--text2); border: 1px solid var(--border); border-bottom: none; border-radius: 8px 8px 0 0; background: #eee; transition: all 0.2s; }
.tab.active { background: var(--primary); color: white; border-color: var(--primary); }
.tab:hover:not(.active) { background: #ddd; }
.section { display: none; }
.section.active { display: block; }
.card { background: var(--card); border-radius: 10px; padding: 24px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
.card h2 { font-size: 1.3em; margin-bottom: 4px; color: var(--primary); }
.card h3 { font-size: 1.05em; margin: 16px 0 8px; color: var(--text2); }
.card .desc { color: var(--text2); font-size: 0.9em; margin-bottom: 16px; }
table { width: 100%; border-collapse: collapse; font-size: 0.85em; }
th { background: var(--primary); color: white; padding: 10px 8px; text-align: left; cursor: pointer; user-select: none; white-space: nowrap; position: sticky; top: 0; z-index: 2; }
th:hover { background: #0a2f5c; }
th .arrow { font-size: 0.7em; margin-left: 2px; }
td { padding: 8px; border-bottom: 1px solid var(--border); white-space: nowrap; }
tr:hover td { background: #f0f4ff; }
tr:nth-child(even) td { background: #fafafa; }
tr:hover td { background: #e8eef7 !important; }
.pos { color: var(--green); font-weight: 600; }
.neg { color: var(--red); font-weight: 600; }
.neutral { color: var(--text2); }
.badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 0.78em; font-weight: 600; }
.badge-nuclear { background: #c62828; color: white; }
.badge-gamma { background: #e65100; color: white; }
.badge-highiv { background: #f9a825; color: #333; }
.badge-normal { background: #e0e0e0; color: #555; }
.badge-lowvol { background: #90caf9; color: #1a237e; }
.badge-persistent { background: #2e7d32; color: white; }
.badge-weak { background: #f9a825; color: #333; }
.badge-random { background: #ef5350; color: white; }
.bar-container { display: flex; align-items: center; gap: 8px; }
.bar { height: 16px; border-radius: 3px; min-width: 2px; }
.bar-pos { background: linear-gradient(90deg, #43a047, #2e7d32); }
.bar-neg { background: linear-gradient(90deg, #e53935, #c62828); }
.stat-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin: 16px 0; }
.stat-box { background: #f8f9fa; border-radius: 8px; padding: 16px; text-align: center; border: 1px solid var(--border); }
.stat-box .val { font-size: 2em; font-weight: 700; color: var(--primary); }
.stat-box .label { font-size: 0.85em; color: var(--text2); margin-top: 4px; }
.chart-row { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin: 16px 0; }
.chart-container { position: relative; height: 350px; }
.search { width: 100%; padding: 10px 16px; border: 2px solid var(--border); border-radius: 8px; font-size: 1em; margin-bottom: 12px; }
.search:focus { outline: none; border-color: var(--primary); }
.table-wrap { max-height: 600px; overflow-y: auto; border-radius: 8px; border: 1px solid var(--border); }
.tier-matrix { border-collapse: collapse; }
.tier-matrix th, .tier-matrix td { text-align: center; padding: 8px 12px; min-width: 80px; }
.tier-matrix td { font-weight: 600; }
.warning { background: #fff3e0; border-left: 4px solid #e65100; padding: 16px; border-radius: 0 8px 8px 0; margin: 16px 0; }
.warning .title { font-weight: 700; color: #e65100; margin-bottom: 4px; }
.filter-row { display: flex; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; align-items: center; }
.filter-row label { font-size: 0.85em; color: var(--text2); }
.filter-row select, .filter-row input { padding: 6px 10px; border: 1px solid var(--border); border-radius: 6px; font-size: 0.85em; }
@media (max-width: 900px) {
    .chart-row { grid-template-columns: 1fr; }
    .stat-grid { grid-template-columns: 1fr 1fr; }
    .container { padding: 10px; }
    .header { padding: 20px; }
    .header h1 { font-size: 1.4em; }
    table { font-size: 0.75em; }
    td, th { padding: 4px; }
}
</style>
</head>
<body>
<div class="container">
<div class="header">
    <h1>MLB Best Ball: Year-Over-Year Streakiness Analysis</h1>
    <div class="sub">Do TEAR rates, boom weeks, IV, and Gini persist across time periods?</div>
    <div class="meta">
        <span id="meta-periods"></span>
        <span id="meta-type"></span>
        <span id="meta-generated"></span>
    </div>
</div>

<div class="tabs" id="tabs">
    <div class="tab active" data-tab="overview">Overview</div>
    <div class="tab" data-tab="correlations">Persistence</div>
    <div class="tab" data-tab="players">Players</div>
    <div class="tab" data-tab="movers">Movers</div>
    <div class="tab" data-tab="tiers">IV Tiers</div>
    <div class="tab" data-tab="stars">Stars</div>
</div>

<!-- OVERVIEW -->
<div class="section active" id="sec-overview">
    <div class="stat-grid" id="overview-stats"></div>
    <div class="card">
        <h2>Metric Persistence</h2>
        <p class="desc">How well does each metric in Period 1 predict Period 2? Bars show correlation strength. Green = reliable signal, red = random noise.</p>
        <div class="chart-container" style="height:450px"><canvas id="corrChart"></canvas></div>
    </div>
    <div class="chart-row">
        <div class="card">
            <h2>Talent-Adjusted Persistence</h2>
            <p class="desc">After removing talent (mean weekly pts), which metrics still persist? This isolates true streakiness.</p>
            <div class="chart-container"><canvas id="adjCorrChart"></canvas></div>
        </div>
        <div class="card">
            <h2>BB Score Component Weights vs Persistence</h2>
            <p class="desc">Bubble size = weight in BB Score formula. X = talent-adjusted persistence. Red = adding noise.</p>
            <div class="chart-container"><canvas id="bubbleChart"></canvas></div>
        </div>
    </div>
    <div id="overviewWarning"></div>
</div>

<!-- CORRELATIONS -->
<div class="section" id="sec-correlations">
    <div class="card">
        <h2>Full Correlation Table</h2>
        <p class="desc">Raw correlation: Period 1 vs Period 2. Talent-Adjusted: after regressing out mean weekly pts.</p>
        <div class="table-wrap"><table id="corrTable"></table></div>
    </div>
    <div class="card">
        <h2>BB Score Formula Efficiency</h2>
        <p class="desc">What percentage of the BB Score's weight is allocated to metrics that actually persist?</p>
        <div class="chart-row">
            <div class="chart-container" style="height:280px"><canvas id="weightPie"></canvas></div>
            <div id="formulaBreakdown"></div>
        </div>
    </div>
</div>

<!-- PLAYERS -->
<div class="section" id="sec-players">
    <div class="card">
        <h2>Player Comparison Table</h2>
        <p class="desc">Click any column header to sort. Use the search box to find players.</p>
        <input type="text" class="search" id="playerSearch" placeholder="Search players...">
        <div class="filter-row">
            <label>Min Games (each period): <input type="number" id="minGames" value="20" min="1" max="100" style="width:60px"></label>
            <label>Sort by: <select id="sortCol">
                <option value="bb_score_p1">BB Score (P1)</option>
                <option value="bb_score_p2">BB Score (P2)</option>
                <option value="bb_change">BB Change</option>
                <option value="gini_p1">Gini (P1)</option>
                <option value="gini_p2">Gini (P2)</option>
                <option value="iv_p1">IV (P1)</option>
            </select></label>
        </div>
        <div class="table-wrap" style="max-height:700px"><table id="playerTable"></table></div>
    </div>
</div>

<!-- MOVERS -->
<div class="section" id="sec-movers">
    <div class="chart-row">
        <div class="card">
            <h2 id="risersTitle">Top 20 Risers</h2>
            <div class="table-wrap"><table id="risersTable"></table></div>
        </div>
        <div class="card">
            <h2 id="fallersTitle">Top 20 Fallers</h2>
            <div class="table-wrap"><table id="fallersTable"></table></div>
        </div>
    </div>
</div>

<!-- IV TIERS -->
<div class="section" id="sec-tiers">
    <div class="card">
        <h2>IV Tier Transition Matrix</h2>
        <p class="desc">Where do players end up in Period 2 based on their Period 1 IV tier? Higher diagonal % = more persistent.</p>
        <table class="tier-matrix" id="tierTable"></table>
    </div>
    <div class="card">
        <h2>Tier Flow</h2>
        <div class="chart-container" style="height:400px"><canvas id="tierChart"></canvas></div>
    </div>
</div>

<!-- CONSISTENT STARS -->
<div class="section" id="sec-stars">
    <div class="stat-grid" id="starStats"></div>
    <div class="chart-row">
        <div class="card">
            <h2 id="consistentTitle">Consistent Stars</h2>
            <p class="desc" id="consistentDesc"></p>
            <div class="table-wrap"><table id="consistentTable"></table></div>
        </div>
        <div class="card">
            <h2 id="p1OnlyTitle">Period 1 Only Stars</h2>
            <p class="desc" id="p1OnlyDesc"></p>
            <div class="table-wrap"><table id="p1OnlyTable"></table></div>
        </div>
    </div>
</div>
</div>

<script>
// ===== DATA (injected by generator) =====
const BATTING_DATA = __BATTING_JSON__;
const PITCHING_DATA = __PITCHING_JSON__;

let currentData = BATTING_DATA;

// ===== TAB NAVIGATION =====
document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
        tab.classList.add('active');
        document.getElementById('sec-' + tab.dataset.tab).classList.add('active');
    });
});

function tierBadge(tier) {
    const cls = {'Nuclear':'nuclear','Gamma':'gamma','High-IV':'highiv','Normal':'normal','Low-Vol':'lowvol'}[tier] || 'normal';
    return `<span class="badge badge-${cls}">${tier}</span>`;
}

function chgClass(val) { return val > 0 ? 'pos' : val < 0 ? 'neg' : 'neutral'; }
function fmt(v, d=1) { return v != null ? v.toFixed(d) : '-'; }
function fmtChg(v, d=1) { return v != null ? (v>0?'+':'') + v.toFixed(d) : '-'; }

function renderAll(data) {
    currentData = data;
    document.getElementById('meta-periods').textContent = `${data.label1} vs ${data.label2}`;
    document.getElementById('meta-type').textContent = data.stats_type.toUpperCase();
    document.getElementById('meta-generated').textContent = `Generated: ${data.generated_at}`;

    renderOverview(data);
    renderCorrelations(data);
    renderPlayers(data);
    renderMovers(data);
    renderTiers(data);
    renderStars(data);
}

// ===== OVERVIEW =====
function renderOverview(data) {
    const d = data;
    document.getElementById('overview-stats').innerHTML = [
        statBox(d.total_p1, `Players (${d.label1})`),
        statBox(d.total_p2, `Players (${d.label2})`),
        statBox(d.common, 'In Both Periods'),
        statBox(d.consistent_stars.length + '/' + d.top_n, 'Consistent Stars'),
        statBox(((d.consistent_stars.length / d.top_n)*100).toFixed(0)+'%', 'Retention Rate'),
    ].join('');

    // Correlation chart
    const corrs = data.correlations.filter(c => c.raw_r != null).sort((a,b) => Math.abs(b.raw_r) - Math.abs(a.raw_r));
    const corrCtx = document.getElementById('corrChart').getContext('2d');
    if (window._corrChart) window._corrChart.destroy();
    window._corrChart = new Chart(corrCtx, {
        type: 'bar',
        data: {
            labels: corrs.map(c => c.name),
            datasets: [{
                label: 'Raw Correlation',
                data: corrs.map(c => c.raw_r),
                backgroundColor: corrs.map(c => Math.abs(c.raw_r) >= 0.5 ? '#2e7d32' : Math.abs(c.raw_r) >= 0.3 ? '#f9a825' : '#ef5350'),
                borderRadius: 4,
            }]
        },
        options: {
            indexAxis: 'y',
            responsive: true, maintainAspectRatio: false,
            scales: { x: { min: -1, max: 1, grid: { color: '#eee' } } },
            plugins: { legend: { display: false } }
        }
    });

    // Talent-adjusted chart
    const adjCorrs = corrs.filter(c => c.adj_r != null);
    const adjCtx = document.getElementById('adjCorrChart').getContext('2d');
    if (window._adjChart) window._adjChart.destroy();
    window._adjChart = new Chart(adjCtx, {
        type: 'bar',
        data: {
            labels: adjCorrs.map(c => c.name),
            datasets: [
                { label: 'Raw', data: adjCorrs.map(c => c.raw_r), backgroundColor: 'rgba(4,30,66,0.3)', borderRadius: 4 },
                { label: 'Talent-Adjusted', data: adjCorrs.map(c => c.adj_r), backgroundColor: adjCorrs.map(c => Math.abs(c.adj_r) >= 0.3 ? '#2e7d32' : Math.abs(c.adj_r) >= 0.15 ? '#f9a825' : '#ef5350'), borderRadius: 4 },
            ]
        },
        options: {
            indexAxis: 'y', responsive: true, maintainAspectRatio: false,
            scales: { x: { min: -1, max: 1 } },
            plugins: { legend: { position: 'bottom' } }
        }
    });

    // Bubble chart
    const bbComponents = [
        { name: 'USEFUL PPW', weight: 25, key: 'USEFUL Pts/Week' },
        { name: 'USEFUL %', weight: 20, key: 'USEFUL Week %' },
        { name: 'Boom %', weight: 20, key: 'Boom Week %' },
        { name: 'TEAR3', weight: 15, key: 'TEAR3 Rate' },
        { name: 'IV', weight: 10, key: 'Implied Volatility' },
        { name: 'Top 3 Avg', weight: 5, key: 'Top 3 Weeks Avg' },
        { name: 'Gini', weight: 0, key: 'Gini Coefficient' },
    ];

    const bubbleData = bbComponents.map(comp => {
        const c = data.correlations.find(x => x.name === comp.key);
        return { x: c ? (c.adj_r != null ? c.adj_r : c.raw_r) : 0, y: c ? c.raw_r : 0, r: Math.max(comp.weight, 5), label: comp.name, weight: comp.weight };
    });

    const bubbleCtx = document.getElementById('bubbleChart').getContext('2d');
    if (window._bubbleChart) window._bubbleChart.destroy();
    window._bubbleChart = new Chart(bubbleCtx, {
        type: 'bubble',
        data: {
            datasets: [{
                data: bubbleData,
                backgroundColor: bubbleData.map(d => d.x >= 0.3 ? 'rgba(46,125,50,0.6)' : d.x >= 0.15 ? 'rgba(249,168,37,0.6)' : 'rgba(239,83,80,0.6)'),
                borderColor: bubbleData.map(d => d.x >= 0.3 ? '#2e7d32' : d.x >= 0.15 ? '#f57f17' : '#c62828'),
                borderWidth: 2,
            }]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            scales: {
                x: { title: { display: true, text: 'Talent-Adjusted Persistence (r)' }, min: -0.6, max: 0.8 },
                y: { title: { display: true, text: 'Raw Persistence (r)' }, min: -0.6, max: 0.9 },
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: ctx => {
                            const d = bubbleData[ctx.dataIndex];
                            return `${d.label}: raw=${d.y.toFixed(3)}, adj=${d.x.toFixed(3)}, weight=${d.weight}%`;
                        }
                    }
                }
            }
        }
    });

    // Warning
    const randomWeight = bbComponents.filter(c => {
        const corr = data.correlations.find(x => x.name === c.key);
        return c.weight > 0 && (!corr || !corr.adj_r || Math.abs(corr.adj_r) < 0.3);
    }).reduce((s, c) => s + c.weight, 0);

    if (randomWeight > 30) {
        document.getElementById('overviewWarning').innerHTML = `
            <div class="warning">
                <div class="title">BB Score Formula Warning</div>
                <p>${randomWeight}% of the BB Score formula weight goes to metrics that show NO persistence after talent adjustment.
                Consider adding Gini coefficient (talent-adjusted r=${(data.correlations.find(c=>c.name==='Gini Coefficient')||{adj_r:0}).adj_r||'N/A'}) as a primary input.</p>
            </div>`;
    }
}

function statBox(val, label) {
    return `<div class="stat-box"><div class="val">${val}</div><div class="label">${label}</div></div>`;
}

// ===== CORRELATIONS =====
function renderCorrelations(data) {
    const corrs = data.correlations.sort((a,b) => Math.abs(b.raw_r) - Math.abs(a.raw_r));
    let html = '<thead><tr><th>Metric</th><th>Raw r</th><th>Talent-Adj r</th><th>N</th><th>Verdict</th></tr></thead><tbody>';
    corrs.forEach(c => {
        const adj = c.adj_r != null ? c.adj_r : c.raw_r;
        const cls = Math.abs(adj) >= 0.3 ? 'persistent' : Math.abs(adj) >= 0.15 ? 'weak' : 'random';
        const label = Math.abs(adj) >= 0.3 ? 'Persistent' : Math.abs(adj) >= 0.15 ? 'Weak Signal' : 'Random';
        html += `<tr><td><strong>${c.name}</strong></td><td>${fmt(c.raw_r,3)}</td><td>${c.adj_r!=null?fmt(c.adj_r,3):'-'}</td><td>${c.n}</td><td><span class="badge badge-${cls}">${label}</span></td></tr>`;
    });
    html += '</tbody>';
    document.getElementById('corrTable').innerHTML = html;

    // Weight pie
    const bbComps = [
        { name: 'USEFUL PPW (25%)', weight: 25, key: 'USEFUL Pts/Week' },
        { name: 'USEFUL % (20%)', weight: 20, key: 'USEFUL Week %' },
        { name: 'Boom % (20%)', weight: 20, key: 'Boom Week %' },
        { name: 'TEAR3 (15%)', weight: 15, key: 'TEAR3 Rate' },
        { name: 'IV (10%)', weight: 10, key: 'Implied Volatility' },
        { name: 'Top 3 Avg (5%)', weight: 5, key: 'Top 3 Weeks Avg' },
        { name: 'Top 5 Conc (5%)', weight: 5, key: 'Top 5 Concentration' },
    ];
    const pieColors = bbComps.map(c => {
        const corr = data.correlations.find(x => x.name === c.key);
        const adj = corr ? (corr.adj_r != null ? corr.adj_r : corr.raw_r) : 0;
        return Math.abs(adj) >= 0.3 ? '#2e7d32' : Math.abs(adj) >= 0.15 ? '#f9a825' : '#ef5350';
    });
    const pieCtx = document.getElementById('weightPie').getContext('2d');
    if (window._pieChart) window._pieChart.destroy();
    window._pieChart = new Chart(pieCtx, {
        type: 'doughnut',
        data: { labels: bbComps.map(c=>c.name), datasets: [{ data: bbComps.map(c=>c.weight), backgroundColor: pieColors, borderWidth: 2, borderColor: '#fff' }] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'right', labels: { font: { size: 11 } } } } }
    });

    let breakdown = '<h3>Component Persistence</h3><table><thead><tr><th>Component</th><th>Weight</th><th>Adj r</th><th>Signal?</th></tr></thead><tbody>';
    bbComps.forEach(c => {
        const corr = data.correlations.find(x => x.name === c.key);
        const adj = corr ? (corr.adj_r != null ? corr.adj_r : corr.raw_r) : null;
        const cls = adj != null ? (Math.abs(adj) >= 0.3 ? 'persistent' : Math.abs(adj) >= 0.15 ? 'weak' : 'random') : 'random';
        const label = adj != null ? (Math.abs(adj) >= 0.3 ? 'Signal' : Math.abs(adj) >= 0.15 ? 'Weak' : 'Noise') : '?';
        breakdown += `<tr><td>${c.name}</td><td>${c.weight}%</td><td>${adj!=null?adj.toFixed(3):'-'}</td><td><span class="badge badge-${cls}">${label}</span></td></tr>`;
    });
    breakdown += '</tbody></table>';
    document.getElementById('formulaBreakdown').innerHTML = breakdown;
}

// ===== PLAYERS =====
function renderPlayers(data) {
    const d = data;
    function render(sortKey='bb_score_p1', searchTerm='', minG=20) {
        let players = d.players.filter(p => p.games_p1 >= minG && p.games_p2 >= minG);
        if (searchTerm) players = players.filter(p => p.player_name.toLowerCase().includes(searchTerm.toLowerCase()));
        players.sort((a,b) => (b[sortKey]||0) - (a[sortKey]||0));

        let html = `<thead><tr>
            <th>#</th><th>Player</th><th>GP1</th><th>GP2</th>
            <th>BB1</th><th>BB2</th><th>Chg</th>
            <th>T3r1</th><th>T3r2</th>
            <th>Boom1</th><th>Boom2</th>
            <th>IV1</th><th>IV2</th><th>Tier1</th><th>Tier2</th>
            <th>BW1</th><th>BW2</th>
            <th>Gini1</th><th>Gini2</th>
            <th>MeanW1</th><th>MeanW2</th>
        </tr></thead><tbody>`;
        players.forEach((p, i) => {
            html += `<tr>
                <td>${i+1}</td><td><strong>${p.player_name}</strong></td>
                <td>${p.games_p1}</td><td>${p.games_p2}</td>
                <td>${fmt(p.bb_score_p1)}</td><td>${fmt(p.bb_score_p2)}</td>
                <td class="${chgClass(p.bb_change)}">${fmtChg(p.bb_change)}</td>
                <td>${fmt(p.tear3_p1)}</td><td>${fmt(p.tear3_p2)}</td>
                <td>${fmt(p.boom_rate_p1)}</td><td>${fmt(p.boom_rate_p2)}</td>
                <td>${fmt(p.iv_p1,2)}</td><td>${fmt(p.iv_p2,2)}</td>
                <td>${tierBadge(p.iv_tier_p1)}</td><td>${tierBadge(p.iv_tier_p2)}</td>
                <td>${fmt(p.best_week_p1)}</td><td>${fmt(p.best_week_p2)}</td>
                <td>${fmt(p.gini_p1,3)}</td><td>${fmt(p.gini_p2,3)}</td>
                <td>${fmt(p.mean_week_p1)}</td><td>${fmt(p.mean_week_p2)}</td>
            </tr>`;
        });
        html += '</tbody>';
        document.getElementById('playerTable').innerHTML = html;
    }
    render();
    document.getElementById('playerSearch').addEventListener('input', e => render(document.getElementById('sortCol').value, e.target.value, +document.getElementById('minGames').value));
    document.getElementById('sortCol').addEventListener('change', e => render(e.target.value, document.getElementById('playerSearch').value, +document.getElementById('minGames').value));
    document.getElementById('minGames').addEventListener('change', e => render(document.getElementById('sortCol').value, document.getElementById('playerSearch').value, +e.target.value));
}

// ===== MOVERS =====
function renderMovers(data) {
    const sorted = [...data.players].sort((a,b) => b.bb_change - a.bb_change);
    const risers = sorted.slice(0, 20);
    const fallers = sorted.slice(-20).reverse();

    document.getElementById('risersTitle').textContent = `Top 20 Risers (${data.label1} → ${data.label2})`;
    document.getElementById('fallersTitle').textContent = `Top 20 Fallers (${data.label1} → ${data.label2})`;

    [['risersTable', risers], ['fallersTable', fallers]].forEach(([id, list]) => {
        let html = '<thead><tr><th>#</th><th>Player</th><th>BB1</th><th>BB2</th><th>Change</th><th>IV1</th><th>IV2</th><th>Gini1</th><th>Gini2</th></tr></thead><tbody>';
        list.forEach((p, i) => {
            html += `<tr><td>${i+1}</td><td><strong>${p.player_name}</strong></td>
                <td>${fmt(p.bb_score_p1)}</td><td>${fmt(p.bb_score_p2)}</td>
                <td class="${chgClass(p.bb_change)}">${fmtChg(p.bb_change)}</td>
                <td>${fmt(p.iv_p1,2)}</td><td>${fmt(p.iv_p2,2)}</td>
                <td>${fmt(p.gini_p1,3)}</td><td>${fmt(p.gini_p2,3)}</td></tr>`;
        });
        html += '</tbody>';
        document.getElementById(id).innerHTML = html;
    });
}

// ===== TIERS =====
function renderTiers(data) {
    const tiers = data.tier_order;
    const m = data.tier_matrix;
    let html = '<thead><tr><th>From \\ To</th>';
    tiers.forEach(t => html += `<th>${tierBadge(t)}</th>`);
    html += '<th>Total</th><th>Stay%</th></tr></thead><tbody>';
    tiers.forEach(from => {
        const total = tiers.reduce((s, to) => s + (m[from]?.[to]||0), 0);
        if (total === 0) return;
        const stayed = m[from]?.[from] || 0;
        const pct = (stayed/total*100).toFixed(1);
        html += `<tr><td>${tierBadge(from)}</td>`;
        tiers.forEach(to => {
            const val = m[from]?.[to] || 0;
            const isSame = from === to;
            html += `<td style="background:${isSame && val > 0 ? 'rgba(46,125,50,0.15)':'transparent'};font-weight:${isSame?700:400}">${val || '-'}</td>`;
        });
        html += `<td><strong>${total}</strong></td><td><strong>${pct}%</strong></td></tr>`;
    });
    html += '</tbody>';
    document.getElementById('tierTable').innerHTML = html;

    // Stacked bar
    const tierCtx = document.getElementById('tierChart').getContext('2d');
    const colors = { Nuclear: '#c62828', Gamma: '#e65100', 'High-IV': '#f9a825', Normal: '#bdbdbd', 'Low-Vol': '#64b5f6' };
    const datasets = tiers.map(to => ({
        label: to, data: tiers.map(from => m[from]?.[to]||0), backgroundColor: colors[to], borderWidth: 1, borderColor: '#fff',
    }));
    if (window._tierChart) window._tierChart.destroy();
    window._tierChart = new Chart(tierCtx, {
        type: 'bar',
        data: { labels: tiers.map(t => t + ' (P1)'), datasets },
        options: { responsive: true, maintainAspectRatio: false, scales: { x: { stacked: true }, y: { stacked: true, title: { display: true, text: 'Players' } } }, plugins: { legend: { position: 'bottom' } } }
    });
}

// ===== STARS =====
function renderStars(data) {
    const d = data;
    document.getElementById('starStats').innerHTML = [
        statBox(d.consistent_stars.length, `Stars in Both (Top ${d.top_n})`),
        statBox(d.p1_only_stars.length, `${d.label1}-Only Stars`),
        statBox(d.p2_only_stars.length, `${d.label2}-Only Stars`),
        statBox(((d.consistent_stars.length/d.top_n)*100).toFixed(0)+'%', 'Retention Rate'),
    ].join('');

    document.getElementById('consistentTitle').textContent = `Consistent Stars (Top ${d.top_n} in Both)`;
    document.getElementById('consistentDesc').textContent = `These players were elite in both ${d.label1} and ${d.label2}.`;
    document.getElementById('p1OnlyTitle').textContent = `${d.label1}-Only Stars`;
    document.getElementById('p1OnlyDesc').textContent = `Top ${d.top_n} in ${d.label1} but fell off in ${d.label2}.`;

    function starTable(ids, tableId) {
        const players = ids.map(id => d.players.find(p => p.player_id === id)).filter(Boolean).sort((a,b) => b.bb_score_p1 - a.bb_score_p1);
        let html = '<thead><tr><th>Player</th><th>BB1</th><th>BB2</th><th>Chg</th><th>T3r1</th><th>T3r2</th><th>IV1</th><th>IV2</th><th>Gini1</th><th>Gini2</th></tr></thead><tbody>';
        players.forEach(p => {
            html += `<tr><td><strong>${p.player_name}</strong></td>
                <td>${fmt(p.bb_score_p1)}</td><td>${fmt(p.bb_score_p2)}</td>
                <td class="${chgClass(p.bb_change)}">${fmtChg(p.bb_change)}</td>
                <td>${fmt(p.tear3_p1)}</td><td>${fmt(p.tear3_p2)}</td>
                <td>${fmt(p.iv_p1,2)}</td><td>${fmt(p.iv_p2,2)}</td>
                <td>${fmt(p.gini_p1,3)}</td><td>${fmt(p.gini_p2,3)}</td></tr>`;
        });
        html += '</tbody>';
        document.getElementById(tableId).innerHTML = html;
    }
    starTable(d.consistent_stars, 'consistentTable');
    starTable(d.p1_only_stars, 'p1OnlyTable');
}

// ===== INIT =====
renderAll(BATTING_DATA);
</script>
</body>
</html>"""


def generate_site(batting_data, pitching_data, output_dir='docs'):
    """Write the static HTML file."""
    os.makedirs(output_dir, exist_ok=True)

    html = HTML_TEMPLATE.replace(
        '__BATTING_JSON__', json.dumps(batting_data, default=str)
    ).replace(
        '__PITCHING_JSON__', json.dumps(pitching_data, default=str)
    )

    path = os.path.join(output_dir, 'index.html')
    with open(path, 'w') as f:
        f.write(html)

    print(f"  Static site written to: {path}")
    print(f"  To preview locally: open {os.path.abspath(path)} in a browser")
    print(f"  To host on GitHub Pages: Settings > Pages > Source: 'Deploy from branch', Branch: main, Folder: /docs")
    return path


def main():
    parser = argparse.ArgumentParser(description="Generate GitHub Pages site from comparison analysis")
    parser.add_argument("--db", type=str, help="Single database to split into halves")
    parser.add_argument("--db1", type=str, help="First period database")
    parser.add_argument("--db2", type=str, help="Second period database")
    parser.add_argument("--label1", type=str, default="First Half")
    parser.add_argument("--label2", type=str, default="Second Half")
    parser.add_argument("--split-season", action="store_true")
    parser.add_argument("--min-games", type=int, default=15)
    parser.add_argument("--output", type=str, default="docs")
    args = parser.parse_args()

    print("\n  Generating GitHub Pages site...")

    if args.split_season or args.db:
        src = args.db or args.db1
        h1 = src.replace('.db', '_h1.db')
        h2 = src.replace('.db', '_h2.db')
        if not (os.path.exists(h1) and os.path.exists(h2)):
            print(f"  Splitting {src} into halves...")
            split_database_by_half(src, h1, h2)
        db1_path, db2_path = h1, h2
    else:
        db1_path, db2_path = args.db1, args.db2

    all_data = {}
    for stats_type in ['batting', 'pitching']:
        min_g = args.min_games if stats_type == 'batting' else max(8, args.min_games // 2)
        print(f"\n  Computing {stats_type} weekly metrics for {args.label1}...")
        m1 = compute_weekly_metrics(db1_path, stats_type, min_g)
        print(f"  -> {len(m1)} players")

        print(f"  Computing {stats_type} weekly metrics for {args.label2}...")
        m2 = compute_weekly_metrics(db2_path, stats_type, min_g)
        print(f"  -> {len(m2)} players")

        print(f"  Computing {stats_type} game-level shape metrics...")
        s1 = compute_game_shape_metrics(db1_path, stats_type, min_g)
        s2 = compute_game_shape_metrics(db2_path, stats_type, min_g)

        data = build_comparison_data(m1, m2, s1, s2, args.label1, args.label2, stats_type)
        all_data[stats_type] = data

    generate_site(all_data.get('batting', {}), all_data.get('pitching', {}), args.output)


if __name__ == "__main__":
    main()
