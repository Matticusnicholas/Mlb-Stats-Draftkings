#!/usr/bin/env python3
"""
Script to analyze players for DraftKings Best Ball using rolling 7-day windows.

This analyzes weekly performance and multi-game tear streaks, which are
critical for best ball formats where your best scores auto-count each week.
"""
import argparse
import logging
from tqdm import tqdm

from src.database.db_manager import DatabaseManager
from src.analytics.weekly_analyzer import WeeklyAnalyzer

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def analyze_top_bestball_players(
    analyzer: WeeklyAnalyzer,
    stats_type: str = "batting",
    min_games: int = 20,
    top_n: int = 50
):
    """
    Analyze and display top players for best ball.

    Args:
        analyzer: Weekly analyzer instance
        stats_type: 'batting' or 'pitching'
        min_games: Minimum games required
        top_n: Number of top players to show
    """
    logger.info(f"Analyzing top {top_n} best ball {stats_type} players...")

    top_players = analyzer.get_top_bestball_players(
        stats_type=stats_type,
        min_games=min_games,
        limit=top_n
    )

    if not top_players:
        logger.warning("No players found with sufficient data")
        return

    print("\n" + "="*100)
    print(f"TOP {top_n} BEST BALL {stats_type.upper()} PLAYERS (7-Day Rolling Windows)")
    print("="*100)
    print(f"{'Rank':<5} {'Player Name':<30} {'BB Score':<9} {'Best Week':<10} "
          f"{'Top3 Avg':<10} {'Boom%':<8} {'TEAR3':<7} {'TEAR4':<7}")
    print("-"*100)

    for idx, player in enumerate(top_players, 1):
        print(f"{idx:<5} {player['player_name']:<30} "
              f"{player['bestball_score']:<9.1f} {player['best_week']:<10.1f} "
              f"{player['top3_weeks_avg']:<10.1f} {player['boom_week_rate']:<8.1f} "
              f"{player['tear3_rate']:<7.1f} {player['tear4_rate']:<7.1f}")

    print("="*100)
    print("\nColumn Definitions:")
    print("  BB Score    : Best Ball composite score (0-100, higher = better)")
    print("  Best Week   : Highest 7-day rolling window DK points")
    print("  Top3 Avg    : Average of top 3 weekly scores")
    print("  Boom%       : Percentage of weeks in 90th percentile+")
    print("  TEAR3       : Rate of 3+ game hot streaks (per 100 games)")
    print("  TEAR4       : Rate of 4+ game hot streaks (per 100 games)")
    print()


def show_player_detail(
    analyzer: WeeklyAnalyzer,
    player_id: int,
    stats_type: str = "batting"
):
    """
    Show detailed weekly analysis for a specific player.

    Args:
        analyzer: Weekly analyzer instance
        player_id: MLB player ID
        stats_type: 'batting' or 'pitching'
    """
    from src.database.models import Player

    db = analyzer.db
    session = db.get_session()

    try:
        player = session.query(Player).filter_by(player_id=player_id).first()

        if not player:
            print(f"Player {player_id} not found")
            return

        metrics = analyzer.calculate_weekly_volatility(player_id, stats_type)

        if not metrics:
            print(f"Insufficient data for player {player.player_name}")
            return

        print("\n" + "="*80)
        print(f"BEST BALL ANALYSIS: {player.player_name}")
        print("="*80)

        print("\nWEEKLY PERFORMANCE:")
        print(f"  Best Week Ever:        {metrics['best_week']:.1f} points")
        print(f"  Top 3 Weeks Average:   {metrics['top3_weeks_avg']:.1f} points")
        print(f"  Top 5 Weeks Average:   {metrics['top5_weeks_avg']:.1f} points")
        print(f"  Mean Weekly Points:    {metrics['mean_week_points']:.1f} points")
        print(f"  Median Weekly Points:  {metrics['median_week_points']:.1f} points")

        print("\nCEILING METRICS:")
        print(f"  95th Percentile Week:  {metrics['week_percentile_95']:.1f} points")
        print(f"  90th Percentile Week:  {metrics['week_percentile_90']:.1f} points")
        print(f"  75th Percentile Week:  {metrics['week_percentile_75']:.1f} points")

        print("\nBOOM WEEKS:")
        print(f"  Boom Week Rate:        {metrics['boom_week_rate']:.1f}% ({metrics['boom_week_count']} weeks)")
        print(f"  High Week Rate:        {metrics['high_week_rate']:.1f}% ({metrics['high_week_count']} weeks)")
        print(f"  Top 5 Concentration:   {metrics['top5_weeks_pct']:.1f}% of total points")

        print("\nMULTI-GAME TEAR METRICS:")
        print(f"  TEAR2 (2+ games):      {metrics['tear2_rate']:.1f} per 100 games ({metrics['tear2_count']} total)")
        print(f"  TEAR3 (3+ games):      {metrics['tear3_rate']:.1f} per 100 games ({metrics['tear3_count']} total)")
        print(f"  TEAR4 (4+ games):      {metrics['tear4_rate']:.1f} per 100 games ({metrics['tear4_count']} total)")
        print(f"  TEAR5 (5+ games):      {metrics['tear5_rate']:.1f} per 100 games ({metrics['tear5_count']} total)")
        print(f"  Longest Tear:          {metrics['longest_tear']} consecutive hot games")
        print(f"  Tear Threshold:        {metrics['tear_threshold']:.1f} points (75th percentile)")

        print("\nOVERALL BEST BALL SCORE:")
        print(f"  Best Ball Score:       {metrics['bestball_score']:.1f} / 100")

        print("="*80)
        print()

    finally:
        session.close()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Analyze players for DraftKings Best Ball (rolling 7-day windows)"
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default="data/mlb_stats.db",
        help="Path to database file"
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
        default=20,
        help="Minimum games required for analysis"
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=50,
        help="Number of top players to show"
    )
    parser.add_argument(
        "--player-id",
        type=int,
        help="Show detailed analysis for specific player ID"
    )

    args = parser.parse_args()

    # Initialize components
    logger.info("Initializing Best Ball analyzer...")
    db = DatabaseManager(db_path=args.db_path)
    analyzer = WeeklyAnalyzer(db)

    if args.player_id:
        # Show detailed analysis for specific player
        show_player_detail(analyzer, args.player_id, args.stats_type)
    else:
        # Show top players
        logger.info("="*60)
        logger.info("BEST BALL ANALYSIS (Rolling 7-Day Windows)")
        logger.info("="*60)

        analyze_top_bestball_players(
            analyzer=analyzer,
            stats_type=args.stats_type,
            min_games=args.min_games,
            top_n=args.top_n
        )

    logger.info("\nBest Ball analysis complete!")
    print("\nTIP: Use --player-id <ID> to see detailed breakdown for a specific player")


if __name__ == "__main__":
    main()
