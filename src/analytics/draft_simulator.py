"""
Draft Simulator for Best Ball Fantasy Baseball.

Simulates a full season for a drafted roster using historical performance distributions,
models week-by-week performance, and calculates optimal best ball lineups.

Supports multiple platforms:
- DraftKings: 2P, 1C, 1-1B, 1-2B, 1-3B, 1-SS, 3OF (10 starters, NO UTIL)
- Underdog/Drafters: 3P, 3IF, 3OF, 1UTIL (10 starters)
"""
import numpy as np
import pandas as pd
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import logging
from collections import defaultdict

from ..database.db_manager import DatabaseManager
from ..database.models import PlayerGame, Game, Player
from .weekly_analyzer import WeeklyAnalyzer

logger = logging.getLogger(__name__)


class PositionType(Enum):
    """Position classification for flex eligibility."""
    INFIELD = "IF"
    OUTFIELD = "OF"
    PITCHER = "P"
    CATCHER = "C"
    UTILITY = "UTIL"


# Position to position type mapping
POSITION_CLASSIFICATION = {
    # Infielders
    '1B': PositionType.INFIELD,
    '2B': PositionType.INFIELD,
    '3B': PositionType.INFIELD,
    'SS': PositionType.INFIELD,
    # Catcher (can be IF or separate)
    'C': PositionType.CATCHER,
    # Outfielders
    'LF': PositionType.OUTFIELD,
    'CF': PositionType.OUTFIELD,
    'RF': PositionType.OUTFIELD,
    'OF': PositionType.OUTFIELD,
    # Pitchers
    'P': PositionType.PITCHER,
    'SP': PositionType.PITCHER,
    'RP': PositionType.PITCHER,
    # Designated hitter / Utility
    'DH': PositionType.UTILITY,
    'UTIL': PositionType.UTILITY,
    # Pinch hitter (shouldn't appear but handle it)
    'PH': PositionType.UTILITY,
}


@dataclass
class RosterSlot:
    """Defines a roster slot configuration."""
    name: str
    count: int
    eligible_types: List[PositionType]
    eligible_positions: List[str]


# Platform-specific roster configurations
ROSTER_CONFIGS = {
    'draftkings': {
        'slots': [
            RosterSlot('P', 2, [PositionType.PITCHER], ['P', 'SP', 'RP']),
            RosterSlot('C', 1, [PositionType.CATCHER], ['C']),
            RosterSlot('1B', 1, [PositionType.INFIELD], ['1B']),
            RosterSlot('2B', 1, [PositionType.INFIELD], ['2B']),
            RosterSlot('3B', 1, [PositionType.INFIELD], ['3B']),
            RosterSlot('SS', 1, [PositionType.INFIELD], ['SS']),
            RosterSlot('OF', 3, [PositionType.OUTFIELD], ['OF', 'LF', 'CF', 'RF']),
        ],
        'roster_size': 20,
        'weekly_starters': 10,
        'description': 'DraftKings Best Ball'
    },
    'underdog': {
        'slots': [
            RosterSlot('P', 3, [PositionType.PITCHER], ['P', 'SP', 'RP']),
            RosterSlot('IF', 3, [PositionType.INFIELD, PositionType.CATCHER],
                      ['C', '1B', '2B', '3B', 'SS']),
            RosterSlot('OF', 3, [PositionType.OUTFIELD], ['OF', 'LF', 'CF', 'RF']),
            RosterSlot('UTIL', 1, [PositionType.INFIELD, PositionType.OUTFIELD, PositionType.CATCHER],
                      ['C', '1B', '2B', '3B', 'SS', 'LF', 'CF', 'RF', 'OF']),
        ],
        'roster_size': 20,
        'weekly_starters': 10,
        'description': 'Underdog Best Ball'
    },
    'drafters': {
        'slots': [
            RosterSlot('P', 3, [PositionType.PITCHER], ['P', 'SP', 'RP']),
            RosterSlot('IF', 3, [PositionType.INFIELD, PositionType.CATCHER],
                      ['C', '1B', '2B', '3B', 'SS']),
            RosterSlot('OF', 3, [PositionType.OUTFIELD], ['OF', 'LF', 'CF', 'RF']),
            RosterSlot('UTIL', 1, [PositionType.INFIELD, PositionType.OUTFIELD, PositionType.CATCHER],
                      ['C', '1B', '2B', '3B', 'SS', 'LF', 'CF', 'RF', 'OF']),
        ],
        'roster_size': 20,
        'weekly_starters': 10,
        'description': 'Drafters Best Ball'
    }
}


