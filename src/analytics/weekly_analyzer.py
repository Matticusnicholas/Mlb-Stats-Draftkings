"""
Weekly/Rolling window analysis for DraftKings Best Ball.

Analyzes 7-day rolling windows and multi-game tear streaks.
"""
import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional
from datetime import datetime, timedelta
import logging

from ..database.models import PlayerGame, Game
from ..database.db_manager import DatabaseManager

logger = logging.getLogger(__name__)


class WeeklyAnalyzer:
    """
    Analyzes weekly performance and hot streaks for Best Ball optimization.
    """

    def __init__(self, db_manager: DatabaseManager):
        """
        Initialize weekly analyzer.

        Args:
            db_manager: Database manager instance
        """
        self.db = db_manager

    def get_player_rolling_windows(
        self,
        player_id: int,
        stats_type: str = "batting",
        window_days: int = 7
    ) -> pd.DataFrame:
        """
        Calculate rolling window statistics for a player.

        Args:
            player_id: MLB player ID
            stats_type: 'batting' or 'pitching'
            window_days: Size of rolling window in days

        Returns:
            DataFrame with rolling window stats
        """
        player_games = self.db.get_player_games(player_id, stats_type)

        if not player_games:
            return pd.DataFrame()

        # Build DataFrame with dates and points
        session = self.db.get_session()
        try:
            data = []
            for pg in player_games:
                game = session.query(Game).filter_by(game_pk=pg.game_pk).first()
                if game:
                    data.append({
                        'date': game.game_date.date(),
                        'points': pg.dk_points,
                        'game_pk': pg.game_pk
                    })

            if not data:
                return pd.DataFrame()

            df = pd.DataFrame(data)
            df = df.sort_values('date').reset_index(drop=True)

            # Calculate rolling 7-day sums
            # For each date, sum all games in the previous 7 days
            rolling_sums = []

            for i, row in df.iterrows():
                end_date = row['date']
                start_date = end_date - timedelta(days=window_days-1)

                # Get all games in this 7-day window
                window_games = df[
                    (df['date'] >= start_date) &
                    (df['date'] <= end_date)
                ]

                rolling_sums.append({
                    'end_date': end_date,
                    'start_date': start_date,
                    'window_points': window_games['points'].sum(),
                    'games_in_window': len(window_games),
                    'avg_per_game': window_games['points'].mean() if len(window_games) > 0 else 0
                })

            rolling_df = pd.DataFrame(rolling_sums)

            return rolling_df

        finally:
            session.close()

    def calculate_tear_metrics(
        self,
        player_id: int,
        stats_type: str = "batting",
        threshold_percentile: float = 75
    ) -> Dict:
        """
        Calculate TEAR metrics - likelihood of multi-game hot streaks.

        A "tear" is consecutive games above a threshold (75th percentile by default).

        Args:
            player_id: MLB player ID
            stats_type: 'batting' or 'pitching'
            threshold_percentile: Percentile to define "hot" game

        Returns:
            Dictionary with TEAR2, TEAR3, TEAR4, TEAR5 metrics
        """
        player_games = self.db.get_player_games(player_id, stats_type)

        if len(player_games) < 10:
            return {
                'tear2_rate': 0.0,
                'tear3_rate': 0.0,
                'tear4_rate': 0.0,
                'tear5_rate': 0.0,
                'tear2_count': 0,
                'tear3_count': 0,
                'tear4_count': 0,
                'tear5_count': 0,
                'longest_tear': 0,
                'tear_threshold': 0.0
            }

        # Get games in chronological order
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

            games_with_dates.sort(key=lambda x: x['date'])
            points = [g['points'] for g in games_with_dates]

            # Define threshold for "hot" game
            threshold = np.percentile(points, threshold_percentile)

            # Find consecutive hot streaks
            current_streak = 0
            tear_lengths = []

            for pts in points:
                if pts >= threshold:
                    current_streak += 1
                else:
                    if current_streak >= 2:  # Only count streaks of 2+
                        tear_lengths.append(current_streak)
                    current_streak = 0

            # Don't forget final streak
            if current_streak >= 2:
                tear_lengths.append(current_streak)

            # Count tears of each length
            tear2_count = sum(1 for t in tear_lengths if t >= 2)
            tear3_count = sum(1 for t in tear_lengths if t >= 3)
            tear4_count = sum(1 for t in tear_lengths if t >= 4)
            tear5_count = sum(1 for t in tear_lengths if t >= 5)

            # Calculate rates (per 100 games)
            games_played = len(points)
            rate_multiplier = 100 / games_played if games_played > 0 else 0

            return {
                'tear2_rate': round(tear2_count * rate_multiplier, 2),
                'tear3_rate': round(tear3_count * rate_multiplier, 2),
                'tear4_rate': round(tear4_count * rate_multiplier, 2),
                'tear5_rate': round(tear5_count * rate_multiplier, 2),
                'tear2_count': tear2_count,
                'tear3_count': tear3_count,
                'tear4_count': tear4_count,
                'tear5_count': tear5_count,
                'longest_tear': max(tear_lengths) if tear_lengths else 0,
                'tear_threshold': round(threshold, 2)
            }

        finally:
            session.close()

    def calculate_weekly_volatility(
        self,
        player_id: int,
        stats_type: str = "batting",
        min_games: int = 10
    ) -> Optional[Dict]:
        """
        Calculate comprehensive weekly volatility metrics.

        Args:
            player_id: MLB player ID
            stats_type: 'batting' or 'pitching'
            min_games: Minimum games required

        Returns:
            Dictionary of weekly volatility metrics
        """
        player_games = self.db.get_player_games(player_id, stats_type)

        if len(player_games) < min_games:
            return None

        # Get rolling 7-day windows
        rolling_df = self.get_player_rolling_windows(player_id, stats_type, window_days=7)

        if rolling_df.empty or len(rolling_df) < 5:
            return None

        window_points = rolling_df['window_points'].values

        metrics = {}

        # Basic weekly stats
        metrics['total_windows'] = len(rolling_df)
        metrics['mean_week_points'] = float(np.mean(window_points))
        metrics['median_week_points'] = float(np.median(window_points))
        metrics['std_week_points'] = float(np.std(window_points, ddof=1))

        # Best weeks
        sorted_weeks = np.sort(window_points)[::-1]
        metrics['best_week'] = float(sorted_weeks[0]) if len(sorted_weeks) > 0 else 0
        metrics['top3_weeks_avg'] = float(np.mean(sorted_weeks[:3])) if len(sorted_weeks) >= 3 else 0
        metrics['top5_weeks_avg'] = float(np.mean(sorted_weeks[:5])) if len(sorted_weeks) >= 5 else 0

        # Percentiles
        metrics['week_percentile_75'] = float(np.percentile(window_points, 75))
        metrics['week_percentile_90'] = float(np.percentile(window_points, 90))
        metrics['week_percentile_95'] = float(np.percentile(window_points, 95))

        # Boom weeks (define as 90th percentile+)
        boom_threshold = metrics['week_percentile_90']
        boom_weeks = np.sum(window_points >= boom_threshold)
        metrics['boom_week_rate'] = float(boom_weeks / len(window_points) * 100)
        metrics['boom_week_count'] = int(boom_weeks)

        # High-scoring weeks (40+ for hitters, 50+ for pitchers)
        high_threshold = 40 if stats_type == "batting" else 50
        high_weeks = np.sum(window_points >= high_threshold)
        metrics['high_week_rate'] = float(high_weeks / len(window_points) * 100)
        metrics['high_week_count'] = int(high_weeks)

        # Top weeks concentration
        top5_sum = float(np.sum(sorted_weeks[:5])) if len(sorted_weeks) >= 5 else float(np.sum(sorted_weeks))
        total_sum = float(np.sum(window_points))
        metrics['top5_weeks_pct'] = (top5_sum / total_sum * 100) if total_sum > 0 else 0

        # USEFUL points metric - only count weeks worthy of starting lineup
        # Threshold based on top 100-150 players' weekly scores (70th percentile)
        # This represents "starting worthy" performance in a competitive league
        useful_threshold = self._get_useful_threshold(stats_type)
        useful_weeks_mask = window_points >= useful_threshold
        useful_weeks = window_points[useful_weeks_mask]

        metrics['useful_threshold'] = float(useful_threshold)
        metrics['useful_points_total'] = float(np.sum(useful_weeks)) if len(useful_weeks) > 0 else 0
        metrics['useful_weeks_count'] = int(np.sum(useful_weeks_mask))
        metrics['useful_weeks_pct'] = float(np.sum(useful_weeks_mask) / len(window_points) * 100) if len(window_points) > 0 else 0

        # Wasted points (points from non-starting-worthy weeks)
        wasted_weeks = window_points[~useful_weeks_mask]
        metrics['wasted_points'] = float(np.sum(wasted_weeks)) if len(wasted_weeks) > 0 else 0
        metrics['wasted_weeks_count'] = int(len(wasted_weeks))

        # Efficiency: what % of total points came from starting-worthy weeks
        metrics['useful_efficiency'] = float((metrics['useful_points_total'] / total_sum * 100)) if total_sum > 0 else 0

        # Concentration: average points per useful week (spike-iness of useful production)
        metrics['useful_points_per_week'] = float(metrics['useful_points_total'] / metrics['useful_weeks_count']) if metrics['useful_weeks_count'] > 0 else 0

        # TEAR metrics
        tear_metrics = self.calculate_tear_metrics(player_id, stats_type)
        metrics.update(tear_metrics)

        # Weekly consistency score (inverse - lower = more volatile = better for best ball)
        cv = metrics['std_week_points'] / metrics['mean_week_points'] if metrics['mean_week_points'] > 0 else 0
        metrics['weekly_cv'] = float(cv)

        # Best Ball Score (composite metric for weekly formats)
        metrics['bestball_score'] = self._calculate_bestball_score(metrics)

        return metrics

    def _get_useful_threshold(self, stats_type: str = "batting") -> float:
        """
        Calculate league-wide "starting worthy" threshold.

        Gets top 100-150 players' weekly scores and uses 70th percentile
        as the threshold for a "useful" (starting-worthy) week.

        Args:
            stats_type: 'batting' or 'pitching'

        Returns:
            Weekly point threshold for starting-worthy performance
        """
        # Cache threshold to avoid recalculating for every player
        cache_key = f'_useful_threshold_{stats_type}'
        if hasattr(self, cache_key):
            return getattr(self, cache_key)

        # Get top players by game count
        session = self.db.get_session()
        try:
            from sqlalchemy import func
            from ..database.models import PlayerGame

            # Get players with most games (top ~150)
            top_players = session.query(
                PlayerGame.player_id,
                func.count(PlayerGame.game_pk).label('game_count')
            ).filter(
                PlayerGame.stats_type == stats_type
            ).group_by(
                PlayerGame.player_id
            ).having(
                func.count(PlayerGame.game_pk) >= 20
            ).order_by(
                func.count(PlayerGame.game_pk).desc()
            ).limit(150).all()

            if not top_players:
                # Fallback if no data
                return 25.0 if stats_type == "batting" else 30.0

            # Collect all weekly scores from these top players
            all_weekly_scores = []

            for player_id, _ in top_players:
                rolling_df = self.get_player_rolling_windows(player_id, stats_type, window_days=7)
                if not rolling_df.empty:
                    all_weekly_scores.extend(rolling_df['window_points'].values)

            if not all_weekly_scores:
                # Fallback
                return 25.0 if stats_type == "batting" else 30.0

            # Use 70th percentile as "starting worthy" threshold
            # This means if your week is in top 30% of all weeks, it's useful
            threshold = float(np.percentile(all_weekly_scores, 70))

            # Cache for this instance
            setattr(self, cache_key, threshold)

            logger.info(f"Calculated USEFUL threshold for {stats_type}: {threshold:.2f} pts (70th percentile)")

            return threshold

        finally:
            session.close()

    def _calculate_bestball_score(self, metrics: Dict) -> float:
        """
        Calculate a composite Best Ball score (0-100).
        Higher = better for best ball formats.

        Heavily weights ceiling weeks and tear potential.

        Args:
            metrics: Dictionary of weekly metrics

        Returns:
            Best Ball score (0-100)
        """
        # Best week score (normalized)
        best_week_score = min(100, metrics['best_week'] * 1.5)

        # Top weeks average
        top3_score = min(100, metrics['top3_weeks_avg'] * 2)

        # Boom week rate (how often they have monster weeks)
        boom_score = min(100, metrics['boom_week_rate'] * 5)

        # TEAR3+ rate (3+ game hot streaks)
        tear_score = min(100, metrics['tear3_rate'] * 5)

        # Top 5 weeks concentration (higher = more spike-y)
        concentration_score = min(100, metrics['top5_weeks_pct'])

        # Weighted combination (emphasis on ceiling and tears)
        bestball_score = (
            best_week_score * 0.25 +     # Best week ever
            top3_score * 0.20 +           # Typical ceiling weeks
            boom_score * 0.20 +           # Boom week frequency
            tear_score * 0.20 +           # Multi-game tear ability
            concentration_score * 0.15    # Spike concentration
        )

        return round(bestball_score, 2)

    def analyze_all_players_weekly(
        self,
        stats_type: str = "batting",
        min_games: int = 20
    ) -> List[int]:
        """
        Analyze weekly metrics for all eligible players.

        Args:
            stats_type: 'batting' or 'pitching'
            min_games: Minimum games required

        Returns:
            List of player IDs analyzed
        """
        session = self.db.get_session()
        try:
            from sqlalchemy import func

            # Get all players with sufficient games
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
            logger.info(f"Analyzing weekly stats for {len(player_ids)} players")

            analyzed = []
            for player_id in player_ids:
                try:
                    metrics = self.calculate_weekly_volatility(player_id, stats_type, min_games)
                    if metrics:
                        # Store in database (we'll need to add a table for this)
                        # For now, just track that we analyzed them
                        analyzed.append(player_id)

                        # Could save to a new WeeklyVolatility table
                        # self.db.save_weekly_volatility(player_id, stats_type, metrics)

                except Exception as e:
                    logger.error(f"Error analyzing weekly for player {player_id}: {e}")

            logger.info(f"Successfully analyzed {len(analyzed)} players for weekly metrics")
            return analyzed

        finally:
            session.close()

    def get_top_bestball_players(
        self,
        stats_type: str = "batting",
        min_games: int = 20,
        limit: int = 50,
        progress_callback=None
    ) -> List[Dict]:
        """
        Get top players for best ball based on weekly analysis.

        Args:
            stats_type: 'batting' or 'pitching'
            min_games: Minimum games required
            limit: Number of players to return
            progress_callback: Optional callback function(current, total, player_name)

        Returns:
            List of player dictionaries with weekly metrics
        """
        session = self.db.get_session()
        try:
            from ..database.models import Player
            from sqlalchemy import func

            # Get all eligible players
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
            total_players = len(player_ids)

            # Limit calculation to reasonable number for performance
            # If too many players, sample or limit
            if total_players > 300:
                logger.info(f"Found {total_players} players, limiting to top 300 for performance")
                # Get players with most games first (likely to be better)
                player_game_counts = session.query(
                    PlayerGame.player_id,
                    func.count(PlayerGame.id).label('game_count')
                ).filter_by(
                    stats_type=stats_type
                ).group_by(
                    PlayerGame.player_id
                ).having(
                    func.count(PlayerGame.id) >= min_games
                ).order_by(
                    func.count(PlayerGame.id).desc()
                ).limit(300).all()

                player_ids = [pid for pid, count in player_game_counts]
                total_players = len(player_ids)

            logger.info(f"Calculating Best Ball metrics for {total_players} players...")

            # Calculate weekly metrics for each
            player_scores = []

            for idx, player_id in enumerate(player_ids, 1):
                try:
                    if progress_callback:
                        player = session.query(Player).filter_by(player_id=player_id).first()
                        player_name = player.player_name if player else str(player_id)
                        progress_callback(idx, total_players, player_name)

                    metrics = self.calculate_weekly_volatility(player_id, stats_type, min_games)

                    if metrics and metrics['bestball_score'] > 0:
                        if not progress_callback:  # Only query if we haven't already
                            player = session.query(Player).filter_by(player_id=player_id).first()

                        if player:
                            player_scores.append({
                                'player_id': player_id,
                                'player_name': player.player_name,
                                'bestball_score': metrics['bestball_score'],
                                'best_week': metrics['best_week'],
                                'top3_weeks_avg': metrics['top3_weeks_avg'],
                                'boom_week_rate': metrics['boom_week_rate'],
                                'tear3_rate': metrics['tear3_rate'],
                                'tear4_rate': metrics['tear4_rate'],
                                'longest_tear': metrics['longest_tear'],
                                'mean_week_points': metrics['mean_week_points']
                            })

                except Exception as e:
                    logger.error(f"Error processing player {player_id}: {e}")
                    continue

            # Sort by bestball_score
            player_scores.sort(key=lambda x: x['bestball_score'], reverse=True)

            return player_scores[:limit]

        finally:
            session.close()


if __name__ == "__main__":
    # Example usage
    from ..database import DatabaseManager

    db = DatabaseManager()
    analyzer = WeeklyAnalyzer(db)

    # Example: Get top best ball players
    # top_players = analyzer.get_top_bestball_players("batting", min_games=20, limit=25)
    # for i, p in enumerate(top_players, 1):
    #     print(f"{i}. {p['player_name']}: BB Score={p['bestball_score']:.1f}, Best Week={p['best_week']:.1f}")
