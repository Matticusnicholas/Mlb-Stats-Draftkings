#!/usr/bin/env python3
"""
Script to fetch MLB game data and calculate DraftKings points.
"""
import argparse
import logging
from datetime import date, datetime
from tqdm import tqdm

from src.api.mlb_api import MLBStatsAPI
from src.database.db_manager import DatabaseManager
from src.utils.dk_calculator import DKPointsCalculator

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def fetch_season_schedule(api: MLBStatsAPI, db: DatabaseManager, season: str = "2025"):
    """
    Fetch and store schedule for entire season.

    Args:
        api: MLB Stats API client
        db: Database manager
        season: Season year
    """
    logger.info(f"Fetching schedule for {season} season...")

    try:
        games = api.fetch_season_schedule(season=season, game_type="R")
        logger.info(f"Found {len(games)} games for {season} season")

        # Store games in database
        added = db.add_games(games)
        logger.info(f"Added {added} new games to database")

        return len(games)

    except Exception as e:
        logger.error(f"Error fetching season schedule: {e}")
        raise


def fetch_boxscores(
    api: MLBStatsAPI,
    db: DatabaseManager,
    calculator: DKPointsCalculator,
    limit: int = None,
    batch_size: int = 100
):
    """
    Fetch boxscore data for games and calculate DK points.

    Args:
        api: MLB Stats API client
        db: Database manager
        calculator: DK points calculator
        limit: Maximum number of games to fetch
        batch_size: Number of games to process before showing progress
    """
    logger.info("Fetching boxscores for unfetched games...")

    # Get list of games to fetch
    game_pks = db.get_games_to_fetch(limit=limit)
    total_games = len(game_pks)

    if total_games == 0:
        logger.info("No games to fetch!")
        return 0

    logger.info(f"Found {total_games} games to process")

    processed = 0
    errors = 0

    # Use tqdm for progress bar
    with tqdm(total=total_games, desc="Fetching boxscores") as pbar:
        for game_pk in game_pks:
            try:
                # Fetch boxscore
                boxscore = api.fetch_boxscore(game_pk)

                # Extract player stats
                player_stats = api.extract_player_stats(boxscore)

                # Calculate DK points and store
                for player_data in player_stats:
                    dk_points = calculator.calculate_points(player_data)

                    db.add_player_game(
                        game_pk=game_pk,
                        player_data=player_data,
                        dk_points=dk_points
                    )

                # Mark game as fetched
                db.mark_game_fetched(game_pk)

                processed += 1
                pbar.update(1)

            except Exception as e:
                logger.error(f"Error processing game {game_pk}: {e}")
                errors += 1
                pbar.update(1)
                continue

    logger.info(f"Processed {processed} games successfully, {errors} errors")
    return processed


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Fetch MLB data and calculate DK points")
    parser.add_argument(
        "--season",
        type=str,
        default="2025",
        help="Season year to fetch (default: 2025)"
    )
    parser.add_argument(
        "--schedule-only",
        action="store_true",
        help="Only fetch schedule, don't fetch boxscores"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of games to fetch boxscores for"
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default="data/mlb_stats.db",
        help="Path to database file"
    )

    args = parser.parse_args()

    # Initialize components
    logger.info("Initializing components...")
    api = MLBStatsAPI(rate_limit_delay=0.3)
    db = DatabaseManager(db_path=args.db_path)
    calculator = DKPointsCalculator()

    # Fetch schedule
    logger.info("="*60)
    logger.info("STEP 1: Fetch Season Schedule")
    logger.info("="*60)

    total_games = fetch_season_schedule(api, db, season=args.season)

    if args.schedule_only:
        logger.info("Schedule-only mode. Exiting.")
        return

    # Fetch boxscores
    logger.info("\n" + "="*60)
    logger.info("STEP 2: Fetch Boxscores and Calculate DK Points")
    logger.info("="*60)

    processed = fetch_boxscores(
        api=api,
        db=db,
        calculator=calculator,
        limit=args.limit
    )

    # Show database stats
    logger.info("\n" + "="*60)
    logger.info("DATABASE SUMMARY")
    logger.info("="*60)

    stats = db.get_database_stats()
    for key, value in stats.items():
        logger.info(f"  {key}: {value}")

    logger.info("\nData fetch complete!")


if __name__ == "__main__":
    main()