@dataclass
class SimulatedWeek:
    """Results for a single simulated week."""
    week_number: int
    player_scores: Dict[int, float]  # player_id -> simulated points
    optimal_lineup: List[int]  # player_ids in optimal starting lineup
    total_points: float
    bench_points: float


@dataclass
class SimulatedSeason:
    """Complete simulated season results."""
    weeks: List[SimulatedWeek]
    total_points: float
    weekly_totals: List[float]
    optimal_weekly_points: List[float]


class DraftSimulator:
    """
    Monte Carlo draft simulator for Best Ball fantasy baseball.

    Uses historical performance distributions to simulate season outcomes
    for a drafted roster, then calculates optimal best ball lineups.
    """

    def __init__(
        self,
        db_manager: DatabaseManager,
        scoring_system: str = 'draftkings',
        num_simulations: int = 1000,
        weeks_in_season: int = 26
    ):
        """
        Initialize draft simulator.

        Args:
            db_manager: Database manager instance
            scoring_system: Platform scoring system
            num_simulations: Number of Monte Carlo simulations
            weeks_in_season: Number of weeks in season (MLB ~26 weeks)
        """
        self.db = db_manager
        self.scoring_system = scoring_system
        self.num_simulations = num_simulations
        self.weeks_in_season = weeks_in_season
        self.weekly_analyzer = WeeklyAnalyzer(db_manager, scoring_system)

        # Cache player historical data for simulation
        self._player_distributions = {}
        self._player_positions = {}
        self._player_names = {}

        logger.info(f"DraftSimulator initialized: {scoring_system}, {num_simulations} sims, {weeks_in_season} weeks")

    def get_position_type(self, position: str) -> PositionType:
        """
        Get position type (IF/OF/P) from specific position.

        Args:
            position: Specific position string (e.g., '1B', 'CF')

        Returns:
            PositionType enum
        """
        if not position:
            return PositionType.UTILITY

        # Clean position string
        pos = position.upper().strip()

        # Handle multi-position eligibility (take first)
        if '/' in pos:
            pos = pos.split('/')[0]

        return POSITION_CLASSIFICATION.get(pos, PositionType.UTILITY)

    def get_player_primary_position(self, player_id: int) -> Tuple[str, PositionType]:
        """
        Get player's primary position from their game history.

        Args:
            player_id: MLB player ID

        Returns:
            Tuple of (position string, PositionType)
        """
        if player_id in self._player_positions:
            pos = self._player_positions[player_id]
            return pos, self.get_position_type(pos)

        session = self.db.get_session()
        try:
            # Get most common position from games
            games = session.query(PlayerGame).filter(
                PlayerGame.player_id == player_id
            ).all()

            if not games:
                return 'UTIL', PositionType.UTILITY

            # Count position occurrences
            position_counts = defaultdict(int)
            for game in games:
                if game.position:
                    position_counts[game.position] += 1

            if not position_counts:
                # Check if pitcher by stats_type
                if games[0].stats_type == 'pitching':
                    return 'P', PositionType.PITCHER
                return 'UTIL', PositionType.UTILITY

            # Get most common position
            primary_pos = max(position_counts, key=position_counts.get)
            self._player_positions[player_id] = primary_pos

            return primary_pos, self.get_position_type(primary_pos)

        finally:
            session.close()

    def load_player_distribution(self, player_id: int, stats_type: str = None) -> Dict:
        """
        Load historical performance distribution for a player.

        Args:
            player_id: MLB player ID
            stats_type: 'batting' or 'pitching' (auto-detected if None)

        Returns:
            Dictionary with distribution parameters
        """
        cache_key = (player_id, stats_type)
        if cache_key in self._player_distributions:
            return self._player_distributions[cache_key]

        session = self.db.get_session()
        try:
            # Get player info
            player = session.query(Player).filter_by(player_id=player_id).first()
            if player:
                self._player_names[player_id] = player.player_name

            # Get player games
            games = self.db.get_player_games(player_id, stats_type)

            if not games:
                return None

            # Determine stats_type from games if not specified
            if stats_type is None:
                stats_type = games[0].stats_type

            # Get points based on scoring system
            if self.scoring_system == 'draftkings':
                points = [g.dk_points for g in games]
            elif self.scoring_system == 'underdog':
                points = [g.underdog_points or g.dk_points for g in games]
            elif self.scoring_system == 'drafters':
                points = [g.drafters_points or g.dk_points for g in games]
            else:
                points = [g.dk_points for g in games]

            points = np.array(points)

            # Calculate distribution parameters
            distribution = {
                'player_id': player_id,
                'player_name': self._player_names.get(player_id, f'Player {player_id}'),
                'stats_type': stats_type,
                'games_played': len(points),
                'mean': float(np.mean(points)),
                'std': float(np.std(points)),
                'min': float(np.min(points)),
                'max': float(np.max(points)),
                'median': float(np.median(points)),
                'percentile_25': float(np.percentile(points, 25)),
                'percentile_75': float(np.percentile(points, 75)),
                'percentile_90': float(np.percentile(points, 90)),
                'percentile_95': float(np.percentile(points, 95)),
                # Store raw points for bootstrap sampling
                'historical_points': points.tolist(),
                # Games per week estimate
                'games_per_week': len(points) / self.weeks_in_season if len(points) > 0 else 0
            }

            # Get position info
            pos, pos_type = self.get_player_primary_position(player_id)
            distribution['position'] = pos
            distribution['position_type'] = pos_type.value

            self._player_distributions[cache_key] = distribution
            return distribution

        finally:
            session.close()

    def simulate_player_week(
        self,
        distribution: Dict,
        method: str = 'bootstrap'
    ) -> float:
        """
        Simulate a single week's performance for a player.

        Args:
            distribution: Player's historical distribution
            method: 'bootstrap' (resample history) or 'parametric' (normal dist)

        Returns:
            Simulated weekly points
        """
        games_per_week = distribution.get('games_per_week', 4)

        # Estimate games this week (slightly random)
        num_games = max(1, int(np.random.poisson(games_per_week)))

        if method == 'bootstrap':
            # Bootstrap: randomly sample from historical games
            historical = distribution['historical_points']
            if len(historical) == 0:
                return 0.0

            sampled_games = np.random.choice(historical, size=num_games, replace=True)
            return float(np.sum(sampled_games))

        else:  # parametric
            # Parametric: sample from fitted normal distribution
            mean_per_game = distribution['mean']
            std_per_game = distribution['std']

            # Sample each game
            game_points = np.random.normal(mean_per_game, std_per_game, size=num_games)
            # Floor at 0 (can't have negative total)
            game_points = np.maximum(game_points, 0)
            return float(np.sum(game_points))

    def optimize_weekly_lineup(
        self,
        player_scores: Dict[int, float],
        roster: List[Dict],
        platform: str = 'draftkings'
    ) -> Tuple[List[int], float]:
        """
        Select optimal starting lineup for best ball scoring.

        Args:
            player_scores: player_id -> weekly points
            roster: List of player dictionaries with position info
            platform: Platform configuration to use

        Returns:
            Tuple of (list of starting player_ids, total points)
        """
        config = ROSTER_CONFIGS.get(platform, ROSTER_CONFIGS['draftkings'])
        slots = config['slots']

        # Sort players by weekly score (descending)
        scored_players = [
            (p, player_scores.get(p['player_id'], 0))
            for p in roster
        ]
        scored_players.sort(key=lambda x: x[1], reverse=True)

        # Greedy slot filling - take best available for each slot
        selected = []
        used_players = set()

        for slot in slots:
            for _ in range(slot.count):
                best_player = None
                best_score = -1

                for player, score in scored_players:
                    if player['player_id'] in used_players:
                        continue

                    # Check position eligibility
                    player_pos = player.get('position', '')
                    player_pos_type = player.get('position_type', '')

                    # Check if eligible for this slot
                    eligible = False

                    # Check by position type
                    for elig_type in slot.eligible_types:
                        if player_pos_type == elig_type.value:
                            eligible = True
                            break

                    # Also check by specific position
                    if not eligible:
                        if player_pos in slot.eligible_positions:
                            eligible = True

                    if eligible and score > best_score:
                        best_player = player
                        best_score = score

                if best_player:
                    selected.append(best_player['player_id'])
                    used_players.add(best_player['player_id'])

        total_points = sum(player_scores.get(pid, 0) for pid in selected)
        return selected, total_points

    def simulate_season(
        self,
        roster: List[Dict],
        method: str = 'bootstrap'
    ) -> SimulatedSeason:
        """
        Simulate a complete season for a roster.

        Args:
            roster: List of player dictionaries with player_id, position, etc.
            method: Simulation method ('bootstrap' or 'parametric')

        Returns:
            SimulatedSeason with week-by-week results
        """
        # Load distributions for all players
        for player in roster:
            player_id = player['player_id']
            stats_type = player.get('stats_type', 'batting')

            dist = self.load_player_distribution(player_id, stats_type)
            if dist:
                # Add position info to roster entry
                player['position'] = dist['position']
                player['position_type'] = dist['position_type']

        weeks = []
        weekly_totals = []

        for week_num in range(1, self.weeks_in_season + 1):
            # Simulate each player's week
            player_scores = {}
            for player in roster:
                player_id = player['player_id']
                stats_type = player.get('stats_type')
                cache_key = (player_id, stats_type)

                dist = self._player_distributions.get(cache_key)
                if dist:
                    player_scores[player_id] = self.simulate_player_week(dist, method)
                else:
                    player_scores[player_id] = 0.0

            # Optimize lineup
            optimal_lineup, total_points = self.optimize_weekly_lineup(
                player_scores, roster, self.scoring_system
            )

            # Calculate bench points
            bench_points = sum(
                score for pid, score in player_scores.items()
                if pid not in optimal_lineup
            )

            week = SimulatedWeek(
                week_number=week_num,
                player_scores=player_scores,
                optimal_lineup=optimal_lineup,
                total_points=total_points,
                bench_points=bench_points
            )
            weeks.append(week)
            weekly_totals.append(total_points)

        return SimulatedSeason(
            weeks=weeks,
            total_points=sum(weekly_totals),
            weekly_totals=weekly_totals,
            optimal_weekly_points=weekly_totals
        )

    def run_monte_carlo(
        self,
        roster: List[Dict],
        method: str = 'bootstrap',
        return_all_simulations: bool = False
    ) -> Dict:
        """
        Run Monte Carlo simulation for a roster.

        Args:
            roster: List of player dictionaries
            method: Simulation method
            return_all_simulations: Whether to return all simulation details

        Returns:
            Dictionary with simulation results and percentile outcomes
        """
        logger.info(f"Running {self.num_simulations} simulations for roster of {len(roster)} players")

        season_totals = []
        all_simulations = []

        for sim_num in range(self.num_simulations):
            season = self.simulate_season(roster, method)
            season_totals.append(season.total_points)

            if return_all_simulations:
                all_simulations.append({
                    'simulation': sim_num + 1,
                    'total_points': season.total_points,
                    'weekly_totals': season.weekly_totals
                })

            if (sim_num + 1) % 100 == 0:
                logger.debug(f"Completed simulation {sim_num + 1}/{self.num_simulations}")

        season_totals = np.array(season_totals)

        # Calculate percentile outcomes
        results = {
            'num_simulations': self.num_simulations,
            'roster_size': len(roster),
            'weeks_in_season': self.weeks_in_season,
            'scoring_system': self.scoring_system,

            # Distribution stats
            'mean_season_points': float(np.mean(season_totals)),
            'median_season_points': float(np.median(season_totals)),
            'std_season_points': float(np.std(season_totals)),
            'min_season_points': float(np.min(season_totals)),
            'max_season_points': float(np.max(season_totals)),

            # Percentile outcomes
            'percentile_10': float(np.percentile(season_totals, 10)),
            'percentile_25': float(np.percentile(season_totals, 25)),
            'percentile_50': float(np.percentile(season_totals, 50)),
            'percentile_75': float(np.percentile(season_totals, 75)),
            'percentile_90': float(np.percentile(season_totals, 90)),
            'percentile_95': float(np.percentile(season_totals, 95)),
            'percentile_99': float(np.percentile(season_totals, 99)),

            # Weekly averages
            'avg_weekly_points': float(np.mean(season_totals) / self.weeks_in_season),

            # Histogram data for visualization
            'histogram': {
                'values': season_totals.tolist(),
                'bins': 30
            },

            # Roster info with positions
            'roster': [
                {
                    'player_id': p['player_id'],
                    'player_name': self._player_names.get(p['player_id'], f"Player {p['player_id']}"),
                    'position': p.get('position', 'UTIL'),
                    'position_type': p.get('position_type', 'UTIL'),
                    'stats_type': p.get('stats_type', 'batting')
                }
                for p in roster
            ]
        }

        if return_all_simulations:
            results['simulations'] = all_simulations

        return results

    def get_draft_pool(
        self,
        min_games: int = 20,
        limit: int = 300,
        use_cache: bool = True
    ) -> List[Dict]:
        """
        Get available players for drafting with their metrics.

        Args:
            min_games: Minimum games played
            limit: Maximum players to return per category
            use_cache: Whether to try using cached data first

        Returns:
            List of player dictionaries with metrics and position info
        """
        import os
        import json

        players = []

        # Try to use cached data for faster loading
        cache_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'web', 'cache')
        batting_cache = os.path.join(cache_dir, 'batting_players.json')
        pitching_cache = os.path.join(cache_dir, 'pitching_players.json')

        if use_cache and os.path.exists(batting_cache) and os.path.exists(pitching_cache):
            logger.info("Loading draft pool from cache files")
            try:
                # Load batters from cache
                with open(batting_cache, 'r') as f:
                    batting_data = json.load(f)
                    batters = batting_data.get('players', [])[:limit]

                for batter in batters:
                    if batter.get('games_played', 0) < min_games:
                        continue
                    # Use position from cache, derive position_type without DB query
                    pos = batter.get('position', 'UTIL')
                    pos_type = self.get_position_type(pos)
                    batter['position'] = pos
                    batter['position_type'] = pos_type.value
                    batter['stats_type'] = 'batting'
                    players.append(batter)

                # Load pitchers from cache
                with open(pitching_cache, 'r') as f:
                    pitching_data = json.load(f)
                    pitchers = pitching_data.get('players', [])[:limit]

                for pitcher in pitchers:
                    if pitcher.get('games_played', 0) < min_games:
                        continue
                    pitcher['position'] = 'P'
                    pitcher['position_type'] = PositionType.PITCHER.value
                    pitcher['stats_type'] = 'pitching'
                    players.append(pitcher)

                logger.info(f"Loaded {len(players)} players from cache")
                return players

            except Exception as e:
                logger.warning(f"Cache load failed, falling back to live calculation: {e}")

        # Fall back to live calculation
        logger.info("Calculating draft pool (no cache available)")

        # Get batters
        batters = self.weekly_analyzer.get_top_bestball_players(
            stats_type='batting',
            min_games=min_games,
            limit=limit
        )

        for batter in batters:
            player_id = batter['player_id']
            pos, pos_type = self.get_player_primary_position(player_id)
            batter['position'] = pos
            batter['position_type'] = pos_type.value
            batter['stats_type'] = 'batting'
            players.append(batter)

        # Get pitchers
        pitchers = self.weekly_analyzer.get_top_bestball_players(
            stats_type='pitching',
            min_games=min_games,
            limit=limit
        )

        for pitcher in pitchers:
            pitcher['position'] = 'P'
            pitcher['position_type'] = PositionType.PITCHER.value
            pitcher['stats_type'] = 'pitching'
            players.append(pitcher)

        return players

    def validate_roster(
        self,
        roster: List[Dict],
        platform: str = 'draftkings'
    ) -> Dict:
        """
        Validate that a roster meets platform requirements.

        Args:
            roster: List of player dictionaries
            platform: Platform to validate against

        Returns:
            Dictionary with validation results
        """
        config = ROSTER_CONFIGS.get(platform, ROSTER_CONFIGS['draftkings'])

        issues = []

        # Check roster size
        if len(roster) != config['roster_size']:
            issues.append(f"Roster has {len(roster)} players, needs {config['roster_size']}")

        # Count by position type
        position_counts = defaultdict(int)
        for player in roster:
            pos_type = player.get('position_type', 'UTIL')
            position_counts[pos_type] += 1

        return {
            'valid': len(issues) == 0,
            'issues': issues,
            'position_counts': dict(position_counts),
            'roster_size': len(roster),
            'required_size': config['roster_size']
        }


