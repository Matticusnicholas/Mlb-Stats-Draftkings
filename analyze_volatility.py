#!/usr/bin/env python3
"""
Script to analyze player volatility and generate reports.
"""
import argparse
import logging
from tqdm import tqdm

from src.database.db_manager import DatabaseManager
from src.analytics.volatility_analyzer import VolatilityAnalyzer
from src.analytics.roster_optimizer import RosterOptimizer
from src.utils.visualizations import PerformanceVisualizer

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def analyze_all_players(
    analyzer: VolatilityAnalyzer,
    stats_type: str = "batting",
    min_games: int = 20
):
    """
    Analyze volatility for all eligible players.

    Args:
        analyzer: Volatility analyzer instance
        stats_type: 'batting' or 'pitching'
        min_games: Minimum games required
    """
    logger.info(f"Analyzing {stats_type} volatility (min {min_games} games)...")

    analyzed_players = analyzer.analyze_all_players(
        stats_type=stats_type,
        min_games=min_games
    )

    logger.info(f"Analyzed {len(analyzed_players)} players")
    return analyzed_players


def generate_top_players_report(
    db: DatabaseManager,
    stats_type: str = "batting",
    min_games: int = 20,
    top_n: int = 50
):
    """
    Generate report of top variance players.

    Args:
        db: Database manager
        stats_type: 'batting' or 'pitching'
        min_games: Minimum games threshold
        top_n: Number of top players to show
    """
    logger.info(f"Generating top {top_n} {stats_type} volatility report...")

    results = db.get_high_variance_players(
        stats_type=stats_type,
        min_games=min_games,
        limit=top_n
    )

    if not results:
        logger.warning("No players found with volatility data")
        return

    print("\n" + "="*80)
    print(f"TOP {top_n} HIGH-VARIANCE {stats_type.upper()} PLAYERS")
    print("="*80)
    print(f"{'Rank':<5} {'Player Name':<30} {'Games':<7} {'Mean':<8} {'Std':<8} {'Var':<8} {'Upside':<8}")
    print("-"*80)

    for idx, (player, volatility) in enumerate(results, 1):
        print(f"{idx:<5} {player.player_name:<30} {volatility.games_played:<7} "
              f"{volatility.mean_points:<8.2f} {volatility.std_dev:<8.2f} "
              f"{volatility.variance_score:<8.2f} {volatility.upside_score:<8.2f}")

    print("="*80)


def build_sample_roster(
    optimizer: RosterOptimizer,
    stats_type: str = "batting",
    min_games: int = 20,
    min_variance: float = 30.0
):
    """
    Build a sample max-variance roster.

    Args:
        optimizer: Roster optimizer instance
        stats_type: 'batting' or 'pitching'
        min_games: Minimum games
        min_variance: Minimum variance score
    """
    logger.info("Building sample max-variance roster...")

    # Get player pool
    player_pool = optimizer.get_player_pool(
        stats_type=stats_type,
        min_games=min_games,
        min_variance_score=min_variance
    )

    if len(player_pool) < 10:
        logger.warning(f"Insufficient players ({len(player_pool)}) for roster building")
        return

    # Build roster
    roster = optimizer.build_max_variance_roster(
        player_pool,
        optimization_metric='variance_score'
    )

    # Display roster
    print("\n" + "="*80)
    print("SAMPLE MAX-VARIANCE ROSTER")
    print("="*80)

    print("\nPITCHERS:")
    print("-"*80)
    for i, p in enumerate(roster.get('pitchers', []), 1):
        print(f"{i}. {p['player_name']:<30} Var: {p['variance_score']:<6.1f}  "
              f"Mean: {p['mean_points']:<6.1f}  Max: {p['max_points']:<6.1f}")

    print("\nBATTERS:")
    print("-"*80)
    for i, p in enumerate(roster.get('batters', []), 1):
        print(f"{i}. {p['player_name']:<30} Var: {p['variance_score']:<6.1f}  "
              f"Mean: {p['mean_points']:<6.1f}  Max: {p['max_points']:<6.1f}")

    print("\n" + "="*80)
    print("ROSTER SUMMARY")
    print("="*80)
    print(f"Total Variance Score:    {roster.get('total_variance_score', 0):.2f}")
    print(f"Total Upside Score:      {roster.get('total_upside_score', 0):.2f}")
    print(f"Projected Mean Points:   {roster.get('mean_projected_points', 0):.2f}")
    print(f"Projected Std Dev:       {roster.get('std_dev', 0):.2f}")

    # Upside analysis
    upside_eval = optimizer.evaluate_roster_upside(roster)
    print(f"\nCeiling Projection:      {upside_eval['ceiling_projection']:.2f}")
    print(f"Expected 90th %ile:      {upside_eval['expected_90th_percentile']:.2f}")
    print(f"Boom Probability:        {upside_eval['boom_probability']:.1f}%")
    print("="*80)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Analyze player volatility")
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
        help="Number of top players to show in report"
    )
    parser.add_argument(
        "--skip-analysis",
        action="store_true",
        help="Skip re-analyzing players, just generate report"
    )
    parser.add_argument(
        "--build-roster",
        action="store_true",
        help="Build sample max-variance roster"
    )
    parser.add_argument(
        "--min-variance",
        type=float,
        default=30.0,
        help="Minimum variance score for roster building"
    )

    args = parser.parse_args()

    # Initialize components
    logger.info("Initializing components...")
    db = DatabaseManager(db_path=args.db_path)
    analyzer = VolatilityAnalyzer(db)
    optimizer = RosterOptimizer(db)

    # Analyze players
    if not args.skip_analysis:
        logger.info("="*60)
        logger.info("STEP 1: Analyze Player Volatility")
        logger.info("="*60)

        analyze_all_players(
            analyzer=analyzer,
            stats_type=args.stats_type,
            min_games=args.min_games
        )

    # Generate report
    logger.info("\n" + "="*60)
    logger.info("STEP 2: Generate Top Players Report")
    logger.info("="*60)

    generate_top_players_report(
        db=db,
        stats_type=args.stats_type,
        min_games=args.min_games,
        top_n=args.top_n
    )

    # Build roster if requested
    if args.build_roster:
        logger.info("\n" + "="*60)
        logger.info("STEP 3: Build Sample Roster")
        logger.info("="*60)

        build_sample_roster(
            optimizer=optimizer,
            stats_type=args.stats_type,
            min_games=args.min_games,
            min_variance=args.min_variance
        )

    logger.info("\nAnalysis complete!")


if __name__ == "__main__":
    main()
