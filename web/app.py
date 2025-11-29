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
import logging

# Setup logger
logger = logging.getLogger(__name__)

# Add parent directory to path to import from src
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.database.db_manager import DatabaseManager
from src.analytics.weekly_analyzer import WeeklyAnalyzer
from src.analytics.draft_simulator import DraftSimulator
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


@app.route('/player/<int:player_id>', methods=['GET'])
def player_profile(player_id):
    """
    Show detailed player profile with visualizations.

    Query params:
        stats_type: 'batting' or 'pitching' (default: batting)
        scoring_system: Scoring system (default: draftkings)
    """
    try:
        stats_type = request.args.get('stats_type', 'batting')
        scoring_system = request.args.get('scoring_system', 'draftkings')

        # Get player info
        from src.database.models import Player
        session = db.get_session()
        player = session.query(Player).filter_by(player_id=player_id).first()

        if not player:
            session.close()
            return "Player not found", 404

        # Try to load from cache first (for instant loading)
        cache_file = BATTING_CACHE if stats_type == 'batting' else PITCHING_CACHE
        cached_player = None
        metrics = None
        chart_data = None

        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r') as f:
                    cache_data = json.load(f)
                    # Find this player in the cache
                    for p in cache_data.get('players', []):
                        if p['player_id'] == player_id:
                            cached_player = p
                            break

                if cached_player:
                    # Use cached data for instant loading!
                    metrics = cached_player  # The full player dict contains all metrics
                    chart_data = cached_player.get('chart_data', None)

            except Exception as e:
                logger.warning(f"Cache read error, falling back to live calculation: {e}")

        # Fall back to live calculation if cache not available
        if not metrics or not chart_data:
            logger.info(f"Cache miss for player {player_id}, calculating live...")

            # Initialize analyzer
            analyzer = WeeklyAnalyzer(db, scoring_system=scoring_system)

            # Get detailed metrics
            metrics = analyzer.calculate_weekly_volatility(player_id, stats_type, min_games=10)

            if not metrics:
                session.close()
                return "Insufficient data for this player", 404

            # Get rolling windows data for visualization
            rolling_df = analyzer.get_player_rolling_windows(player_id, stats_type, window_days=7)
            sequential_df = analyzer.get_player_sequential_weeks(player_id, stats_type, days_per_week=7)

            # Prepare chart data
            import pandas as pd
            chart_data = {
                'rolling_windows': {
                    'dates': (pd.to_datetime(rolling_df['end_date']).dt.strftime('%Y-%m-%d').tolist()
                              if not rolling_df.empty else []),
                    'points': rolling_df['window_points'].tolist() if not rolling_df.empty else []
                },
                'sequential_weeks': {
                    'week_numbers': list(range(1, len(sequential_df) + 1)) if not sequential_df.empty else [],
                    'points': sequential_df['week_points'].tolist() if not sequential_df.empty else [],
                    'useful_threshold': metrics.get('useful_threshold', 0)
                }
            }

        session.close()

        return render_template(
            'player_profile.html',
            player=player,
            metrics=metrics,
            chart_data=chart_data,
            stats_type=stats_type,
            scoring_system=scoring_system
        )

    except Exception as e:
        logger.error(f"Error loading player profile: {e}")
        return f"Error loading player profile: {str(e)}", 500


@app.route('/draft')
def draft_simulator():
    """Render draft simulator page."""
    return render_template('draft_simulator.html')


@app.route('/api/draft/debug')
def draft_debug():
    """Debug endpoint - check cache status directly in browser."""
    batting_path = os.path.join(CACHE_DIR, 'batting_players.json')
    pitching_path = os.path.join(CACHE_DIR, 'pitching_players.json')

    result = {
        'cache_dir': CACHE_DIR,
        'cache_dir_exists': os.path.exists(CACHE_DIR),
        'batting_cache': {
            'path': batting_path,
            'exists': os.path.exists(batting_path),
            'size': os.path.getsize(batting_path) if os.path.exists(batting_path) else 0
        },
        'pitching_cache': {
            'path': pitching_path,
            'exists': os.path.exists(pitching_path),
            'size': os.path.getsize(pitching_path) if os.path.exists(pitching_path) else 0
        }
    }

    # Try to load and count players
    if os.path.exists(batting_path):
        try:
            with open(batting_path) as f:
                data = json.load(f)
                result['batting_cache']['player_count'] = len(data.get('players', []))
                if data.get('players'):
                    result['batting_cache']['sample_player'] = data['players'][0]
        except Exception as e:
            result['batting_cache']['load_error'] = str(e)

    if os.path.exists(pitching_path):
        try:
            with open(pitching_path) as f:
                data = json.load(f)
                result['pitching_cache']['player_count'] = len(data.get('players', []))
        except Exception as e:
            result['pitching_cache']['load_error'] = str(e)

    # List cache directory contents
    if os.path.exists(CACHE_DIR):
        result['cache_contents'] = os.listdir(CACHE_DIR)

    return jsonify(result)


