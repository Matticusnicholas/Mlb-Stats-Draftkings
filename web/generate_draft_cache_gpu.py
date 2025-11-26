"""
GPU-accelerated batch cache generator for draft simulator.
Uses CuPy (NVIDIA CUDA) when available, falls back to NumPy.

Requires: pip install cupy-cuda11x (or cupy-cuda12x for CUDA 12)
"""
import sys
import os
import json
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Try to import GPU libraries
GPU_AVAILABLE = False
try:
    import cupy as cp
    import cudf
    GPU_AVAILABLE = True
    print("✓ NVIDIA GPU detected - using CUDA acceleration")
except ImportError:
    import numpy as cp  # Fallback to numpy with same API
    print("○ No GPU libraries found - using CPU (still fast)")

import numpy as np
import pandas as pd
from src.database.db_manager import DatabaseManager
from src.database.models import PlayerGame, Player, Game

CACHE_DIR = os.path.join(os.path.dirname(__file__), 'cache')
BATTING_CACHE = os.path.join(CACHE_DIR, 'batting_players.json')
PITCHING_CACHE = os.path.join(CACHE_DIR, 'pitching_players.json')


def check_gpu():
    """Check if NVIDIA GPU is available and print info."""
    try:
        import cupy as cp
        device = cp.cuda.Device(0)
        props = cp.cuda.runtime.getDeviceProperties(0)
        print(f"\n GPU: {props['name'].decode()}")
        print(f"  Memory: {props['totalGlobalMem'] / 1e9:.1f} GB")
        print(f"  CUDA Cores: ~{props['multiProcessorCount'] * 128}")
        return True
    except Exception as e:
        print(f"\n No NVIDIA GPU available: {e}")
        return False


def generate_cache_gpu(min_games: int = 20):
    """
    Generate draft cache using GPU when available.
    Falls back to optimized CPU if no GPU.
    """
    print("=" * 60)
    print("DRAFT CACHE GENERATOR (GPU-ACCELERATED)")
    print("=" * 60)

    has_gpu = check_gpu()
    start_time = datetime.now()

    db = DatabaseManager('data/mlb_stats.db')
    session = db.get_session()
    os.makedirs(CACHE_DIR, exist_ok=True)

    # ========================================
    # Load all data
    # ========================================
    print("\n[1/4] Loading game data...")

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

    df = pd.read_sql(query.statement, session.bind)
    print(f"    Loaded {len(df):,} records")
    session.close()

    # ========================================
    # Process on GPU or CPU
    # ========================================
    if has_gpu and GPU_AVAILABLE:
        print("\n[2/4] Processing batters on GPU...")
        batters_df = df[df['stats_type'] == 'batting'].copy()
        batter_metrics = calculate_metrics_gpu(batters_df, min_games, 'batting')

        print("\n[3/4] Processing pitchers on GPU...")
        pitchers_df = df[df['stats_type'] == 'pitching'].copy()
        pitcher_metrics = calculate_metrics_gpu(pitchers_df, min_games, 'pitching')
    else:
        print("\n[2/4] Processing batters on CPU...")
        batters_df = df[df['stats_type'] == 'batting'].copy()
        batter_metrics = calculate_metrics_cpu(batters_df, min_games, 'batting')

        print("\n[3/4] Processing pitchers on CPU...")
        pitchers_df = df[df['stats_type'] == 'pitching'].copy()
        pitcher_metrics = calculate_metrics_cpu(pitchers_df, min_games, 'pitching')

    print(f"    Batters: {len(batter_metrics)}, Pitchers: {len(pitcher_metrics)}")

    # ========================================
    # Save cache
    # ========================================
    print("\n[4/4] Saving cache files...")

    with open(BATTING_CACHE, 'w') as f:
        json.dump({
            'generated_at': datetime.now().isoformat(),
            'count': len(batter_metrics),
            'gpu_accelerated': has_gpu,
            'players': batter_metrics
        }, f)

    with open(PITCHING_CACHE, 'w') as f:
        json.dump({
            'generated_at': datetime.now().isoformat(),
            'count': len(pitcher_metrics),
            'gpu_accelerated': has_gpu,
            'players': pitcher_metrics
        }, f)

    elapsed = (datetime.now() - start_time).total_seconds()
    print("\n" + "=" * 60)
    print(f"DONE in {elapsed:.2f} seconds {'(GPU)' if has_gpu else '(CPU)'}")
    print(f"  Batters: {len(batter_metrics)}")
    print(f"  Pitchers: {len(pitcher_metrics)}")
    print("=" * 60)


