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

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

CACHE_DIR = os.path.join(os.path.dirname(__file__), 'cache')
BATTING_CACHE = os.path.join(CACHE_DIR, 'batting_players.json')
PITCHING_CACHE = os.path.join(CACHE_DIR, 'pitching_players.json')
COMBINED_CACHE = os.path.join(CACHE_DIR, 'combined_players.json')


def precalculate_all_players():
    """Pre-calculate Best Ball metrics for all players and save to JSON."""
    # Create cache directory if it doesn't exist
    os.makedirs(CACHE_DIR, exist_ok=True)

    DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'mlb_stats.db')

    logger.info("Initializing database and analyzer...")
    db = DatabaseManager(DB_PATH)
    weekly_analyzer = WeeklyAnalyzer(db)

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

    # Save batting to JSON
    logger.info(f"Saving batting data to {BATTING_CACHE}...")
    cache_data = {
        'generated_at': datetime.now().isoformat(),
        'count': len(batting_players),
        'players': batting_players
    }
    with open(BATTING_CACHE, 'w') as f:
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

    # Save pitching to JSON
    logger.info(f"Saving pitching data to {PITCHING_CACHE}...")
    cache_data = {
        'generated_at': datetime.now().isoformat(),
        'count': len(pitching_players),
        'players': pitching_players
    }
    with open(PITCHING_CACHE, 'w') as f:
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

    # Count batting vs pitching in combined rankings
    batting_count = sum(1 for p in combined_players if p.get('player_type') == 'batting')
    pitching_count = sum(1 for p in combined_players if p.get('player_type') == 'pitching')
    logger.info(f"  - {batting_count} batting players")
    logger.info(f"  - {pitching_count} pitching players")

    # Save combined to JSON
    logger.info(f"Saving combined data to {COMBINED_CACHE}...")
    cache_data = {
        'generated_at': datetime.now().isoformat(),
        'count': len(combined_players),
        'batting_count': batting_count,
        'pitching_count': pitching_count,
        'players': combined_players
    }
    with open(COMBINED_CACHE, 'w') as f:
        json.dump(cache_data, f, indent=2)
    logger.info("✓ Combined cache saved")

    # Summary
    logger.info("\n" + "="*60)
    logger.info("PRE-CALCULATION COMPLETE")
    logger.info("="*60)
    logger.info(f"Batting players analyzed: {len(batting_players)}")
    logger.info(f"Pitching players analyzed: {len(pitching_players)}")
    logger.info(f"Combined players analyzed: {len(combined_players)}")
    logger.info(f"Total players: {len(batting_players) + len(pitching_players)}")
    logger.info(f"\nCache files created:")
    logger.info(f"  - {BATTING_CACHE}")
    logger.info(f"  - {PITCHING_CACHE}")
    logger.info(f"  - {COMBINED_CACHE}")
    logger.info("\nThe web app will now load INSTANTLY from these cache files!")


if __name__ == '__main__':
    precalculate_all_players()
