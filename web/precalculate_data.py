"""
Pre-calculate Best Ball metrics for all players and store in JSON cache.
This allows the web app to serve data instantly without calculating on-the-fly.
"""
import sys
import os
import json
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.database.db_manager import DatabaseManager
from src.analytics.weekly_analyzer import WeeklyAnalyzer
import logging
import pandas as pd

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

CACHE_DIR = os.path.join(os.path.dirname(__file__), 'cache')

def get_cache_filename(stats_type, scoring_system='draftkings'):
    """Generate cache filename based on stats type and scoring system."""
    return os.path.join(CACHE_DIR, f'{stats_type}_players_{scoring_system}.json')


def add_chart_data_to_players(players, analyzer, stats_type):
    """
    Add profile chart data to each player for instant profile page loading.
    This includes rolling windows and sequential weeks data for visualizations.
    """
    logger.info(f"Adding chart data for {len(players)} players...")

    for i, player in enumerate(players):
        if (i + 1) % 50 == 0:
            logger.info(f"  Progress: {i+1}/{len(players)} players processed")

        try:
            player_id = player['player_id']

            # Get rolling windows data
            rolling_df = analyzer.get_player_rolling_windows(player_id, stats_type, window_days=7)

            # Get sequential weeks data
            sequential_df = analyzer.get_player_sequential_weeks(player_id, stats_type, days_per_week=7)

            # Add chart data to player dictionary
            player['chart_data'] = {
                'rolling_windows': {
                    'dates': (pd.to_datetime(rolling_df['end_date']).dt.strftime('%Y-%m-%d').tolist()
                              if not rolling_df.empty else []),
                    'points': rolling_df['window_points'].tolist() if not rolling_df.empty else []
                },
                'sequential_weeks': {
                    'week_numbers': list(range(1, len(sequential_df) + 1)) if not sequential_df.empty else [],
                    'points': sequential_df['week_points'].tolist() if not sequential_df.empty else [],
                    'useful_threshold': player.get('useful_threshold', 0)
                }
            }
        except Exception as e:
            logger.warning(f"  Error adding chart data for player {player.get('player_name', 'Unknown')}: {e}")
            # Add empty chart data on error
            player['chart_data'] = {
                'rolling_windows': {'dates': [], 'points': []},
                'sequential_weeks': {'week_numbers': [], 'points': [], 'useful_threshold': 0}
            }

    logger.info(f"✓ Chart data added for all players")
    return players