def calculate_metrics_gpu(df: pd.DataFrame, min_games: int, stats_type: str) -> list:
    """
    Calculate metrics using GPU (cuDF/CuPy).
    Sends entire dataset to GPU memory, processes in parallel.
    """
    import cudf
    import cupy as cp

    if df.empty:
        return []

    # Transfer to GPU memory
    gdf = cudf.DataFrame.from_pandas(df)

    # Group by player
    grouped = gdf.groupby(['player_id', 'player_name'])

    # Aggregate on GPU
    agg = grouped['dk_points'].agg(['count', 'sum', 'mean', 'std', 'min', 'max']).reset_index()
    agg.columns = ['player_id', 'player_name', 'games', 'total', 'mean', 'std', 'min', 'max']

    # Filter by min games
    agg = agg[agg['games'] >= min_games]

    # Calculate percentiles on GPU (custom kernel would be faster, but this works)
    def calc_percentiles(group):
        pts = group['dk_points'].values
        pts_cpu = cp.asnumpy(pts)  # Need to go to CPU for percentile
        return pd.Series({
            'p95': np.percentile(pts_cpu, 95),
            'boom_rate': (pts_cpu >= (20 if stats_type == 'batting' else 25)).sum() / len(pts_cpu) * 100
        })

    # This part still needs CPU for percentiles (could optimize with custom CUDA kernel)
    pdf = df.groupby(['player_id', 'player_name']).apply(calc_percentiles).reset_index()
    agg_cpu = agg.to_pandas()
    agg_cpu = agg_cpu.merge(pdf, on=['player_id', 'player_name'])

    # Get positions
    positions = df.groupby(['player_id', 'player_name'])['position'].agg(
        lambda x: x.mode().iloc[0] if len(x.mode()) > 0 else 'UTIL'
    ).reset_index()
    agg_cpu = agg_cpu.merge(positions, on=['player_id', 'player_name'])

    # Calculate derived metrics
    league_std = agg_cpu['std'].median()
    agg_cpu['iv'] = (agg_cpu['std'] / league_std).round(2)
    agg_cpu['bestball_score'] = (
        agg_cpu['iv'] * 20 + agg_cpu['boom_rate'] * 0.5 + agg_cpu['p95'] * 0.3
    ).clip(0, 100).round(1)
    agg_cpu['useful_points_total'] = (agg_cpu['total'] * 0.7).round(1)
    agg_cpu['std'] = agg_cpu['std'].fillna(0)
    agg_cpu = agg_cpu.sort_values('bestball_score', ascending=False)

    # Convert to list
    return [
        {
            'player_id': int(row['player_id']),
            'player_name': row['player_name'],
            'games_played': int(row['games']),
            'mean_points': round(float(row['mean']), 2),
            'total_points': round(float(row['total']), 1),
            'std_dev': round(float(row['std']), 2),
            'iv': float(row['iv']),
            'bestball_score': float(row['bestball_score']),
            'boom_week_rate': round(float(row['boom_rate']), 1),
            'useful_points_total': float(row['useful_points_total']),
            'percentile_95': round(float(row['p95']), 1),
            'position': row['position'] if stats_type == 'batting' else 'P'
        }
        for _, row in agg_cpu.iterrows()
    ]


def calculate_metrics_cpu(df: pd.DataFrame, min_games: int, stats_type: str) -> list:
    """Optimized CPU fallback using pandas vectorization."""
    if df.empty:
        return []

    grouped = df.groupby(['player_id', 'player_name'])

    agg = grouped['dk_points'].agg([
        ('games_played', 'count'),
        ('total_points', 'sum'),
        ('mean_points', 'mean'),
        ('std_dev', 'std'),
    ]).reset_index()

    agg = agg[agg['games_played'] >= min_games]

    # Percentiles and boom rate
    extras = grouped['dk_points'].apply(
        lambda x: pd.Series({
            'p95': np.percentile(x, 95),
            'boom_rate': (x >= (20 if stats_type == 'batting' else 25)).sum() / len(x) * 100
        })
    ).unstack().reset_index()
    agg = agg.merge(extras, on=['player_id', 'player_name'])

    # Positions
    positions = df.groupby(['player_id', 'player_name'])['position'].agg(
        lambda x: x.mode().iloc[0] if len(x.mode()) > 0 else 'UTIL'
    ).reset_index()
    agg = agg.merge(positions, on=['player_id', 'player_name'])

    # Derived metrics
    league_std = agg['std_dev'].median()
    agg['iv'] = (agg['std_dev'] / league_std).round(2)
    agg['bestball_score'] = (agg['iv'] * 20 + agg['boom_rate'] * 0.5 + agg['p95'] * 0.3).clip(0, 100).round(1)
    agg['useful_points_total'] = (agg['total_points'] * 0.7).round(1)
    agg['std_dev'] = agg['std_dev'].fillna(0)
    agg = agg.sort_values('bestball_score', ascending=False)

    return [
        {
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
        }
        for _, row in agg.iterrows()
    ]


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Generate draft cache (GPU-accelerated)')
    parser.add_argument('--min-games', type=int, default=20, help='Minimum games played')
    parser.add_argument('--check-gpu', action='store_true', help='Only check GPU availability')
    args = parser.parse_args()

    if args.check_gpu:
        check_gpu()
    else:
        generate_cache_gpu(min_games=args.min_games)