def compare_rosters(
    simulator: DraftSimulator,
    roster1: List[Dict],
    roster2: List[Dict],
    num_simulations: int = 1000
) -> Dict:
    """
    Compare two rosters head-to-head.

    Args:
        simulator: DraftSimulator instance
        roster1: First roster
        roster2: Second roster
        num_simulations: Simulations per roster

    Returns:
        Comparison results
    """
    # Temporarily set simulation count
    original_sims = simulator.num_simulations
    simulator.num_simulations = num_simulations

    results1 = simulator.run_monte_carlo(roster1)
    results2 = simulator.run_monte_carlo(roster2)

    simulator.num_simulations = original_sims

    # Calculate head-to-head win probability
    totals1 = results1['histogram']['values']
    totals2 = results2['histogram']['values']

    # Pair random draws and count wins
    min_len = min(len(totals1), len(totals2))
    wins1 = sum(1 for i in range(min_len) if totals1[i] > totals2[i])
    wins2 = sum(1 for i in range(min_len) if totals2[i] > totals1[i])
    ties = min_len - wins1 - wins2

    return {
        'roster1': {
            'mean': results1['mean_season_points'],
            'median': results1['median_season_points'],
            'percentile_75': results1['percentile_75'],
            'percentile_90': results1['percentile_90'],
            'win_pct': wins1 / min_len * 100
        },
        'roster2': {
            'mean': results2['mean_season_points'],
            'median': results2['median_season_points'],
            'percentile_75': results2['percentile_75'],
            'percentile_90': results2['percentile_90'],
            'win_pct': wins2 / min_len * 100
        },
        'tie_pct': ties / min_len * 100
    }