@app.route('/api/draft/players', methods=['GET'])
def get_draft_players():
    """
    Get available players for drafting with position info.
    Loads directly from cache files for reliability.
    """
    try:
        min_games = int(request.args.get('min_games', 20))
        limit = int(request.args.get('limit', 300))

        # Load directly from cache files (most reliable)
        batting_cache_path = os.path.join(CACHE_DIR, 'batting_players.json')
        pitching_cache_path = os.path.join(CACHE_DIR, 'pitching_players.json')

        players = []
        debug_info = {
            'batting_cache_exists': os.path.exists(batting_cache_path),
            'pitching_cache_exists': os.path.exists(pitching_cache_path),
            'cache_dir': CACHE_DIR,
            'batting_path': batting_cache_path,
            'pitching_path': pitching_cache_path
        }

        # Load batters
        if os.path.exists(batting_cache_path):
            with open(batting_cache_path, 'r') as f:
                batting_data = json.load(f)
                batters = batting_data.get('players', [])
                debug_info['batters_in_cache'] = len(batters)

                for batter in batters[:limit]:
                    if batter.get('games_played', 0) < min_games:
                        continue
                    pos = batter.get('position', 'UTIL')
                    # Derive position type
                    if pos in ['C', '1B', '2B', '3B', 'SS']:
                        pos_type = 'IF'
                    elif pos in ['LF', 'CF', 'RF', 'OF']:
                        pos_type = 'OF'
                    elif pos in ['P', 'SP', 'RP']:
                        pos_type = 'P'
                    elif pos == 'C':
                        pos_type = 'C'
                    else:
                        pos_type = 'UTIL'
                    batter['position_type'] = pos_type
                    batter['stats_type'] = 'batting'
                    players.append(batter)
        else:
            debug_info['batting_error'] = 'Cache file not found'

        # Load pitchers
        if os.path.exists(pitching_cache_path):
            with open(pitching_cache_path, 'r') as f:
                pitching_data = json.load(f)
                pitchers = pitching_data.get('players', [])
                debug_info['pitchers_in_cache'] = len(pitchers)

                for pitcher in pitchers[:limit]:
                    if pitcher.get('games_played', 0) < min_games:
                        continue
                    pitcher['position'] = 'P'
                    pitcher['position_type'] = 'P'
                    pitcher['stats_type'] = 'pitching'
                    players.append(pitcher)
        else:
            debug_info['pitching_error'] = 'Cache file not found'

        # Sort by bestball_score
        players.sort(key=lambda x: x.get('bestball_score', 0), reverse=True)

        debug_info['final_player_count'] = len(players)

        return jsonify({
            'success': True,
            'players': players,
            'count': len(players),
            'debug': debug_info
        })

    except Exception as e:
        import traceback
        logger.error(f"Error getting draft players: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500


@app.route('/api/draft/simulate', methods=['POST'])
def run_draft_simulation():
    """
    Run Monte Carlo simulation for a drafted roster.

    POST body:
        roster: List of player objects with player_id, position, stats_type
        num_simulations: Number of simulations (100-10000)
        method: 'bootstrap' or 'parametric'
        platform: Scoring platform
        weeks: Number of weeks to simulate (default: 26)
    """
    try:
        data = request.get_json()

        roster = data.get('roster', [])
        num_simulations = min(int(data.get('num_simulations', 500)), 10000)
        method = data.get('method', 'bootstrap')
        platform = data.get('platform', 'draftkings')
        weeks = int(data.get('weeks', 26))

        if len(roster) < 5:
            return jsonify({
                'success': False,
                'error': 'Need at least 5 players to simulate'
            }), 400

        # Create simulator
        simulator = DraftSimulator(
            db,
            scoring_system=platform,
            num_simulations=num_simulations,
            weeks_in_season=weeks
        )

        # Run simulation
        results = simulator.run_monte_carlo(roster, method=method)

        return jsonify({
            'success': True,
            'results': results
        })

    except Exception as e:
        logger.error(f"Error running simulation: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/draft/validate', methods=['POST'])
def validate_roster():
    """
    Validate a roster against platform requirements.

    POST body:
        roster: List of player objects
        platform: Platform to validate against
    """
    try:
        data = request.get_json()
        roster = data.get('roster', [])
        platform = data.get('platform', 'draftkings')

        simulator = DraftSimulator(db, scoring_system=platform)
        validation = simulator.validate_roster(roster, platform)

        return jsonify({
            'success': True,
            'validation': validation
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# =============================================================================
# MOCK DRAFT ROUTES
# =============================================================================

# Store active mock drafts in memory (in production, use Redis or similar)
_active_drafts = {}


@app.route('/mock-draft')
def mock_draft_page():
    """Render mock draft simulator page."""
    return render_template('mock_draft.html')


@app.route('/api/mock-draft/start', methods=['POST'])
def start_mock_draft():
    """
    Start a new mock draft.

    POST body:
        user_position: Draft position (1-12)
    """
    try:
        from src.analytics.mock_draft import MockDraftEngine

        data = request.get_json() or {}
        user_position = data.get('user_position', 1)

        if not 1 <= user_position <= 12:
            return jsonify({'success': False, 'error': 'Position must be 1-12'}), 400

        # Create new draft
        draft_id = f"draft_{datetime.now().strftime('%Y%m%d%H%M%S')}_{user_position}"
        engine = MockDraftEngine(user_position=user_position)

        _active_drafts[draft_id] = engine

        # Simulate until user's first pick
        picks_made = engine.simulate_until_user_pick()

        return jsonify({
            'success': True,
            'draft_id': draft_id,
            'state': engine.get_draft_state(),
            'picks_made': [
                {
                    'round': p.round_num,
                    'pick': p.pick_num,
                    'overall': p.overall_pick,
                    'team_id': p.team_id,
                    'player': p.player_name,
                    'position': p.position,
                    'adp': p.adp_rank
                }
                for p in picks_made
            ]
        })

    except Exception as e:
        logger.error(f"Error starting mock draft: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/mock-draft/<draft_id>/pick', methods=['POST'])
def make_mock_draft_pick(draft_id):
    """
    Make a pick in an active mock draft.

    POST body:
        player_id: Database player ID to draft
    """
    try:
        if draft_id not in _active_drafts:
            return jsonify({'success': False, 'error': 'Draft not found'}), 404

        engine = _active_drafts[draft_id]
        data = request.get_json()
        player_id = data.get('player_id')

        if not player_id:
            return jsonify({'success': False, 'error': 'player_id required'}), 400

        # Make user's pick
        user_pick = engine.user_make_pick(player_id)

        if not user_pick:
            return jsonify({'success': False, 'error': 'Not your turn'}), 400

        # Simulate until next user pick
        ai_picks = engine.simulate_until_user_pick()

        return jsonify({
            'success': True,
            'user_pick': {
                'round': user_pick.round_num,
                'pick': user_pick.pick_num,
                'overall': user_pick.overall_pick,
                'player': user_pick.player_name,
                'position': user_pick.position,
                'adp': user_pick.adp_rank
            },
            'ai_picks': [
                {
                    'round': p.round_num,
                    'pick': p.pick_num,
                    'overall': p.overall_pick,
                    'team_id': p.team_id,
                    'player': p.player_name,
                    'position': p.position,
                    'adp': p.adp_rank
                }
                for p in ai_picks
            ],
            'state': engine.get_draft_state()
        })

    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error making pick: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/mock-draft/<draft_id>/state')
def get_mock_draft_state(draft_id):
    """Get current state of a mock draft."""
    if draft_id not in _active_drafts:
        return jsonify({'success': False, 'error': 'Draft not found'}), 404

    engine = _active_drafts[draft_id]
    return jsonify({
        'success': True,
        'state': engine.get_draft_state()
    })


@app.route('/api/mock-draft/<draft_id>/available')
def get_available_players(draft_id):
    """Get available players in mock draft."""
    if draft_id not in _active_drafts:
        return jsonify({'success': False, 'error': 'Draft not found'}), 404

    engine = _active_drafts[draft_id]

    # Get query params for filtering
    position = request.args.get('position')
    limit = int(request.args.get('limit', 50))

    players = engine.available_players
    if position:
        players = [p for p in players if p.position == position]

    return jsonify({
        'success': True,
        'players': [
            {
                'player_id': p.db_player_id,
                'player_name': p.player_name,
                'position': p.position,
                'team': p.team,
                'adp_rank': p.rank,
                'ev_rank': p.ev_rank,
                'bestball_score': round(p.bestball_score, 1)
            }
            for p in players[:limit]
        ]
    })


@app.route('/api/mock-draft/<draft_id>/roster')
def get_user_roster(draft_id):
    """Get user's roster in mock draft."""
    if draft_id not in _active_drafts:
        return jsonify({'success': False, 'error': 'Draft not found'}), 404

    engine = _active_drafts[draft_id]
    roster = engine.get_user_roster()

    return jsonify({
        'success': True,
        'roster': [
            {
                'round': p.round_num,
                'pick': p.pick_num,
                'player_id': p.player_id,
                'player_name': p.player_name,
                'position': p.position,
                'adp_rank': p.adp_rank
            }
            for p in roster
        ]
    })


@app.route('/api/mock-draft/<draft_id>/all-rosters')
def get_all_rosters(draft_id):
    """Get all teams' rosters for completed draft."""
    if draft_id not in _active_drafts:
        return jsonify({'success': False, 'error': 'Draft not found'}), 404

    engine = _active_drafts[draft_id]

    rosters = {}
    for team in engine.teams:
        rosters[team.team_id] = {
            'name': team.name,
            'archetype': team.archetype.value,
            'roster': [
                {
                    'round': p.round_num,
                    'player_name': p.player_name,
                    'position': p.position,
                    'adp_rank': p.adp_rank
                }
                for p in team.roster
            ]
        }

    return jsonify({
        'success': True,
        'rosters': rosters
    })


# ============================================================================
# NFBC Cutline Championship Draft Routes
# ============================================================================

# Store active Cutline drafts
_active_cutline_drafts = {}


@app.route('/cutline-draft')
def cutline_draft_page():
    """Render Cutline draft simulator page."""
    return render_template('cutline_draft.html')


@app.route('/api/cutline-draft/start', methods=['POST'])
def start_cutline_draft():
    """
    Start a new Cutline Championship draft.

    POST body:
        user_position: Draft position (1-10)
    """
    try:
        from src.analytics.cutline_draft import CutlineDraftEngine

        data = request.get_json() or {}
        user_position = data.get('user_position', 1)

        if not 1 <= user_position <= 10:
            return jsonify({'success': False, 'error': 'Position must be 1-10'}), 400

        # Create new draft
        draft_id = f"cutline_{datetime.now().strftime('%Y%m%d%H%M%S')}_{user_position}"
        engine = CutlineDraftEngine(user_position=user_position)

        _active_cutline_drafts[draft_id] = engine

        # Simulate until user's first pick
        picks_made = engine.simulate_until_user_pick()

        return jsonify({
            'success': True,
            'draft_id': draft_id,
            'state': engine.get_draft_state(),
            'picks_made': [
                {
                    'round': p.round_num,
                    'pick': p.pick_num,
                    'overall': p.overall_pick,
                    'team_id': p.team_id,
                    'player': p.player_name,
                    'position': p.position,
                    'rank': p.rank
                }
                for p in picks_made
            ]
        })

    except Exception as e:
        logger.error(f"Error starting Cutline draft: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/cutline-draft/<draft_id>/pick', methods=['POST'])
def make_cutline_draft_pick(draft_id):
    """Make a pick in an active Cutline draft."""
    try:
        if draft_id not in _active_cutline_drafts:
            return jsonify({'success': False, 'error': 'Draft not found'}), 404

        engine = _active_cutline_drafts[draft_id]
        data = request.get_json()
        player_id = data.get('player_id')

        if not player_id:
            return jsonify({'success': False, 'error': 'player_id required'}), 400

        # Make user's pick
        user_pick = engine.user_make_pick(player_id)

        if not user_pick:
            return jsonify({'success': False, 'error': 'Not your turn'}), 400

        # Simulate until next user pick
        ai_picks = engine.simulate_until_user_pick()

        return jsonify({
            'success': True,
            'user_pick': {
                'round': user_pick.round_num,
                'pick': user_pick.pick_num,
                'overall': user_pick.overall_pick,
                'player': user_pick.player_name,
                'position': user_pick.position,
                'rank': user_pick.rank
            },
            'ai_picks': [
                {
                    'round': p.round_num,
                    'pick': p.pick_num,
                    'overall': p.overall_pick,
                    'team_id': p.team_id,
                    'player': p.player_name,
                    'position': p.position,
                    'rank': p.rank
                }
                for p in ai_picks
            ],
            'state': engine.get_draft_state()
        })

    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error making Cutline pick: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/cutline-draft/<draft_id>/state')
def get_cutline_draft_state(draft_id):
    """Get current state of a Cutline draft."""
    if draft_id not in _active_cutline_drafts:
        return jsonify({'success': False, 'error': 'Draft not found'}), 404

    engine = _active_cutline_drafts[draft_id]
    return jsonify({
        'success': True,
        'state': engine.get_draft_state()
    })


@app.route('/api/cutline-draft/<draft_id>/available')
def get_cutline_available_players(draft_id):
    """Get available players in Cutline draft."""
    if draft_id not in _active_cutline_drafts:
        return jsonify({'success': False, 'error': 'Draft not found'}), 404

    engine = _active_cutline_drafts[draft_id]

    position = request.args.get('position')
    limit = int(request.args.get('limit', 50))

    players = engine.get_available_players_by_position(position)

    return jsonify({
        'success': True,
        'players': players[:limit]
    })


@app.route('/api/cutline-draft/<draft_id>/roster')
def get_cutline_user_roster(draft_id):
    """Get user's roster in Cutline draft."""
    if draft_id not in _active_cutline_drafts:
        return jsonify({'success': False, 'error': 'Draft not found'}), 404

    engine = _active_cutline_drafts[draft_id]
    roster = engine.get_user_roster()

    return jsonify({
        'success': True,
        'roster': [
            {
                'round': p.round_num,
                'pick': p.pick_num,
                'player_id': p.player_id,
                'player_name': p.player_name,
                'position': p.position,
                'team': p.team_abbr,
                'rank': p.rank,
                'ev_rank': p.ev_rank
            }
            for p in roster
        ]
    })


@app.route('/api/cutline-draft/<draft_id>/simulate', methods=['POST'])
def simulate_cutline_season(draft_id):
    """
    Run Monte Carlo simulation on completed Cutline draft.

    POST body:
        num_simulations: Number of simulations (default: 500)
    """
    if draft_id not in _active_cutline_drafts:
        return jsonify({'success': False, 'error': 'Draft not found'}), 404

    engine = _active_cutline_drafts[draft_id]

    if not engine.is_draft_complete():
        return jsonify({'success': False, 'error': 'Draft not complete'}), 400

    try:
        from src.analytics.draft_simulator import DraftSimulator

        data = request.get_json() or {}
        num_sims = min(data.get('num_simulations', 500), 1000)

        # Get user roster
        roster = engine.export_roster_for_simulation()
        player_ids = [p['player_id'] for p in roster]

        # Run simulation with Cutline scoring
        simulator = DraftSimulator(
            db,
            scoring_system='cutline',
            num_simulations=num_sims,
            weeks_in_season=26
        )

        results = simulator.simulate_roster(player_ids)

        return jsonify({
            'success': True,
            'simulation_results': {
                'num_simulations': num_sims,
                'mean_total_points': round(results.get('mean_total', 0), 1),
                'std_dev': round(results.get('std_dev', 0), 1),
                'percentile_10': round(results.get('p10', 0), 1),
                'percentile_50': round(results.get('p50', 0), 1),
                'percentile_90': round(results.get('p90', 0), 1),
                'weekly_avg': round(results.get('weekly_avg', 0), 1),
                'ceiling': round(results.get('ceiling', 0), 1),
                'floor': round(results.get('floor', 0), 1),
            },
            'roster': roster
        })

    except Exception as e:
        logger.error(f"Error running Cutline simulation: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/cutline-draft/<draft_id>/all-rosters')
def get_cutline_all_rosters(draft_id):
    """Get all teams' rosters for completed Cutline draft."""
    if draft_id not in _active_cutline_drafts:
        return jsonify({'success': False, 'error': 'Draft not found'}), 404

    engine = _active_cutline_drafts[draft_id]

    rosters = {}
    for team in engine.teams:
        rosters[team.team_id] = {
            'name': team.name,
            'archetype': team.archetype.value,
            'position_counts': team.get_position_counts(),
            'roster': [
                {
                    'round': p.round_num,
                    'player_name': p.player_name,
                    'position': p.position,
                    'team': p.team_abbr,
                    'rank': p.rank
                }
                for p in team.roster
            ]
        }

    return jsonify({
        'success': True,
        'rosters': rosters
    })


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
