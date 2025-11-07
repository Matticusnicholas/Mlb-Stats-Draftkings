"""
Volatility analysis engine for identifying high-variance MLB players.
"""
import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional
from datetime import datetime, timedelta, date
from scipy import stats as scipy_stats
import logging

from ..database.models import PlayerGame, Game
from ..database.db_manager import DatabaseManager

logger = logging.getLogger(__name__)


class VolatilityAnalyzer:
    """
    Analyzes player performance volatility and streakiness for DFS optimization.
    """

    def __init__(self, db_manager: DatabaseManager):
        """
        Initialize volatility analyzer.

        Args:
            db_manager: Database manager instance
        """
        self.db = db_manager

    def calculate_player_volatility(
        self,
        player_id: int,
        stats_type: str = "batting",
        min_games: int = 10
    ) -> Optional[Dict]:
        """
        Calculate comprehensive volatility metrics for a player.

        Args:
            player_id: MLB player ID
            stats_type: 'batting' or 'pitching'
            min_games: Minimum games required for analysis

        Returns:
            Dictionary of volatility metrics or None if insufficient data
        """
        # Get player games
        player_games = self.db.get_player_games(player_id, stats_type)

        if len(player_games) < min_games:
            logger.info(f"Player {player_id} has only {len(player_games)} games, minimum is {min_games}")
            return None

        # Extract DK points
        points = [pg.dk_points for pg in player_games]
        points_array = np.array(points)

        # Get game dates for time-based analysis
        session = self.db.get_session()
        try:
            games_with_dates = []
            for pg in player_games:
                game = session.query(Game).filter_by(game_pk=pg.game_pk).first()
                if game:
                    games_with_dates.append({
                        'date': game.game_date,
                        'points': pg.dk_points
                    })
        finally:
            session.close()

        # Sort by date
        games_with_dates.sort(key=lambda x: x['date'])

        metrics = {}

        # Basic stats
        metrics['games_played'] = len(points)
        metrics['total_points'] = float(np.sum(points_array))
        metrics['mean_points'] = float(np.mean(points_array))
        metrics['median_points'] = float(np.median(points_array))

        # Volatility metrics
        metrics['std_dev'] = float(np.std(points_array, ddof=1))
        metrics['coefficient_of_variation'] = (
            metrics['std_dev'] / metrics['mean_points']
            if metrics['mean_points'] > 0 else 0
        )
        metrics['min_points'] = float(np.min(points_array))
        metrics['max_points'] = float(np.max(points_array))
        metrics['points_range'] = metrics['max_points'] - metrics['min_points']

        # Percentiles
        metrics['percentile_25'] = float(np.percentile(points_array, 25))
        metrics['percentile_75'] = float(np.percentile(points_array, 75))
        metrics['percentile_90'] = float(np.percentile(points_array, 90))
        metrics['percentile_95'] = float(np.percentile(points_array, 95))

        # Spike metrics
        sorted_points = np.sort(points_array)[::-1]  # Descending
        top5_count = min(5, len(sorted_points))
        metrics['top5_games_total'] = float(np.sum(sorted_points[:top5_count]))
        metrics['top5_games_pct'] = (
            metrics['top5_games_total'] / metrics['total_points'] * 100
            if metrics['total_points'] > 0 else 0
        )

        # Spike rate: percentage of games above 90th percentile (by definition, ~10%)
        spike_threshold = metrics['percentile_90']
        spike_games = np.sum(points_array >= spike_threshold)
        metrics['spike_rate'] = float(spike_games / len(points_array) * 100)

        # Boom/Bust rates
        metrics['boom_rate'] = float(np.sum(points_array >= 20) / len(points_array) * 100)
        metrics['bust_rate'] = float(np.sum(points_array < 5) / len(points_array) * 100)

        # Streakiness analysis
        streakiness = self._analyze_streakiness(games_with_dates)
        metrics.update(streakiness)

        # Recent form (last 7, 14, 30 days)
        recent_form = self._analyze_recent_form(games_with_dates)
        metrics.update(recent_form)

        # Calculate composite variance score
        metrics['variance_score'] = self._calculate_variance_score(metrics)

        # Calculate upside score (weighted toward ceiling games)
        metrics['upside_score'] = self._calculate_upside_score(metrics)

        metrics['stats_type'] = stats_type

        return metrics

    def _analyze_streakiness(self, games_with_dates: List[Dict]) -> Dict:
        """
        Analyze hot and cold streaks.

        Args:
            games_with_dates: List of dicts with 'date' and 'points'

        Returns:
            Dictionary of streak metrics
        """
        if len(games_with_dates) < 5:
            return {
                'longest_hot_streak': 0,
                'longest_cold_streak': 0,
                'current_streak_type': 'neutral',
                'current_streak_length': 0
            }

        points = [g['points'] for g in games_with_dates]
        mean_points = np.mean(points)
        std_points = np.std(points, ddof=1)

        # Define hot (>0.5 std above mean) and cold (<0.5 std below mean)
        hot_threshold = mean_points + 0.5 * std_points
        cold_threshold = mean_points - 0.5 * std_points

        longest_hot = 0
        longest_cold = 0
        current_hot = 0
        current_cold = 0

        for pts in points:
            if pts >= hot_threshold:
                current_hot += 1
                current_cold = 0
                longest_hot = max(longest_hot, current_hot)
            elif pts <= cold_threshold:
                current_cold += 1
                current_hot = 0
                longest_cold = max(longest_cold, current_cold)
            else:
                current_hot = 0
                current_cold = 0

        # Determine current streak (from most recent games)
        recent_points = points[-5:]  # Last 5 games
        recent_mean = np.mean(recent_points)

        if recent_mean >= hot_threshold:
            current_streak_type = 'hot'
            current_streak_length = current_hot
        elif recent_mean <= cold_threshold:
            current_streak_type = 'cold'
            current_streak_length = current_cold
        else:
            current_streak_type = 'neutral'
            current_streak_length = 0

        return {
            'longest_hot_streak': longest_hot,
            'longest_cold_streak': longest_cold,
            'current_streak_type': current_streak_type,
            'current_streak_length': current_streak_length
        }

    def _analyze_recent_form(self, games_with_dates: List[Dict]) -> Dict:
        """
        Analyze recent performance (last 7, 14, 30 days).

        Args:
            games_with_dates: List of dicts with 'date' and 'points'

        Returns:
            Dictionary of recent form metrics
        """
        if not games_with_dates:
            return {
                'last7_mean': 0.0, 'last14_mean': 0.0, 'last30_mean': 0.0,
                'last7_std': 0.0, 'last14_std': 0.0, 'last30_std': 0.0
            }

        now = datetime.now()
        last7_cutoff = now - timedelta(days=7)
        last14_cutoff = now - timedelta(days=14)
        last30_cutoff = now - timedelta(days=30)

        last7_points = [g['points'] for g in games_with_dates if g['date'] >= last7_cutoff]
        last14_points = [g['points'] for g in games_with_dates if g['date'] >= last14_cutoff]
        last30_points = [g['points'] for g in games_with_dates if g['date'] >= last30_cutoff]

        return {
            'last7_mean': float(np.mean(last7_points)) if last7_points else 0.0,
            'last14_mean': float(np.mean(last14_points)) if last14_points else 0.0,
            'last30_mean': float(np.mean(last30_points)) if last30_points else 0.0,
            'last7_std': float(np.std(last7_points, ddof=1)) if len(last7_points) > 1 else 0.0,
            'last14_std': float(np.std(last14_points, ddof=1)) if len(last14_points) > 1 else 0.0,
            'last30_std': float(np.std(last30_points, ddof=1)) if len(last30_points) > 1 else 0.0
        }

    def _calculate_variance_score(self, metrics: Dict) -> float:
        """
        Calculate a composite variance score (0-100).
        Higher score = more desirable for high-variance tournaments.

        Args:
            metrics: Dictionary of calculated metrics

        Returns:
            Variance score (0-100)
        """
        # Normalize components to 0-100 scale

        # 1. Coefficient of variation (normalized, higher is better)
        cv_score = min(100, metrics['coefficient_of_variation'] * 50)

        # 2. Top 5 games percentage (higher concentration = more volatile)
        top5_score = metrics['top5_games_pct']

        # 3. Spike rate (higher = more likely to have big games)
        spike_score = metrics['spike_rate'] * 5  # Scale from 0-20% to 0-100

        # 4. Boom rate (20+ point games)
        boom_score = metrics['boom_rate'] * 2  # Scale to 0-100

        # 5. Points range (normalized by mean)
        range_score = min(100, (metrics['points_range'] / metrics['mean_points']) * 10)

        # Weighted combination
        variance_score = (
            cv_score * 0.25 +
            top5_score * 0.20 +
            spike_score * 0.20 +
            boom_score * 0.20 +
            range_score * 0.15
        )

        return round(variance_score, 2)

    def _calculate_upside_score(self, metrics: Dict) -> float:
        """
        Calculate an upside score emphasizing ceiling games.

        Args:
            metrics: Dictionary of calculated metrics

        Returns:
            Upside score (0-100)
        """
        # Components
        max_score = min(100, metrics['max_points'] * 2)
        p95_score = min(100, metrics['percentile_95'] * 2)
        boom_score = metrics['boom_rate'] * 2

        # Weighted combination (emphasize max and ceiling)
        upside_score = (
            max_score * 0.40 +
            p95_score * 0.35 +
            boom_score * 0.25
        )

        return round(upside_score, 2)

    def analyze_all_players(
        self,
        stats_type: str = "batting",
        min_games: int = 20
    ) -> List[int]:
        """
        Analyze volatility for all players with sufficient games.

        Args:
            stats_type: 'batting' or 'pitching'
            min_games: Minimum games required

        Returns:
            List of player IDs analyzed
        """
        session = self.db.get_session()
        try:
            # Get all unique players with sufficient games
            from sqlalchemy import func
            player_ids = session.query(
                PlayerGame.player_id
            ).filter_by(
                stats_type=stats_type
            ).group_by(
                PlayerGame.player_id
            ).having(
                func.count(PlayerGame.id) >= min_games
            ).all()

            player_ids = [pid[0] for pid in player_ids]
            logger.info(f"Analyzing {len(player_ids)} players with {min_games}+ games")

            analyzed = []
            for player_id in player_ids:
                try:
                    metrics = self.calculate_player_volatility(player_id, stats_type, min_games)
                    if metrics:
                        self.db.save_player_volatility(player_id, stats_type, metrics)
                        analyzed.append(player_id)
                except Exception as e:
                    logger.error(f"Error analyzing player {player_id}: {e}")

            logger.info(f"Successfully analyzed {len(analyzed)} players")
            return analyzed

        finally:
            session.close()

    def get_weekly_volatility(
        self,
        player_id: int,
        stats_type: str = "batting"
    ) -> pd.DataFrame:
        """
        Calculate rolling weekly volatility metrics.

        Args:
            player_id: MLB player ID
            stats_type: 'batting' or 'pitching'

        Returns:
            DataFrame with weekly stats
        """
        player_games = self.db.get_player_games(player_id, stats_type)

        if not player_games:
            return pd.DataFrame()

        # Create DataFrame
        session = self.db.get_session()
        try:
            data = []
            for pg in player_games:
                game = session.query(Game).filter_by(game_pk=pg.game_pk).first()
                if game:
                    data.append({
                        'date': game.game_date,
                        'points': pg.dk_points
                    })

            df = pd.DataFrame(data)
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date')

            # Calculate weekly stats (7-day rolling window)
            df['week_mean'] = df['points'].rolling(window=7, min_periods=3).mean()
            df['week_std'] = df['points'].rolling(window=7, min_periods=3).std()
            df['week_cv'] = df['week_std'] / df['week_mean']
            df['z_score'] = (df['points'] - df['week_mean']) / df['week_std']

            return df

        finally:
            session.close()

    def identify_correlation_opportunities(
        self,
        player_ids: List[int],
        stats_type: str = "batting"
    ) -> pd.DataFrame:
        """
        Identify players whose performances tend to correlate (same team stacking).

        Args:
            player_ids: List of player IDs to analyze
            stats_type: 'batting' or 'pitching'

        Returns:
            Correlation matrix DataFrame
        """
        if len(player_ids) < 2:
            return pd.DataFrame()

        # Build matrix of player points by game
        player_data = {}

        for player_id in player_ids:
            games = self.db.get_player_games(player_id, stats_type)
            player_data[player_id] = {pg.game_pk: pg.dk_points for pg in games}

        # Find common games
        all_game_pks = set()
        for games in player_data.values():
            all_game_pks.update(games.keys())

        # Create matrix
        matrix_data = {}
        for player_id in player_ids:
            matrix_data[player_id] = [
                player_data[player_id].get(game_pk, 0)
                for game_pk in sorted(all_game_pks)
            ]

        df = pd.DataFrame(matrix_data)

        # Calculate correlation
        corr_matrix = df.corr()

        return corr_matrix


if __name__ == "__main__":
    # Example usage
    from ..database import DatabaseManager

    db = DatabaseManager()
    analyzer = VolatilityAnalyzer(db)

    # Analyze all batting players
    # analyzed = analyzer.analyze_all_players("batting", min_games=20)
    # print(f"Analyzed {len(analyzed)} players")
