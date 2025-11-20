"""
Flask web application for MLB Best Ball Analyzer.
Baseball Savant-style interface for Best Ball draft analysis.
"""
from flask import Flask, render_template, jsonify, request, send_file
from flask_cors import CORS
import sys
import os
import json
from datetime import datetime
import tempfile

# Add parent directory to path to import from src
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.database.db_manager import DatabaseManager
from src.analytics.weekly_analyzer import WeeklyAnalyzer
from src.utils.export_rankings import RankingsExporter

app = Flask(__name__)
CORS(app)

# Initialize database
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'mlb_stats.db')
db = DatabaseManager(DB_PATH)

# Cache file paths
CACHE_DIR = os.path.join(os.path.dirname(__file__), 'cache')
BATTING_CACHE = os.path.join(CACHE_DIR, 'batting_players.json')
PITCHING_CACHE = os.path.join(CACHE_DIR, 'pitching_players.json')
COMBINED_CACHE = os.path.join(CACHE_DIR, 'combined_players.json')

# In-memory cache
_player_cache = {
    'batting': None,
    'pitching': None,
    'combined': None
}


def load_cached_players(stats_type='batting'):
    """Load pre-calculated players from JSON cache."""
    # Select appropriate cache file
    if stats_type == 'batting':
        cache_file = BATTING_CACHE
    elif stats_type == 'pitching':
        cache_file = PITCHING_CACHE
    elif stats_type == 'combined':
        cache_file = COMBINED_CACHE
    else:
        print(f"WARNING: Unknown stats_type: {stats_type}")
        return None

    # Check if cache exists
    if not os.path.exists(cache_file):
        print(f"WARNING: Cache file not found: {cache_file}")
        print("Run 'python web/precalculate_data.py' to generate cache files.")
        return None

    # Check if already loaded in memory
    if _player_cache[stats_type] is not None:
        return _player_cache[stats_type]

    # Load from file
    try:
        with open(cache_file, 'r') as f:
            cache_data = json.load(f)

        players = cache_data.get('players', [])
        _player_cache[stats_type] = players

        print(f"✓ Loaded {len(players)} {stats_type} players from cache (generated: {cache_data.get('generated_at', 'unknown')})")
        return players
    except Exception as e:
        print(f"ERROR loading cache: {e}")
        return None


@app.route('/')
def index():
    """Render main page."""
    return render_template('index.html')


