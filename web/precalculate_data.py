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
BATTING_CACHE = os.path.join(CACHE_DIR, 'batting_players.json')
PITCHING_CACHE = os.path.join(CACHE_DIR, 'pitching_players.json')
COMBINED_CACHE = os.path.join(CACHE_DIR, 'combined_players.json')


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

    # Pre-load all player positions and game counts for fast lookup
    logger.info("Loading player positions and game counts...")
    session = db.get_session()
    from src.database.models import PlayerGame
    from sqlalchemy import func
    from collections import defaultdict

    position_counts = defaultdict(lambda: defaultdict(int))
    game_counts = defaultdict(lambda: defaultdict(int))  # {player_id: {stats_type: count}}

    for row in session.query(PlayerGame.player_id, PlayerGame.position, PlayerGame.stats_type).all():
        if row.position:
            position_counts[row.player_id][row.position] += 1
        game_counts[row.player_id][row.stats_type] += 1

    # Define position categories for best ball (no DH/PH in best ball)
    IF_POSITIONS = {'C', '1B', '2B', '3B', 'SS'}
    OF_POSITIONS = {'LF', 'CF', 'RF'}

    def get_primary_position(player_id, stats_type):
        """Get best ball position for a player.

        For best ball, DH and PH don't exist - players must be assigned to
        a real position. If their primary position is DH/PH, we look at their
        other positions and assign IF or OF based on where they played more.
        """
        if stats_type == 'pitching':
            return 'P'
        counts = position_counts.get(player_id, {})
        if not counts:
            return 'OF'  # Default to OF (DraftKings has no UTIL)

        primary = max(counts, key=counts.get)

        # If primary position is a real position (not DH/PH), use it
        if primary in IF_POSITIONS or primary in OF_POSITIONS:
            return primary

        # For DH/PH players, determine IF vs OF based on other positions
        if_games = sum(counts.get(pos, 0) for pos in IF_POSITIONS)
        of_games = sum(counts.get(pos, 0) for pos in OF_POSITIONS)

        if of_games > if_games:
            # Return most common OF position
            of_counts = {pos: counts.get(pos, 0) for pos in OF_POSITIONS if counts.get(pos, 0) > 0}
            if of_counts:
                return max(of_counts, key=of_counts.get)
            return 'OF'  # Generic OF if no specific position
        elif if_games > 0:
            # Return most common IF position
            if_counts = {pos: counts.get(pos, 0) for pos in IF_POSITIONS if counts.get(pos, 0) > 0}
            if if_counts:
                return max(if_counts, key=if_counts.get)
            return '1B'  # Default IF position
        else:
            # Pure DH with no field positions - default to OF (DraftKings has no UTIL)
            return 'OF'

    def get_games_played(player_id, stats_type):
        """Get games played for a player."""
        return game_counts.get(player_id, {}).get(stats_type, 0)

    session.close()
    logger.info(f"Loaded positions for {len(position_counts)} players, game counts for {len(game_counts)} players")

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

    # Add positions and games_played to batting players
    logger.info("Adding positions and games_played to batting players...")
    for player in batting_players:
        player['position'] = get_primary_position(player['player_id'], 'batting')
        player['games_played'] = get_games_played(player['player_id'], 'batting')

    # Add chart data for instant profile loading
    logger.info("\nAdding chart data to batting players...")
    batting_players = add_chart_data_to_players(batting_players, weekly_analyzer, 'batting')

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

    # Add positions and games_played to pitching players
    logger.info("Adding positions and games_played to pitching players...")
    for player in pitching_players:
        player['position'] = 'P'
        player['games_played'] = get_games_played(player['player_id'], 'pitching')

    # Add chart data for instant profile loading
    logger.info("\nAdding chart data to pitching players...")
    pitching_players = add_chart_data_to_players(pitching_players, weekly_analyzer, 'pitching')

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

    # Add positions and games_played to combined players
    logger.info("Adding positions and games_played to combined players...")
    for player in combined_players:
        stats_type = player.get('player_type', 'batting')
        if stats_type == 'pitching':
            player['position'] = 'P'
        else:
            player['position'] = get_primary_position(player['player_id'], 'batting')
        player['games_played'] = get_games_played(player['player_id'], stats_type)

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
