#!/usr/bin/env python3
"""
Compare player streakiness, TEAR metrics, and boom/bust profiles across
two MLB seasons (or time periods within a season).

Answers the question: Do players who are streaky/explosive in one period
maintain those traits in another? Are TEAR rates, boom week %, and
implied volatility persistent or random?

Usage:
    # Compare 2023 vs 2024 (requires separate databases):
    python compare_seasons.py --db1 data/mlb_stats_2023.db --db2 data/mlb_stats_2024.db --label1 2023 --label2 2024

    # Compare first half vs second half of a single season:
    python compare_seasons.py --db1 data/mlb_stats.db --split-season --label1 "First Half" --label2 "Second Half"

    # Batting only (default):
    python compare_seasons.py --db1 data/mlb_stats.db --split-season --stats-type batting

    # Pitching:
    python compare_seasons.py --db1 data/mlb_stats.db --split-season --stats-type pitching
"""
import argparse
import logging
import os
import sys
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, date
from typing import List, Dict, Tuple, Optional
from collections import defaultdict

from sqlalchemy import func, create_engine, and_
from sqlalchemy.orm import sessionmaker

from src.database.models import Game, Player, PlayerGame, Base, create_database, get_session
from src.database.db_manager import DatabaseManager
from src.analytics.weekly_analyzer import WeeklyAnalyzer

logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def split_database_by_half(source_db_path: str, h1_db_path: str, h2_db_path: str):
    """
    Split a single-season database into first-half and second-half databases.

    Uses the MLB All-Star break (approximately July 14) as the dividing line.
    """
    source_session = get_session(source_db_path)

    # Find the midpoint of the season
    min_date = source_session.query(func.min(Game.game_date)).scalar()
    max_date = source_session.query(func.max(Game.game_date)).scalar()

    if not min_date or not max_date:
        print("No game data found in source database.")
        return

    # Use midpoint as split
    total_days = (max_date - min_date).days
    midpoint = min_date + timedelta(days=total_days // 2)
    print(f"  Season range: {min_date.strftime('%Y-%m-%d')} to {max_date.strftime('%Y-%m-%d')}")
    print(f"  Split point:  {midpoint.strftime('%Y-%m-%d')}")

    h1_count = source_session.query(func.count(Game.game_pk)).filter(Game.game_date < midpoint).scalar()
    h2_count = source_session.query(func.count(Game.game_pk)).filter(Game.game_date >= midpoint).scalar()
    print(f"  First half games: {h1_count}")
    print(f"  Second half games: {h2_count}")

    source_session.close()

    # Create the two half-season databases
    for half_path, date_filter_desc, is_first_half in [
        (h1_db_path, "first half", True),
        (h2_db_path, "second half", False),
    ]:
        if os.path.exists(half_path):
            os.remove(half_path)

        # Create target database
        target_engine = create_database(half_path)
        target_session = sessionmaker(bind=target_engine)()

        # Re-open source
        source_session = get_session(source_db_path)

        if is_first_half:
            games = source_session.query(Game).filter(Game.game_date < midpoint).all()
        else:
            games = source_session.query(Game).filter(Game.game_date >= midpoint).all()

        game_pks = set()
        for g in games:
            new_game = Game(
                game_pk=g.game_pk,
                game_date=g.game_date,
                game_type=g.game_type,
                away_team_id=g.away_team_id,
                away_team_name=g.away_team_name,
                home_team_id=g.home_team_id,
                home_team_name=g.home_team_name,
                double_header=g.double_header,
                game_number=g.game_number,
                data_fetched=g.data_fetched,
                fetch_date=g.fetch_date,
            )
            target_session.merge(new_game)
            game_pks.add(g.game_pk)

        target_session.commit()

        # Copy players and player_games
        player_ids_added = set()
        player_games = source_session.query(PlayerGame).filter(
            PlayerGame.game_pk.in_(game_pks)
        ).all()

        for pg in player_games:
            # Ensure player exists
            if pg.player_id not in player_ids_added:
                player = source_session.query(Player).filter_by(player_id=pg.player_id).first()
                if player:
                    new_player = Player(
                        player_id=player.player_id,
                        player_name=player.player_name,
                        last_updated=player.last_updated,
                    )
                    target_session.merge(new_player)
                    player_ids_added.add(pg.player_id)

            new_pg = PlayerGame(
                game_pk=pg.game_pk,
                player_id=pg.player_id,
                team_id=pg.team_id,
                team_name=pg.team_name,
                position=pg.position,
                stats_type=pg.stats_type,
                dk_points=pg.dk_points,
                underdog_points=pg.underdog_points,
                drafters_points=pg.drafters_points,
                at_bats=pg.at_bats,
                hits=pg.hits,
                singles=pg.singles,
                doubles=pg.doubles,
                triples=pg.triples,
                home_runs=pg.home_runs,
                rbi=pg.rbi,
                runs=pg.runs,
                walks=pg.walks,
                intentional_walks=pg.intentional_walks,
                hit_by_pitch=pg.hit_by_pitch,
                stolen_bases=pg.stolen_bases,
                caught_stealing=pg.caught_stealing,
                strikeouts_batting=pg.strikeouts_batting,
                innings_pitched=pg.innings_pitched,
                strikeouts_pitching=pg.strikeouts_pitching,
                wins=pg.wins,
                losses=pg.losses,
                saves=pg.saves,
                earned_runs=pg.earned_runs,
                hits_allowed=pg.hits_allowed,
                walks_allowed=pg.walks_allowed,
                hit_batsmen=pg.hit_batsmen,
                complete_games=pg.complete_games,
                shutouts=pg.shutouts,
            )
            target_session.add(new_pg)

        target_session.commit()

        pg_count = target_session.query(func.count(PlayerGame.id)).scalar()
        print(f"  {date_filter_desc}: {len(game_pks)} games, {len(player_ids_added)} players, {pg_count} performances")

        target_session.close()
        source_session.close()


def compute_player_metrics(db_path: str, stats_type: str, min_games: int = 15) -> Dict[int, Dict]:
    """
    Compute all weekly/tear/boom metrics for qualifying players in a database.

    Returns dict keyed by player_id with full metrics.
    """
    db = DatabaseManager(db_path=db_path)
    analyzer = WeeklyAnalyzer(db, scoring_system='draftkings')

    session = db.get_session()
    try:
        # Get qualifying players
        player_query = session.query(
            PlayerGame.player_id,
            func.count(PlayerGame.id).label('games')
        ).filter(
            PlayerGame.stats_type == stats_type
        ).group_by(
            PlayerGame.player_id
        ).having(
            func.count(PlayerGame.id) >= min_games
        ).all()

        player_ids = [pid for pid, _ in player_query]
        game_counts = {pid: count for pid, count in player_query}

        results = {}
        for pid in player_ids:
            try:
                metrics = analyzer.calculate_weekly_volatility(pid, stats_type, min_games=min_games)
                if metrics and metrics.get('bestball_score', 0) > 0:
                    player = session.query(Player).filter_by(player_id=pid).first()
                    if player:
                        metrics['player_name'] = player.player_name
                        metrics['player_id'] = pid
                        metrics['games_played'] = game_counts.get(pid, 0)
                        results[pid] = metrics
            except Exception as e:
                continue

        return results
    finally:
        session.close()


def compare_metrics(
    metrics1: Dict[int, Dict],
    metrics2: Dict[int, Dict],
    label1: str,
    label2: str,
    stats_type: str,
    output_path: str = None,
):
    """
    Compare player metrics across two time periods and produce a detailed report.
    """
    # Find players in both periods
    common_ids = set(metrics1.keys()) & set(metrics2.keys())
    only_p1 = set(metrics1.keys()) - set(metrics2.keys())
    only_p2 = set(metrics2.keys()) - set(metrics1.keys())

    report_lines = []

    def out(line="", end="\n"):
        report_lines.append(line)
        print(line, end=end)

    out()
    out("=" * 120)
    out(f"  YEAR-OVER-YEAR COMPARISON: {label1} vs {label2}")
    out(f"  Stats Type: {stats_type.upper()} | Scoring: DraftKings")
    out("=" * 120)

    out(f"\n  Players in {label1}: {len(metrics1)}")
    out(f"  Players in {label2}: {len(metrics2)}")
    out(f"  Players in BOTH periods: {len(common_ids)}")
    out(f"  Only in {label1}: {len(only_p1)}")
    out(f"  Only in {label2}: {len(only_p2)}")

    if len(common_ids) < 10:
        out("\n  Not enough common players to run comparison analysis.")
        return

    # Build comparison DataFrame
    rows = []
    for pid in common_ids:
        m1 = metrics1[pid]
        m2 = metrics2[pid]
        rows.append({
            'player_id': pid,
            'player_name': m1.get('player_name', m2.get('player_name', str(pid))),
            'games_p1': m1.get('games_played', 0),
            'games_p2': m2.get('games_played', 0),
            # Best Ball Score
            'bb_score_p1': m1.get('bestball_score', 0),
            'bb_score_p2': m2.get('bestball_score', 0),
            # TEAR metrics
            'tear2_p1': m1.get('tear2_rate', 0),
            'tear2_p2': m2.get('tear2_rate', 0),
            'tear3_p1': m1.get('tear3_rate', 0),
            'tear3_p2': m2.get('tear3_rate', 0),
            'tear4_p1': m1.get('tear4_rate', 0),
            'tear4_p2': m2.get('tear4_rate', 0),
            'tear5_p1': m1.get('tear5_rate', 0),
            'tear5_p2': m2.get('tear5_rate', 0),
            'longest_tear_p1': m1.get('longest_tear', 0),
            'longest_tear_p2': m2.get('longest_tear', 0),
            # Boom metrics
            'boom_rate_p1': m1.get('boom_week_rate', 0),
            'boom_rate_p2': m2.get('boom_week_rate', 0),
            'best_week_p1': m1.get('best_week', 0),
            'best_week_p2': m2.get('best_week', 0),
            'top3_avg_p1': m1.get('top3_weeks_avg', 0),
            'top3_avg_p2': m2.get('top3_weeks_avg', 0),
            # IV
            'iv_p1': m1.get('implied_volatility', 0),
            'iv_p2': m2.get('implied_volatility', 0),
            'iv_tier_p1': m1.get('iv_tier', 'N/A'),
            'iv_tier_p2': m2.get('iv_tier', 'N/A'),
            # Weekly stats
            'mean_week_p1': m1.get('mean_week_points', 0),
            'mean_week_p2': m2.get('mean_week_points', 0),
            'std_week_p1': m1.get('std_week_points', 0),
            'std_week_p2': m2.get('std_week_points', 0),
            # USEFUL metrics
            'useful_pct_p1': m1.get('useful_weeks_pct', 0),
            'useful_pct_p2': m2.get('useful_weeks_pct', 0),
            'useful_ppw_p1': m1.get('useful_points_per_week', 0),
            'useful_ppw_p2': m2.get('useful_points_per_week', 0),
        })

    df = pd.DataFrame(rows)

    # =========================================================================
    # SECTION 1: CORRELATION ANALYSIS
    # =========================================================================
    out("\n" + "=" * 120)
    out("  SECTION 1: METRIC PERSISTENCE (CORRELATION ANALYSIS)")
    out("  How well does each metric in Period 1 predict Period 2?")
    out("=" * 120)

    correlation_metrics = [
        ('Best Ball Score', 'bb_score'),
        ('TEAR2 Rate', 'tear2'),
        ('TEAR3 Rate', 'tear3'),
        ('TEAR4 Rate', 'tear4'),
        ('Boom Week %', 'boom_rate'),
        ('Best Week', 'best_week'),
        ('Top 3 Weeks Avg', 'top3_avg'),
        ('Implied Volatility', 'iv'),
        ('Mean Weekly Pts', 'mean_week'),
        ('Weekly Std Dev', 'std_week'),
        ('USEFUL Week %', 'useful_pct'),
        ('USEFUL Pts/Week', 'useful_ppw'),
        ('Longest Tear', 'longest_tear'),
    ]

    out(f"\n  {'Metric':<25} {'Correlation':>12} {'Interpretation':<30} {'N':>5}")
    out("  " + "-" * 75)

    correlations = {}
    for name, prefix in correlation_metrics:
        col1 = f'{prefix}_p1'
        col2 = f'{prefix}_p2'
        valid = df[[col1, col2]].dropna()
        valid = valid[(valid[col1] != 0) | (valid[col2] != 0)]

        if len(valid) < 10:
            out(f"  {name:<25} {'N/A':>12} {'Insufficient data':<30} {len(valid):>5}")
            continue

        corr = valid[col1].corr(valid[col2])
        correlations[name] = corr

        if abs(corr) >= 0.7:
            interp = "STRONG persistence"
        elif abs(corr) >= 0.5:
            interp = "MODERATE persistence"
        elif abs(corr) >= 0.3:
            interp = "WEAK persistence"
        else:
            interp = "NO persistence (random)"

        marker = " ***" if abs(corr) >= 0.5 else " **" if abs(corr) >= 0.3 else ""
        out(f"  {name:<25} {corr:>12.3f} {interp:<30} {len(valid):>5}{marker}")

    out("\n  *** = Strong signal   ** = Moderate signal")
    out("  Correlation > 0.5 means the trait is REPEATABLE across periods")
    out("  Correlation < 0.3 means the trait is largely RANDOM")

    # =========================================================================
    # SECTION 2: TOP PLAYERS COMPARISON
    # =========================================================================
    out("\n" + "=" * 120)
    out(f"  SECTION 2: TOP PLAYERS COMPARISON ({label1} vs {label2})")
    out("=" * 120)

    # Sort by P1 Best Ball score
    df_sorted = df.sort_values('bb_score_p1', ascending=False)

    out(f"\n  {'Rank':<5} {'Player Name':<26} {'GP1':>4} {'GP2':>4} "
        f"{'BB1':>6} {'BB2':>6} {'Chg':>6} "
        f"{'T3r1':>6} {'T3r2':>6} "
        f"{'Boom1':>6} {'Boom2':>6} "
        f"{'IV1':>6} {'IV2':>6} "
        f"{'BstWk1':>7} {'BstWk2':>7}")
    out("  " + "-" * 118)

    for idx, (_, row) in enumerate(df_sorted.head(50).iterrows(), 1):
        bb_chg = row['bb_score_p2'] - row['bb_score_p1']
        chg_str = f"{bb_chg:>+5.1f}"

        out(f"  {idx:<5} {row['player_name']:<26} {row['games_p1']:>4} {row['games_p2']:>4} "
            f"{row['bb_score_p1']:>6.1f} {row['bb_score_p2']:>6.1f} {chg_str:>6} "
            f"{row['tear3_p1']:>6.1f} {row['tear3_p2']:>6.1f} "
            f"{row['boom_rate_p1']:>6.1f} {row['boom_rate_p2']:>6.1f} "
            f"{row['iv_p1']:>6.2f} {row['iv_p2']:>6.2f} "
            f"{row['best_week_p1']:>7.1f} {row['best_week_p2']:>7.1f}")

    out(f"\n  Column Key:")
    out(f"    GP1/GP2    = Games played in {label1}/{label2}")
    out(f"    BB1/BB2    = Best Ball Score in {label1}/{label2}")
    out(f"    Chg        = Change in BB Score ({label2} - {label1})")
    out(f"    T3r1/T3r2  = TEAR3 rate (3+ game hot streaks per 100 games)")
    out(f"    Boom1/Boom2= Boom Week % (weeks in 90th percentile)")
    out(f"    IV1/IV2    = Implied Volatility (weekly explosiveness vs league)")
    out(f"    BstWk1/2   = Best single 7-day rolling window")

    # =========================================================================
    # SECTION 3: BIGGEST MOVERS (UP AND DOWN)
    # =========================================================================
    out("\n" + "=" * 120)
    out("  SECTION 3: BIGGEST MOVERS (Changes in Best Ball Score)")
    out("=" * 120)

    df['bb_change'] = df['bb_score_p2'] - df['bb_score_p1']

    # Top risers
    out(f"\n  TOP 15 RISERS ({label1} -> {label2}):")
    out(f"  {'Rank':<5} {'Player Name':<26} {'BB1':>6} {'BB2':>6} {'Change':>7} {'T3 Chg':>7} {'Boom Chg':>8} {'IV Chg':>7}")
    out("  " + "-" * 80)
    for idx, (_, row) in enumerate(df.sort_values('bb_change', ascending=False).head(15).iterrows(), 1):
        t3_chg = row['tear3_p2'] - row['tear3_p1']
        boom_chg = row['boom_rate_p2'] - row['boom_rate_p1']
        iv_chg = row['iv_p2'] - row['iv_p1']
        out(f"  {idx:<5} {row['player_name']:<26} {row['bb_score_p1']:>6.1f} {row['bb_score_p2']:>6.1f} "
            f"{row['bb_change']:>+7.1f} {t3_chg:>+7.1f} {boom_chg:>+8.1f} {iv_chg:>+7.2f}")

    # Top fallers
    out(f"\n  TOP 15 FALLERS ({label1} -> {label2}):")
    out(f"  {'Rank':<5} {'Player Name':<26} {'BB1':>6} {'BB2':>6} {'Change':>7} {'T3 Chg':>7} {'Boom Chg':>8} {'IV Chg':>7}")
    out("  " + "-" * 80)
    for idx, (_, row) in enumerate(df.sort_values('bb_change', ascending=True).head(15).iterrows(), 1):
        t3_chg = row['tear3_p2'] - row['tear3_p1']
        boom_chg = row['boom_rate_p2'] - row['boom_rate_p1']
        iv_chg = row['iv_p2'] - row['iv_p1']
        out(f"  {idx:<5} {row['player_name']:<26} {row['bb_score_p1']:>6.1f} {row['bb_score_p2']:>6.1f} "
            f"{row['bb_change']:>+7.1f} {t3_chg:>+7.1f} {boom_chg:>+8.1f} {iv_chg:>+7.2f}")

    # =========================================================================
    # SECTION 4: TIER STABILITY ANALYSIS
    # =========================================================================
    out("\n" + "=" * 120)
    out("  SECTION 4: IV TIER STABILITY (Do explosive players stay explosive?)")
    out("=" * 120)

    tier_order = ['Nuclear', 'Gamma', 'High-IV', 'Normal', 'Low-Vol']
    tier_transitions = defaultdict(lambda: defaultdict(int))

    for _, row in df.iterrows():
        t1 = row.get('iv_tier_p1', 'N/A')
        t2 = row.get('iv_tier_p2', 'N/A')
        if t1 != 'N/A' and t2 != 'N/A':
            tier_transitions[t1][t2] += 1

    out(f"\n  IV Tier Transition Matrix ({label1} -> {label2}):")
    from_to_label = "From \\ To"
    out(f"  {from_to_label:<12}", end="")
    for tier in tier_order:
        out(f" {tier:>9}", end="")
    out(f" {'Total':>8}  {'Stay%':>6}")
    out("  " + "-" * 75)

    for from_tier in tier_order:
        total = sum(tier_transitions[from_tier].values())
        if total == 0:
            continue
        stayed = tier_transitions[from_tier].get(from_tier, 0)
        stay_pct = (stayed / total * 100) if total > 0 else 0

        out(f"  {from_tier:<12}", end="")
        for to_tier in tier_order:
            count = tier_transitions[from_tier].get(to_tier, 0)
            out(f" {count:>9}", end="")
        out(f" {total:>8}  {stay_pct:>5.1f}%")

    out("\n  Interpretation: Higher 'Stay%' means the tier is more persistent.")
    out("  If Nuclear/Gamma players stay Nuclear/Gamma, streakiness is a SKILL.")
    out("  If they scatter across tiers, it's more RANDOM.")

    # =========================================================================
    # SECTION 5: TEAR STREAK CONSISTENCY
    # =========================================================================
    out("\n" + "=" * 120)
    out("  SECTION 5: TEAR STREAK CONSISTENCY ANALYSIS")
    out("=" * 120)

    # Classify players by tear profile in P1
    df['tear_profile_p1'] = pd.cut(
        df['tear3_p1'],
        bins=[-1, 0.01, 5, 15, 1000],
        labels=['No Tears', 'Low (0-5)', 'Moderate (5-15)', 'High (15+)']
    )
    df['tear_profile_p2'] = pd.cut(
        df['tear3_p2'],
        bins=[-1, 0.01, 5, 15, 1000],
        labels=['No Tears', 'Low (0-5)', 'Moderate (5-15)', 'High (15+)']
    )

    out(f"\n  TEAR3 Rate Categories: What happens to {label1} tear players in {label2}?")
    out(f"\n  {label1} Category    -> {label2} Avg TEAR3  | {label2} Avg BB Score | N Players")
    out("  " + "-" * 70)

    for cat in ['High (15+)', 'Moderate (5-15)', 'Low (0-5)', 'No Tears']:
        subset = df[df['tear_profile_p1'] == cat]
        if len(subset) == 0:
            continue
        avg_t3_p2 = subset['tear3_p2'].mean()
        avg_bb_p2 = subset['bb_score_p2'].mean()
        out(f"  {cat:<18} -> {avg_t3_p2:>14.1f}     | {avg_bb_p2:>12.1f}   | {len(subset):>4}")

    out("\n  If 'High' tear players in P1 maintain high TEAR3 in P2, streakiness is persistent.")

    # =========================================================================
    # SECTION 6: BOOM WEEK PERSISTENCE
    # =========================================================================
    out("\n" + "=" * 120)
    out("  SECTION 6: BOOM WEEK PERSISTENCE")
    out("=" * 120)

    df['boom_profile_p1'] = pd.cut(
        df['boom_rate_p1'],
        bins=[-1, 5, 10, 15, 100],
        labels=['Low Boom (0-5%)', 'Medium (5-10%)', 'High (10-15%)', 'Elite (15%+)']
    )

    out(f"\n  {label1} Boom Category -> {label2} Avg Boom% | {label2} Avg Best Week | N Players")
    out("  " + "-" * 75)

    for cat in ['Elite (15%+)', 'High (10-15%)', 'Medium (5-10%)', 'Low Boom (0-5%)']:
        subset = df[df['boom_profile_p1'] == cat]
        if len(subset) == 0:
            continue
        avg_boom_p2 = subset['boom_rate_p2'].mean()
        avg_bw_p2 = subset['best_week_p2'].mean()
        out(f"  {cat:<22} -> {avg_boom_p2:>10.1f}%   | {avg_bw_p2:>14.1f}    | {len(subset):>4}")

    # =========================================================================
    # SECTION 7: CONSISTENT STARS vs FLASH-IN-THE-PAN
    # =========================================================================
    out("\n" + "=" * 120)
    out("  SECTION 7: CONSISTENT STARS vs ONE-PERIOD WONDERS")
    out("=" * 120)

    # Players ranked top 30 in BOTH periods
    top_n = min(30, len(df) // 3)
    df_p1_sorted = df.sort_values('bb_score_p1', ascending=False)
    df_p2_sorted = df.sort_values('bb_score_p2', ascending=False)

    top_p1 = set(df_p1_sorted.head(top_n)['player_id'].values)
    top_p2 = set(df_p2_sorted.head(top_n)['player_id'].values)

    consistent_stars = top_p1 & top_p2
    p1_only_stars = top_p1 - top_p2
    p2_only_stars = top_p2 - top_p1

    out(f"\n  Using top {top_n} BB Score as cutoff:")
    out(f"    Consistent Stars (top {top_n} in BOTH):  {len(consistent_stars)}")
    out(f"    {label1}-only stars (fell off in {label2}):  {len(p1_only_stars)}")
    out(f"    {label2}-only stars (emerged in {label2}):   {len(p2_only_stars)}")
    retention_rate = len(consistent_stars) / top_n * 100 if top_n > 0 else 0
    out(f"    Retention Rate: {retention_rate:.1f}%")

    if consistent_stars:
        out(f"\n  CONSISTENT STARS (Top {top_n} in both periods):")
        out(f"  {'Player Name':<26} {'BB1':>6} {'BB2':>6} {'T3r1':>6} {'T3r2':>6} {'IV1':>6} {'IV2':>6}")
        out("  " + "-" * 65)
        for pid in sorted(consistent_stars, key=lambda x: metrics1[x].get('bestball_score', 0), reverse=True):
            row = df[df['player_id'] == pid].iloc[0]
            out(f"  {row['player_name']:<26} {row['bb_score_p1']:>6.1f} {row['bb_score_p2']:>6.1f} "
                f"{row['tear3_p1']:>6.1f} {row['tear3_p2']:>6.1f} "
                f"{row['iv_p1']:>6.2f} {row['iv_p2']:>6.2f}")

    if p1_only_stars:
        out(f"\n  {label1}-ONLY STARS (Top {top_n} in {label1}, dropped in {label2}):")
        out(f"  {'Player Name':<26} {'BB1':>6} {'BB2':>6} {'T3r1':>6} {'T3r2':>6} {'IV1':>6} {'IV2':>6}")
        out("  " + "-" * 65)
        for pid in sorted(p1_only_stars, key=lambda x: metrics1[x].get('bestball_score', 0), reverse=True):
            row = df[df['player_id'] == pid].iloc[0]
            out(f"  {row['player_name']:<26} {row['bb_score_p1']:>6.1f} {row['bb_score_p2']:>6.1f} "
                f"{row['tear3_p1']:>6.1f} {row['tear3_p2']:>6.1f} "
                f"{row['iv_p1']:>6.2f} {row['iv_p2']:>6.2f}")

    # =========================================================================
    # SECTION 8: SUMMARY & KEY FINDINGS
    # =========================================================================
    out("\n" + "=" * 120)
    out("  SECTION 8: KEY FINDINGS & TAKEAWAYS")
    out("=" * 120)

    out("\n  METRIC PERSISTENCE RANKING (most to least predictive):")
    if correlations:
        sorted_corrs = sorted(correlations.items(), key=lambda x: abs(x[1]), reverse=True)
        for i, (name, corr) in enumerate(sorted_corrs, 1):
            bar_len = int(abs(corr) * 30)
            bar = "#" * bar_len
            out(f"  {i:>3}. {name:<25} r={corr:>+.3f}  [{bar:<30}]")

    # Overall persistence score
    if correlations:
        avg_corr = np.mean([abs(c) for c in correlations.values()])
        out(f"\n  OVERALL PERSISTENCE INDEX: {avg_corr:.3f}")
        if avg_corr >= 0.5:
            out("  Verdict: Player profiles are HIGHLY PERSISTENT across periods.")
            out("  Best Ball strategy: Trust historical TEAR/boom metrics for draft decisions.")
        elif avg_corr >= 0.3:
            out("  Verdict: Player profiles show MODERATE persistence.")
            out("  Best Ball strategy: Use historical metrics as a guide but expect some regression.")
        else:
            out("  Verdict: Player profiles show LOW persistence. Streakiness is partly random.")
            out("  Best Ball strategy: Don't over-rely on single-season TEAR/boom metrics.")

    out("\n" + "=" * 120)

    # Export the comparison data
    if output_path:
        df.to_csv(output_path, index=False)
        out(f"\n  Full comparison data exported to: {output_path}")

    return df, correlations


def main():
    parser = argparse.ArgumentParser(
        description="Compare player streakiness and TEAR/boom metrics across two MLB seasons or time periods."
    )
    parser.add_argument(
        "--db1",
        type=str,
        required=True,
        help="Path to first period database (e.g., data/mlb_stats_2023.db)"
    )
    parser.add_argument(
        "--db2",
        type=str,
        default=None,
        help="Path to second period database (e.g., data/mlb_stats_2024.db)"
    )
    parser.add_argument(
        "--label1",
        type=str,
        default="Period 1",
        help="Label for first period (e.g., '2023')"
    )
    parser.add_argument(
        "--label2",
        type=str,
        default="Period 2",
        help="Label for second period (e.g., '2024')"
    )
    parser.add_argument(
        "--split-season",
        action="store_true",
        help="Split single database into first/second half instead of using two databases"
    )
    parser.add_argument(
        "--stats-type",
        type=str,
        default="batting",
        choices=["batting", "pitching"],
        help="Stats type to analyze"
    )
    parser.add_argument(
        "--min-games",
        type=int,
        default=15,
        help="Minimum games in each period for a player to be included"
    )
    parser.add_argument(
        "--export",
        type=str,
        default=None,
        help="Export comparison data to CSV file"
    )

    args = parser.parse_args()

    print("\n" + "=" * 120)
    print("  MLB BEST BALL: YEAR-OVER-YEAR STREAKINESS ANALYSIS")
    print("=" * 120)

    if args.split_season:
        # Split single database into two halves
        h1_path = args.db1.replace('.db', '_h1.db')
        h2_path = args.db1.replace('.db', '_h2.db')

        print(f"\n  Splitting {args.db1} into two halves...")
        split_database_by_half(args.db1, h1_path, h2_path)

        db1_path = h1_path
        db2_path = h2_path
    else:
        if not args.db2:
            print("Error: --db2 is required when not using --split-season")
            sys.exit(1)
        db1_path = args.db1
        db2_path = args.db2

    print(f"\n  Computing {args.stats_type} metrics for {args.label1}...")
    metrics1 = compute_player_metrics(db1_path, args.stats_type, min_games=args.min_games)
    print(f"  -> {len(metrics1)} qualifying players")

    print(f"\n  Computing {args.stats_type} metrics for {args.label2}...")
    metrics2 = compute_player_metrics(db2_path, args.stats_type, min_games=args.min_games)
    print(f"  -> {len(metrics2)} qualifying players")

    compare_metrics(
        metrics1, metrics2,
        args.label1, args.label2,
        args.stats_type,
        output_path=args.export,
    )

    # Clean up temp databases if we split
    if args.split_season:
        print(f"\n  Temp databases preserved at {db1_path} and {db2_path}")
        print(f"  (Delete manually if not needed)")

    print("\n  To compare actual 2023 vs 2024 seasons:")
    print("    1. python fetch_data.py --season 2023 --db-path data/mlb_stats_2023.db")
    print("    2. python fetch_data.py --season 2024 --db-path data/mlb_stats_2024.db")
    print("    3. python compare_seasons.py --db1 data/mlb_stats_2023.db --db2 data/mlb_stats_2024.db --label1 2023 --label2 2024")
    print()


if __name__ == "__main__":
    main()
