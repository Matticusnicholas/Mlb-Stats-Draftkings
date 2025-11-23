#!/usr/bin/env python3
"""
Script to analyze players for DraftKings Best Ball using rolling 7-day windows.

This analyzes weekly performance and multi-game tear streaks, which are
critical for best ball formats where your best scores auto-count each week.
"""
import argparse
import logging

from src.database.db_manager import DatabaseManager
from src.analytics.weekly_analyzer import WeeklyAnalyzer
from src.utils.export_rankings import RankingsExporter

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def analyze_top_bestball_players(
    analyzer: WeeklyAnalyzer,
    stats_type: str = "batting",
    min_games: int = 20,
    top_n: int = 50,
    export_path: str = None,
    export_format: str = "csv"
):
    """
    Analyze and display top players for best ball.

    Args:
        analyzer: Weekly analyzer instance
        stats_type: 'batting', 'pitching', or 'combined'
        min_games: Minimum games required
        top_n: Number of top players to show
        export_path: Optional path to export rankings (CSV or JSON)
        export_format: Export format - 'csv' or 'json' (default: csv)
    """
    logger.info(f"Analyzing top {top_n} best ball {stats_type} players...")

    # Use combined method if requested
    if stats_type == "combined":
        top_players = analyzer.get_top_bestball_players_combined(
            min_games=min_games,
            limit=top_n
        )
    else:
        top_players = analyzer.get_top_bestball_players(
            stats_type=stats_type,
            min_games=min_games,
            limit=top_n
        )

    if not top_players:
        logger.warning("No players found with sufficient data")
        return

    # Export if requested
    if export_path:
        logger.info(f"Exporting rankings to {export_path}...")
        try:
            if export_format.lower() == 'json':
                RankingsExporter.to_json(top_players, export_path)
            else:
                include_workhorse = (stats_type == "pitching")
                RankingsExporter.to_csv(top_players, export_path, include_workhorse=include_workhorse)
            logger.info(f"✓ Successfully exported {len(top_players)} players to {export_path}")
        except Exception as e:
            logger.error(f"Export failed: {e}")
            return

    # Determine column widths based on whether we're showing player type
    show_type = stats_type == "combined"
    player_name_width = 26 if show_type else 30
    type_width = 8 if show_type else 0

    print("\n" + "="*100)
    print(f"TOP {top_n} BEST BALL {stats_type.upper()} PLAYERS (7-Day Rolling Windows)")
    print("="*100)

    # Build header dynamically
    header = f"{'Rank':<5} {'Player Name':<{player_name_width}}"
    if show_type:
        header += f" {'Type':<{type_width}}"
    header += f" {'BB Score':<9} {'IV':<6} {'Tier':<9} {'Best Week':<10} {'Top3 Avg':<10} {'Boom%':<8} {'TEAR3':<7}"
    print(header)
    print("-"*110)

    for idx, player in enumerate(top_players, 1):
        row = f"{idx:<5} {player['player_name']:<{player_name_width}}"
        if show_type:
            player_type = player.get('player_type', 'unknown')
            type_abbr = 'BAT' if player_type == 'batting' else 'PIT'
            row += f" {type_abbr:<{type_width}}"

        # Get IV and tier
        iv = player.get('implied_volatility', 0.0)
        iv_tier = player.get('iv_tier', 'N/A')

        row += (f" {player['bestball_score']:<9.1f} {iv:<6.2f} {iv_tier:<9} "
                f"{player['best_week']:<10.1f} {player['top3_weeks_avg']:<10.1f} "
                f"{player['boom_week_rate']:<8.1f} {player['tear3_rate']:<7.1f}")
        print(row)

    print("="*110)
    print("\nColumn Definitions:")
    if show_type:
        print("  Type        : Player type (BAT=batting, PIT=pitching)")
    print("  BB Score    : Best Ball composite score (0-100, higher = better)")
    print("  IV          : Implied Volatility (player weekly σ / league median σ)")
    print("                1.0 = normal, 1.35+ = High-IV, 1.60+ = Gamma, 2.0+ = Nuclear")
    print("  Tier        : IV classification (Nuclear/Gamma/High-IV/Normal/Low-Vol)")
    print("  Best Week   : Highest 7-day rolling window points")
    print("  Top3 Avg    : Average of top 3 weekly scores")
    print("  Boom%       : Percentage of weeks in 90th percentile+")
    print("  TEAR3       : Rate of 3+ game hot streaks (per 100 games)")
    print()
    print("💡 IMPLIED VOLATILITY (IV): Normalized weekly explosiveness vs league average")
    print("   IV >= 2.0  = Nuclear (extreme weekly variance, tournament bombs)")
    print("   IV >= 1.60 = Gamma Tier (very high volatility)")
    print("   IV >= 1.35 = High-IV Tier (above-average explosiveness)")
    print("   IV ~  1.0  = Normal volatility")
    print("   IV <  1.0  = Low-Vol (boring for Best Ball)")
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

        print("\nIMPLIED VOLATILITY (IV):")
        iv = metrics.get('implied_volatility', 0.0)
        iv_tier = metrics.get('iv_tier', 'N/A')
        print(f"  Implied Volatility:    {iv:.2f} ({iv_tier} Tier)")
        print(f"  Weekly Std Dev:        {metrics['std_week_points']:.2f} points")
        if iv >= 2.0:
            print(f"  🔥 NUCLEAR IV - Extreme weekly variance, perfect for tournaments!")
        elif iv >= 1.60:
            print(f"  💥 GAMMA TIER - Very high volatility, elite Best Ball asset")
        elif iv >= 1.35:
            print(f"  ⚡ HIGH-IV TIER - Above-average explosiveness")
        elif iv >= 1.0:
            print(f"  ✓ Normal volatility")
        else:
            print(f"  ⚠️  Low volatility - not ideal for Best Ball")

        print("\nOVERALL BEST BALL SCORE:")
        print(f"  Best Ball Score:       {metrics['bestball_score']:.1f} / 100")

        print("="*80)
        print()

    finally:
        session.close()


