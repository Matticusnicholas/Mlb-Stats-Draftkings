#!/usr/bin/env python3
"""
Example usage of the MLB DraftKings Volatility Analyzer.

This script demonstrates how to use the various components
of the system programmatically.
"""

from src.api.mlb_api import MLBStatsAPI
from src.database.db_manager import DatabaseManager
from src.utils.dk_calculator import DKPointsCalculator
from src.analytics.volatility_analyzer import VolatilityAnalyzer
from src.analytics.roster_optimizer import RosterOptimizer
from src.utils.visualizations import PerformanceVisualizer


def example_fetch_data():
    """Example: Fetching data from MLB Stats API."""
    print("="*60)
    print("EXAMPLE 1: Fetching MLB Data")
    print("="*60)

    api = MLBStatsAPI()

    # Fetch a week of games
    from datetime import date
    start_date = date(2025, 4, 1)
    end_date = date(2025, 4, 7)

    games = api.fetch_schedule(start_date, end_date, season="2025")
    print(f"\nFetched {len(games)} games for April 1-7, 2025")

    if games:
        # Show first game
        game = games[0]
        print(f"\nExample game:")
        print(f"  Game PK: {game['gamePk']}")
        print(f"  Date: {game['gameDate']}")
        print(f"  Matchup: {game['awayTeamName']} @ {game['homeTeamName']}")

        # Fetch boxscore for this game
        print(f"\nFetching boxscore for game {game['gamePk']}...")
        boxscore = api.fetch_boxscore(game['gamePk'])

        # Extract player stats
        player_stats = api.extract_player_stats(boxscore)
        print(f"Found stats for {len(player_stats)} player performances")


def example_calculate_dk_points():
    """Example: Calculating DraftKings points."""
    print("\n" + "="*60)
    print("EXAMPLE 2: Calculating DraftKings Points")
    print("="*60)

    calculator = DKPointsCalculator()

    # Example batting performance
    batting_stats = {
        "hits": 3,
        "doubles": 1,
        "triples": 0,
        "homeRuns": 1,
        "rbi": 3,
        "runs": 2,
        "baseOnBalls": 1,
        "stolenBases": 1,
        "caughtStealing": 0,
        "hitByPitch": 0,
        "intentionalWalks": 0
    }

    points = calculator.calculate_batting_points(batting_stats)
    print(f"\nBatting Performance:")
    print(f"  3 hits (1 single, 1 double, 1 HR)")
    print(f"  3 RBI, 2 runs, 1 walk, 1 stolen base")
    print(f"  DraftKings Points: {points}")

    # Example pitching performance
    pitching_stats = {
        "inningsPitched": "7.0",
        "strikeOuts": 9,
        "wins": 1,
        "earnedRuns": 2,
        "hits": 5,
        "baseOnBalls": 2,
        "hitBatsmen": 0
    }

    points = calculator.calculate_pitching_points(pitching_stats)
    print(f"\nPitching Performance:")
    print(f"  7 IP, 9 K, 1 W, 2 ER, 5 H, 2 BB")
    print(f"  DraftKings Points: {points}")


def example_volatility_analysis():
    """Example: Analyzing player volatility."""
    print("\n" + "="*60)
    print("EXAMPLE 3: Volatility Analysis")
    print("="*60)

    db = DatabaseManager(db_path="data/mlb_stats.db")
    analyzer = VolatilityAnalyzer(db)

    # Check database stats
    stats = db.get_database_stats()
    print(f"\nDatabase contains:")
    print(f"  {stats['total_games']} games")
    print(f"  {stats['total_players']} players")
    print(f"  {stats['batting_performances']} batting performances")
    print(f"  {stats['pitching_performances']} pitching performances")

    if stats['players_with_volatility'] > 0:
        print(f"  {stats['players_with_volatility']} players with volatility data")

        # Get top variance players
        top_players = db.get_high_variance_players(
            stats_type="batting",
            min_games=20,
            limit=10
        )

        print(f"\nTop 10 High-Variance Batting Players:")
        print("-"*60)
        for i, (player, volatility) in enumerate(top_players, 1):
            print(f"{i}. {player.player_name:<30} "
                  f"Var: {volatility.variance_score:.1f}  "
                  f"Mean: {volatility.mean_points:.1f}  "
                  f"Boom: {volatility.boom_rate:.1f}%")
    else:
        print("\nNo volatility data yet. Run analyze_volatility.py first!")


def example_roster_building():
    """Example: Building optimal roster."""
    print("\n" + "="*60)
    print("EXAMPLE 4: Roster Building")
    print("="*60)

    db = DatabaseManager(db_path="data/mlb_stats.db")
    optimizer = RosterOptimizer(db)

    # Get player pool
    player_pool = optimizer.get_player_pool(
        stats_type="batting",
        min_games=20,
        min_variance_score=30.0
    )

    print(f"\nPlayer pool: {len(player_pool)} eligible players")

    if len(player_pool) >= 10:
        # Build max variance roster
        roster = optimizer.build_max_variance_roster(
            player_pool,
            optimization_metric='variance_score'
        )

        print(f"\nBuilt roster with {roster['roster_size']} players")
        print(f"Total Variance Score: {roster['total_variance_score']:.2f}")
        print(f"Projected Points: {roster['mean_projected_points']:.2f}")

        # Evaluate upside
        upside = optimizer.evaluate_roster_upside(roster)
        print(f"Ceiling Projection: {upside['ceiling_projection']:.2f}")
        print(f"Boom Probability: {upside['boom_probability']:.1f}%")
    else:
        print("\nInsufficient players for roster building.")
        print("Lower min_games or min_variance_score thresholds, or fetch more data.")


def example_visualization():
    """Example: Creating visualizations."""
    print("\n" + "="*60)
    print("EXAMPLE 5: Visualizations")
    print("="*60)

    db = DatabaseManager(db_path="data/mlb_stats.db")
    viz = PerformanceVisualizer(db)

    print("\nVisualization functions available:")
    print("  - plot_player_timeline(player_id, stats_type)")
    print("  - plot_distribution(player_id, stats_type)")
    print("  - plot_volatility_comparison(player_ids, stats_type)")
    print("  - plot_weekly_volatility(player_id, stats_type)")

    print("\nExample:")
    print("  viz = PerformanceVisualizer(db)")
    print("  viz.plot_player_timeline(player_id=12345, stats_type='batting')")


def main():
    """Run all examples."""
    print("\n" + "="*70)
    print(" "*15 + "MLB DraftKings Volatility Analyzer")
    print(" "*20 + "Usage Examples")
    print("="*70)

    try:
        # Example 1: Fetch data (commented out to avoid API calls)
        # example_fetch_data()

        print("\n[Example 1: Fetching data - commented out to avoid API calls]")
        print("Uncomment in example_usage.py to run")

        # Example 2: Calculate DK points
        example_calculate_dk_points()

        # Example 3: Volatility analysis
        example_volatility_analysis()

        # Example 4: Roster building
        example_roster_building()

        # Example 5: Visualizations
        example_visualization()

        print("\n" + "="*70)
        print("Examples complete!")
        print("\nTo get started with real data:")
        print("  1. python fetch_data.py --season 2025 --limit 100")
        print("  2. python analyze_volatility.py --stats-type batting")
        print("  3. python run_gui.py")
        print("="*70 + "\n")

    except Exception as e:
        print(f"\nError running examples: {e}")
        print("\nMake sure you have:")
        print("  1. Installed requirements: pip install -r requirements.txt")
        print("  2. Created data directory: mkdir -p data")


if __name__ == "__main__":
    main()