def precalculate_for_scoring_system(scoring_system='draftkings'):
    """Pre-calculate Best Ball metrics for all players for a specific scoring system."""
    logger.info(f"\n{'='*60}")
    logger.info(f"PROCESSING SCORING SYSTEM: {scoring_system.upper()}")
    logger.info(f"{'='*60}")

    DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'mlb_stats.db')

    db = DatabaseManager(DB_PATH)
    weekly_analyzer = WeeklyAnalyzer(db, scoring_system=scoring_system)

    # Get database stats
    stats = db.get_database_stats()
    logger.info(f"Database stats: {stats['total_players']} players, {stats['total_games']} games")

    # Process batting players
    logger.info("\n" + "="*60)
    logger.info("Processing BATTING players...")
    logger.info("="*60)

    batting_players = weekly_analyzer.get_top_bestball_players(
        stats_type='batting',
        min_games=10,
        limit=500,
        progress_callback=lambda curr, total, name: logger.info(f"  [{curr}/{total}] {name}")
    )

    logger.info(f"\nCompleted batting analysis: {len(batting_players)} players")

    # Add chart data for instant profile loading
    logger.info("\nAdding chart data to batting players...")
    batting_players = add_chart_data_to_players(batting_players, weekly_analyzer, 'batting')

    # Save batting to JSON
    batting_cache = get_cache_filename('batting', scoring_system)
    logger.info(f"Saving batting data to {batting_cache}...")
    cache_data = {
        'generated_at': datetime.now().isoformat(),
        'scoring_system': scoring_system,
        'count': len(batting_players),
        'players': batting_players
    }
    with open(batting_cache, 'w') as f:
        json.dump(cache_data, f, indent=2)
    logger.info("✓ Batting cache saved")

    # Process pitching players
    logger.info("\n" + "="*60)
    logger.info("Processing PITCHING players...")
    logger.info("="*60)

    pitching_players = weekly_analyzer.get_top_bestball_players(
        stats_type='pitching',
        min_games=10,
        limit=500,
        progress_callback=lambda curr, total, name: logger.info(f"  [{curr}/{total}] {name}")
    )

    logger.info(f"\nCompleted pitching analysis: {len(pitching_players)} players")

    # Add chart data for instant profile loading
    logger.info("\nAdding chart data to pitching players...")
    pitching_players = add_chart_data_to_players(pitching_players, weekly_analyzer, 'pitching')

    # Save pitching to JSON
    pitching_cache = get_cache_filename('pitching', scoring_system)
    logger.info(f"Saving pitching data to {pitching_cache}...")
    cache_data = {
        'generated_at': datetime.now().isoformat(),
        'scoring_system': scoring_system,
        'count': len(pitching_players),
        'players': pitching_players
    }
    with open(pitching_cache, 'w') as f:
        json.dump(cache_data, f, indent=2)
    logger.info("✓ Pitching cache saved")

    # Process combined rankings
    logger.info("\n" + "="*60)
    logger.info("Processing COMBINED rankings (batting + pitching)...")
    logger.info("="*60)

    combined_players = weekly_analyzer.get_top_bestball_players_combined(
        min_games=10,
        limit=500,
        progress_callback=lambda curr, total, name, player_type: logger.info(f"  [{curr}/{total}] {name} ({player_type})")
    )

    logger.info(f"\nCompleted combined analysis: {len(combined_players)} total players")

    # Add chart data for combined players (need to handle both batting and pitching)
    logger.info("\nAdding chart data to combined players...")
    for i, player in enumerate(combined_players):
        if (i + 1) % 50 == 0:
            logger.info(f"  Progress: {i+1}/{len(combined_players)} players processed")

        try:
            player_id = player['player_id']
            stats_type = player.get('player_type', 'batting')  # batting or pitching

            # Get rolling windows data
            rolling_df = weekly_analyzer.get_player_rolling_windows(player_id, stats_type, window_days=7)

            # Get sequential weeks data
            sequential_df = weekly_analyzer.get_player_sequential_weeks(player_id, stats_type, days_per_week=7)

            # Add chart data to player dictionary
            player['chart_data'] = {
                'rolling_windows': {
                    'dates': (pd.to_datetime(rolling_df['end_date']).dt.strftime('%Y-%m-%d').tolist()
                              if not rolling_df.empty else []),
                    'points': rolling_df['window_points'].tolist() if not rolling_df.empty else []
                },
                'sequential_weeks': {
                    'week_numbers': list(range(1, len(sequential_df) + 1)) if not sequential_df.empty else [],
                    'points': sequential_df['week_points'].tolist() if not sequential_df.empty else [],
                    'useful_threshold': player.get('useful_threshold', 0)
                }
            }
        except Exception as e:
            logger.warning(f"  Error adding chart data for player {player.get('player_name', 'Unknown')}: {e}")
            player['chart_data'] = {
                'rolling_windows': {'dates': [], 'points': []},
                'sequential_weeks': {'week_numbers': [], 'points': [], 'useful_threshold': 0}
            }

    logger.info(f"✓ Chart data added for combined players")

    # Count batting vs pitching in combined rankings
    batting_count = sum(1 for p in combined_players if p.get('player_type') == 'batting')
    pitching_count = sum(1 for p in combined_players if p.get('player_type') == 'pitching')
    logger.info(f"  - {batting_count} batting players")
    logger.info(f"  - {pitching_count} pitching players")

    # Save combined to JSON
    combined_cache = get_cache_filename('combined', scoring_system)
    logger.info(f"Saving combined data to {combined_cache}...")
    cache_data = {
        'generated_at': datetime.now().isoformat(),
        'scoring_system': scoring_system,
        'count': len(combined_players),
        'batting_count': batting_count,
        'pitching_count': pitching_count,
        'players': combined_players
    }
    with open(combined_cache, 'w') as f:
        json.dump(cache_data, f, indent=2)
    logger.info("✓ Combined cache saved")

    # Summary for this scoring system
    logger.info(f"\n✓ {scoring_system.upper()} COMPLETE")
    logger.info(f"Batting players analyzed: {len(batting_players)}")
    logger.info(f"Pitching players analyzed: {len(pitching_players)}")
    logger.info(f"Combined players analyzed: {len(combined_players)}")
    logger.info(f"Cache files created:")
    logger.info(f"  - {batting_cache}")
    logger.info(f"  - {pitching_cache}")
    logger.info(f"  - {combined_cache}")

    return {
        'batting_count': len(batting_players),
        'pitching_count': len(pitching_players),
        'combined_count': len(combined_players)
    }


def precalculate_all_players():
    """Pre-calculate Best Ball metrics for all players across ALL scoring systems."""
    # Create cache directory if it doesn't exist
    os.makedirs(CACHE_DIR, exist_ok=True)

    logger.info("\n" + "="*60)
    logger.info("PRE-CALCULATING DATA FOR ALL SCORING SYSTEMS")
    logger.info("="*60)
    logger.info("This will generate caches for:")
    logger.info("  • DraftKings")
    logger.info("  • Underdog Fantasy")
    logger.info("  • Drafters")
    logger.info("="*60)

    scoring_systems = ['draftkings', 'underdog', 'drafters']
    results = {}

    for scoring_system in scoring_systems:
        results[scoring_system] = precalculate_for_scoring_system(scoring_system)

    # Final summary
    logger.info("\n" + "="*60)
    logger.info("ALL SCORING SYSTEMS COMPLETE")
    logger.info("="*60)

    for scoring_system in scoring_systems:
        r = results[scoring_system]
        logger.info(f"\n{scoring_system.upper()}:")
        logger.info(f"  Batting: {r['batting_count']} players")
        logger.info(f"  Pitching: {r['pitching_count']} players")
        logger.info(f"  Combined: {r['combined_count']} players")

    total_caches = len(scoring_systems) * 3  # 3 cache files per scoring system
    logger.info(f"\n✓ Generated {total_caches} cache files total")
    logger.info("\nThe web app will now load INSTANTLY for ALL scoring systems!")


if __name__ == '__main__':
    precalculate_all_players()
