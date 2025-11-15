"""
Pre-calculate Best Ball metrics for all players and store in database.
This allows the web app to serve data instantly without calculating on-the-fly.
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.database.db_manager import DatabaseManager
from src.analytics.weekly_analyzer import WeeklyAnalyzer
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def precalculate_all_players():
    """Pre-calculate Best Ball metrics for all players."""
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

    # Summary
    logger.info("\n" + "="*60)
    logger.info("PRE-CALCULATION COMPLETE")
    logger.info("="*60)
    logger.info(f"Batting players analyzed: {len(batting_players)}")
    logger.info(f"Pitching players analyzed: {len(pitching_players)}")
    logger.info(f"Total players: {len(batting_players) + len(pitching_players)}")
    logger.info("\nAll Best Ball metrics have been calculated and stored in the database.")
    logger.info("The web app is ready to serve data instantly!")


if __name__ == '__main__':
    precalculate_all_players()