@app.route('/api/players', methods=['GET'])
def get_players():
    """
    Get player data with Best Ball metrics.

    Query params:
        stats_type: 'batting', 'pitching', or 'combined' (default: batting)
        scoring_system: 'draftkings', 'underdog', or 'drafters' (default: draftkings)
        min_games: Minimum games played (default: 20)
        limit: Max players to return (default: 100)
        sort_by: Field to sort by (default: bestball_score)
        use_cache: Use cached data if available (default: true, only for DraftKings)
    """
    try:
        stats_type = request.args.get('stats_type', 'batting')
        scoring_system = request.args.get('scoring_system', 'draftkings')
        min_games = int(request.args.get('min_games', 20))
        limit = int(request.args.get('limit', 100))
        sort_by = request.args.get('sort_by', 'bestball_score')
        use_cache = request.args.get('use_cache', 'true').lower() == 'true'

        # Cache only available for DraftKings scoring
        players = None
        if use_cache and scoring_system == 'draftkings':
            players = load_cached_players(stats_type)

        # Fall back to live calculation if cache not available or different scoring system
        if players is None:
            if scoring_system != 'draftkings':
                print(f"Using {scoring_system} scoring (live calculation)...")
            else:
                print(f"Cache not available, calculating live...")

            # Create analyzer with selected scoring system
            weekly_analyzer = WeeklyAnalyzer(db, scoring_system=scoring_system)

            # Use combined method for combined rankings
            if stats_type == 'combined':
                players = weekly_analyzer.get_top_bestball_players_combined(
                    min_games=min_games,
                    limit=limit
                )
            else:
                players = weekly_analyzer.get_top_bestball_players(
                    stats_type=stats_type,
                    min_games=min_games,
                    limit=limit
                )

        # Sort by requested field
        players.sort(key=lambda x: x.get(sort_by, 0), reverse=True)

        # Apply limit
        players = players[:limit]

        # Calculate percentiles for each stat
        players_with_percentiles = calculate_percentiles(players)

        return jsonify({
            'success': True,
            'players': players_with_percentiles,
            'count': len(players_with_percentiles),
            'scoring_system': scoring_system,
            'from_cache': use_cache and scoring_system == 'draftkings' and _player_cache.get(stats_type) is not None
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/player/<int:player_id>', methods=['GET'])
def get_player_detail(player_id):
    """Get detailed stats for a specific player."""
    try:
        stats_type = request.args.get('stats_type', 'batting')
        scoring_system = request.args.get('scoring_system', 'draftkings')

        # Create analyzer with selected scoring system
        weekly_analyzer = WeeklyAnalyzer(db, scoring_system=scoring_system)

        # Get player metrics
        metrics = weekly_analyzer.calculate_weekly_volatility(player_id, stats_type)

        if not metrics:
            return jsonify({
                'success': False,
                'error': 'Player not found'
            }), 404

        return jsonify({
            'success': True,
            'player': metrics
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/stats', methods=['GET'])
def get_database_stats():
    """Get database statistics."""
    try:
        stats = db.get_database_stats()
        return jsonify({
            'success': True,
            'stats': stats
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


def calculate_percentiles(players):
    """
    Calculate percentiles for each stat across all players.

    Args:
        players: List of player dictionaries

    Returns:
        List of players with percentile data added
    """
    import numpy as np

    if not players:
        return []

    # Stats to calculate percentiles for
    stats = ['bestball_score', 'useful_points_total', 'useful_weeks_count', 'useful_points_per_week',
             'best_week', 'top3_weeks_avg', 'boom_week_rate', 'tear3_rate', 'tear4_rate',
             'longest_tear', 'mean_week_points']

    # Calculate percentiles for each stat
    for stat in stats:
        values = [p.get(stat, 0) for p in players]
        if not values:
            continue

        values_array = np.array(values)

        for player in players:
            val = player.get(stat, 0)
            if len(values_array) > 1:
                percentile = (np.sum(values_array <= val) / len(values_array)) * 100
            else:
                percentile = 50
            player[f'{stat}_percentile'] = round(percentile, 1)

    return players


@app.route('/api/scoring-systems', methods=['GET'])
def get_scoring_systems():
    """Get list of available scoring systems."""
    try:
        from src.utils.multi_scoring import MultiScoringCalculator
        calc = MultiScoringCalculator()
        systems = calc.get_available_systems()

        return jsonify({
            'success': True,
            'scoring_systems': systems
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/export', methods=['GET'])
def export_rankings():
    """
    Export player rankings to CSV format.

    Query params:
        stats_type: 'batting', 'pitching', or 'combined' (default: batting)
        min_games: Minimum games played (default: 20)
        limit: Max players to return (default: 100)
        format: 'csv' or 'json' (default: csv)
        include_workhorse: Include workhorse metrics (default: true for pitchers)
    """
    try:
        stats_type = request.args.get('stats_type', 'batting')
        scoring_system = request.args.get('scoring_system', 'draftkings')
        min_games = int(request.args.get('min_games', 20))
        limit = int(request.args.get('limit', 100))
        export_format = request.args.get('format', 'csv').lower()
        include_workhorse = request.args.get('include_workhorse', 'true').lower() == 'true'

        # Get players from cache or live calculation (cache only for DraftKings)
        players = None
        if scoring_system == 'draftkings':
            players = load_cached_players(stats_type)

        if players is None:
            print(f"Calculating live for export with {scoring_system} scoring...")

            # Create analyzer with selected scoring system
            weekly_analyzer = WeeklyAnalyzer(db, scoring_system=scoring_system)

            if stats_type == 'combined':
                players = weekly_analyzer.get_top_bestball_players_combined(
                    min_games=min_games,
                    limit=limit
                )
            else:
                players = weekly_analyzer.get_top_bestball_players(
                    stats_type=stats_type,
                    min_games=min_games,
                    limit=limit
                )

        # Apply limit
        players = players[:limit]

        # Create temporary file for export
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        if export_format == 'json':
            # Export as JSON
            temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
            RankingsExporter.to_json(players, temp_file.name)
            filename = f'mlb_bestball_{scoring_system}_{stats_type}_{timestamp}.json'
            mimetype = 'application/json'
        else:
            # Export as CSV (default)
            temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
            RankingsExporter.to_csv(players, temp_file.name, include_workhorse=include_workhorse)
            filename = f'mlb_bestball_{scoring_system}_{stats_type}_{timestamp}.csv'
            mimetype = 'text/csv'

        temp_file.close()

        return send_file(
            temp_file.name,
            mimetype=mimetype,
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
