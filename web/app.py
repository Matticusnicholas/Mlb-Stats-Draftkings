"""
Flask web application for MLB Best Ball Analyzer.
Baseball Savant-style interface for Best Ball draft analysis.
"""
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import sys
import os

# Add parent directory to path to import from src
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.database.db_manager import DatabaseManager
from src.analytics.weekly_analyzer import WeeklyAnalyzer

app = Flask(__name__)
CORS(app)

# Initialize database and analyzer
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'mlb_stats.db')
db = DatabaseManager(DB_PATH)
weekly_analyzer = WeeklyAnalyzer(db)


@app.route('/')
def index():
    """Render main page."""
    return render_template('index.html')


@app.route('/api/players', methods=['GET'])
def get_players():
    """
    Get player data with Best Ball metrics.

    Query params:
        stats_type: 'batting' or 'pitching' (default: batting)
        min_games: Minimum games played (default: 20)
        limit: Max players to return (default: 100)
        sort_by: Field to sort by (default: bestball_score)
    """
    try:
        stats_type = request.args.get('stats_type', 'batting')
        min_games = int(request.args.get('min_games', 20))
        limit = int(request.args.get('limit', 100))
        sort_by = request.args.get('sort_by', 'bestball_score')

        # Get player data
        players = weekly_analyzer.get_top_bestball_players(
            stats_type=stats_type,
            min_games=min_games,
            limit=limit
        )

        # Sort by requested field
        players.sort(key=lambda x: x.get(sort_by, 0), reverse=True)

        # Calculate percentiles for each stat
        players_with_percentiles = calculate_percentiles(players)

        return jsonify({
            'success': True,
            'players': players_with_percentiles,
            'count': len(players_with_percentiles)
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
    stats = ['bestball_score', 'best_week', 'top3_weeks_avg', 'boom_week_rate',
             'tear3_rate', 'tear4_rate', 'longest_tear', 'mean_week_points']

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


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