def show_cache_status(db):
    """Show cache status for all scoring systems."""
    from datetime import datetime
    from sqlalchemy import text

    session = db.get_session()
    try:
        scoring_systems = ['draftkings', 'underdog', 'drafters']

        print("\n" + "="*70)
        print("  SCORING CACHE STATUS")
        print("="*70)

        for system in scoring_systems:
            cache_key = f"{system}_points"

            # Check if metadata exists
            result = session.execute(
                text("SELECT last_calculated, total_records FROM cache_metadata WHERE cache_key = :key"),
                {"key": cache_key}
            ).fetchone()

            if result:
                last_calc, total = result
                last_calc_dt = datetime.fromisoformat(last_calc) if isinstance(last_calc, str) else last_calc
                time_ago = datetime.utcnow() - last_calc_dt

                days = time_ago.days
                hours = time_ago.seconds // 3600

                if days > 0:
                    time_str = f"{days}d {hours}h ago"
                elif hours > 0:
                    time_str = f"{hours}h ago"
                else:
                    time_str = "< 1h ago"

                print(f"  {system.upper():12} ✅ Cached ({time_str}) - {total:,} records")
            else:
                print(f"  {system.upper():12} ⚠️  Not cached (will calculate live)")

        print("="*70)
        print("TIP: Run 'python update_scoring_cache.py' to pre-calculate all scoring systems")
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
        choices=["batting", "pitching", "combined"],
        help="Stats type to analyze (combined ranks all players together)"
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
    parser.add_argument(
        "--export",
        type=str,
        help="Export rankings to file (e.g., rankings.csv or rankings.json)"
    )
    parser.add_argument(
        "--export-format",
        type=str,
        default="csv",
        choices=["csv", "json"],
        help="Export format (default: csv)"
    )
    parser.add_argument(
        "--scoring-system",
        type=str,
        default="draftkings",
        choices=["draftkings", "underdog", "drafters"],
        help="Scoring system to use (default: draftkings)"
    )
    parser.add_argument(
        "--cache-status",
        action="store_true",
        help="Show cache status for all scoring systems"
    )

    args = parser.parse_args()

    # Initialize components
    logger.info("Initializing Best Ball analyzer...")
    db = DatabaseManager(db_path=args.db_path)

    # Show cache status if requested or before analysis
    if args.cache_status:
        show_cache_status(db)
        return

    # Always show cache status before analysis
    show_cache_status(db)

    scoring_system = getattr(args, 'scoring_system', 'draftkings')
    analyzer = WeeklyAnalyzer(db, scoring_system=scoring_system)
    logger.info(f"Using {scoring_system} scoring system")

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
            top_n=args.top_n,
            export_path=args.export,
            export_format=args.export_format
        )

    logger.info("\nBest Ball analysis complete!")
    print("\nTIP: Use --player-id <ID> to see detailed breakdown for a specific player")


if __name__ == "__main__":
    main()
