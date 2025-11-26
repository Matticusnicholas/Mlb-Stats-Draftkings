"""
Fast batch cache generator for draft simulator.
Processes all 600+ players in one vectorized pass using pandas/numpy.
"""
import sys
import os
import json
from datetime import datetime
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.database.db_manager import DatabaseManager
from src.database.models import PlayerGame, Player, Game
from sqlalchemy import func

CACHE_DIR = os.path.join(os.path.dirname(__file__), 'cache')
BATTING_CACHE = os.path.join(CACHE_DIR, 'batting_players.json')
PITCHING_CACHE = os.path.join(CACHE_DIR, 'pitching_players.json')


def generate_cache_batch(min_games: int = 20):
    """
    Generate draft cache using batch vectorized operations.
    Processes ALL players at once instead of one-by-one.
    """
    print("=" * 60)
    print("FAST BATCH CACHE GENERATOR")
    print("=" * 60)

    start_time = datetime.now()

    db = DatabaseManager('data/mlb_stats.db')
    session = db.get_session()

    # Create cache directory
    os.makedirs(CACHE_DIR, exist_ok=True)

    # ========================================
    # STEP 1: Load ALL data into DataFrames (one query each)
    # ========================================
    print("\n[1/4] Loading all game data into memory...")

    # Get all player games with player names in ONE query
    query = session.query(
        PlayerGame.player_id,
        Player.player_name,
        PlayerGame.stats_type,
        PlayerGame.position,
        PlayerGame.dk_points,
        Game.game_date
    ).join(
        Player, PlayerGame.player_id == Player.player_id
    ).join(
        Game, PlayerGame.game_pk == Game.game_pk
    )

    # Load into DataFrame
    df = pd.read_sql(query.statement, session.bind)
    print(f"    Loaded {len(df):,} player-game records")

    session.close()

    # ========================================
    # STEP 2: Batch calculate metrics for ALL batters
    # ========================================
    print("\n[2/4] Calculating batter metrics (vectorized)...")

    batters_df = df[df['stats_type'] == 'batting'].copy()
    batter_metrics = calculate_batch_metrics(batters_df, min_games, 'batting')
    print(f"    Processed {len(batter_metrics)} batters")

    # ========================================
    # STEP 3: Batch calculate metrics for ALL pitchers
    # ========================================
    print("\n[3/4] Calculating pitcher metrics (vectorized)...")

    pitchers_df = df[df['stats_type'] == 'pitching'].copy()
    pitcher_metrics = calculate_batch_metrics(pitchers_df, min_games, 'pitching')
    print(f"    Processed {len(pitcher_metrics)} pitchers")

    # ========================================
    # STEP 4: Save to cache files
    # ========================================
    print("\n[4/4] Saving cache files...")

    batting_cache = {
        'generated_at': datetime.now().isoformat(),
        'count': len(batter_metrics),
        'min_games': min_games,
        'players': batter_metrics
    }

    with open(BATTING_CACHE, 'w') as f:
        json.dump(batting_cache, f)
    print(f"    Saved {BATTING_CACHE}")

    pitching_cache = {
        'generated_at': datetime.now().isoformat(),
        'count': len(pitcher_metrics),
        'min_games': min_games,
        'players': pitcher_metrics
    }

    with open(PITCHING_CACHE, 'w') as f:
        json.dump(pitching_cache, f)
    print(f"    Saved {PITCHING_CACHE}")

    # Summary
    elapsed = (datetime.now() - start_time).total_seconds()
    print("\n" + "=" * 60)
    print(f"DONE in {elapsed:.1f} seconds")
    print(f"  Batters: {len(batter_metrics)}")
    print(f"  Pitchers: {len(pitcher_metrics)}")
    print("=" * 60)


def calculate_batch_metrics(df: pd.DataFrame, min_games: int, stats_type: str) -> list:
    """
    Calculate metrics for ALL players at once using pandas groupby.

    This is 10-100x faster than looping through players individually.
    """
    if df.empty:
        return []

    # Group by player and calculate all metrics in one pass
    grouped = df.groupby(['player_id', 'player_name'])

    # Aggregate metrics
    agg = grouped['dk_points'].agg([
        ('games_played', 'count'),
        ('total_points', 'sum'),
        ('mean_points', 'mean'),
        ('std_dev', 'std'),
        ('min_pts', 'min'),
        ('max_pts', 'max'),
        ('median_pts', 'median')
    ]).reset_index()

    # Filter by min games
    agg = agg[agg['games_played'] >= min_games]

    # Calculate percentiles (need to do per-player)
    percentiles = grouped['dk_points'].apply(
        lambda x: pd.Series({
            'p25': np.percentile(x, 25),
            'p75': np.percentile(x, 75),
            'p90': np.percentile(x, 90),
            'p95': np.percentile(x, 95)
        })
    ).unstack().reset_index()
    percentiles.columns = ['player_id', 'player_name', 'p25', 'p75', 'p90', 'p95']

    # Merge percentiles
    agg = agg.merge(percentiles, on=['player_id', 'player_name'])

    # Calculate boom rate (games with 20+ points for batters, 25+ for pitchers)
    boom_threshold = 20 if stats_type == 'batting' else 25
    boom_rates = grouped['dk_points'].apply(
        lambda x: (x >= boom_threshold).sum() / len(x) * 100
    ).reset_index()
    boom_rates.columns = ['player_id', 'player_name', 'boom_rate']
    agg = agg.merge(boom_rates, on=['player_id', 'player_name'])

    # Get primary position (most common)
    positions = df.groupby(['player_id', 'player_name'])['position'].agg(
        lambda x: x.mode().iloc[0] if len(x.mode()) > 0 else 'UTIL'
    ).reset_index()
    positions.columns = ['player_id', 'player_name', 'position']
    agg = agg.merge(positions, on=['player_id', 'player_name'])

    # Calculate IV (implied volatility)
    league_std = agg['std_dev'].median()
    agg['iv'] = (agg['std_dev'] / league_std).round(2)

    # Calculate Best Ball Score
    # Formula: weighted combination of IV, boom rate, and upside
    agg['bestball_score'] = (
        agg['iv'] * 20 +                    # IV contribution
        agg['boom_rate'] * 0.5 +            # Boom rate contribution
        agg['p95'] * 0.3                    # Upside contribution
    ).clip(0, 100).round(1)

    # Calculate useful points (estimate: 70% of total from good weeks)
    agg['useful_points_total'] = (agg['total_points'] * 0.7).round(1)

    # Fill NaN std_dev (players with 1 game)
    agg['std_dev'] = agg['std_dev'].fillna(0)

    # Sort by bestball_score
    agg = agg.sort_values('bestball_score', ascending=False)

    # Convert to list of dicts
    players = []
    for _, row in agg.iterrows():
        players.append({
            'player_id': int(row['player_id']),
            'player_name': row['player_name'],
            'games_played': int(row['games_played']),
            'mean_points': round(float(row['mean_points']), 2),
            'total_points': round(float(row['total_points']), 1),
            'std_dev': round(float(row['std_dev']), 2),
            'iv': float(row['iv']),
            'bestball_score': float(row['bestball_score']),
            'boom_week_rate': round(float(row['boom_rate']), 1),
            'useful_points_total': float(row['useful_points_total']),
            'percentile_95': round(float(row['p95']), 1),
            'position': row['position'] if stats_type == 'batting' else 'P'
        })

    return players


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Generate draft cache (fast batch mode)')
    parser.add_argument('--min-games', type=int, default=20, help='Minimum games played')
    args = parser.parse_args()

    generate_cache_batch(min_games=args.min_games)
