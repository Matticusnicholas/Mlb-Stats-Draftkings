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
from ..utils.multi_scoring import MultiScoringCalculator

logger = logging.getLogger(__name__)


class WeeklyAnalyzer:
    """
    Analyzes weekly performance and hot streaks for Best Ball optimization.
    """

    def __init__(self, db_manager: DatabaseManager, scoring_system: str = 'draftkings'):
        """
        Initialize weekly analyzer.

        Args:
            db_manager: Database manager instance
            scoring_system: Scoring system to use ('draftkings', 'underdog', 'drafters')
        """
        self.db = db_manager
        self.scoring_system = scoring_system
        self.multi_scoring = MultiScoringCalculator()
        logger.info(f"WeeklyAnalyzer initialized with scoring system: {scoring_system}")

    def _get_points(self, player_game) -> float:
        """
        Get points for a player game using current scoring system.
        Uses cached points from database for instant switching between platforms.

        Args:
            player_game: PlayerGame object

        Returns:
            Fantasy points for this game
        """
        # Use cached points from database (pre-calculated for all scoring systems)
        if self.scoring_system == 'draftkings':
            return player_game.dk_points
        elif self.scoring_system == 'underdog':
            # Use cached underdog points if available, otherwise recalculate
            if player_game.underdog_points is not None:
                return player_game.underdog_points
            else:
                return self.multi_scoring.recalculate_points(player_game, self.scoring_system)
        elif self.scoring_system == 'drafters':
            # Use cached drafters points if available, otherwise recalculate
            if player_game.drafters_points is not None:
                return player_game.drafters_points
            else:
                return self.multi_scoring.recalculate_points(player_game, self.scoring_system)
        else:
            # Fallback for any other scoring system
            return self.multi_scoring.recalculate_points(player_game, self.scoring_system)

    def get_player_sequential_weeks(
        self,
        player_id: int,
        stats_type: str = "batting",
        days_per_week: int = 7
    ) -> pd.DataFrame:
        """
        Get NON-OVERLAPPING sequential weekly totals for a player.

        Divides the season into sequential 7-day chunks (like actual weeks).
        Each day appears in exactly ONE week - no overlap.

        Args:
            player_id: MLB player ID
            stats_type: 'batting' or 'pitching'
            days_per_week: Days per week (default 7)

        Returns:
            DataFrame with columns: week_num, start_date, end_date, week_points, games_in_week
        """
        session = self.db.get_session()
        try:
            player_games = self.db.get_player_games(player_id, stats_type)

            if len(player_games) == 0:
                return pd.DataFrame()

            # Get game data with dates
            from ..database.models import Game
            data = []
            for pg in player_games:
                game = session.query(Game).filter(Game.game_pk == pg.game_pk).first()
                if game:
                    # Use dynamic scoring
                    points = self._get_points(pg)
                    data.append({
                        'date': game.game_date.date(),
                        'points': points,
                        'game_pk': pg.game_pk
                    })

            if not data:
                return pd.DataFrame()

            df = pd.DataFrame(data)
            df = df.sort_values('date').reset_index(drop=True)

            # Find season start and divide into sequential weeks
            season_start = df['date'].min()
            season_end = df['date'].max()

            # Create non-overlapping weekly buckets
            weeks = []
            current_week_start = season_start
            week_num = 1

            while current_week_start <= season_end:
                current_week_end = current_week_start + timedelta(days=days_per_week-1)

                # Get all games in this specific week
                week_games = df[
                    (df['date'] >= current_week_start) &
                    (df['date'] <= current_week_end)
                ]

                # Only add weeks with at least one game
                if len(week_games) > 0:
                    weeks.append({
                        'week_num': week_num,
                        'start_date': current_week_start,
                        'end_date': current_week_end,
                        'week_points': week_games['points'].sum(),
                        'games_in_week': len(week_games),
                        'avg_per_game': week_games['points'].mean()
                    })

                # Move to next non-overlapping week
                current_week_start = current_week_end + timedelta(days=1)
                week_num += 1

            return pd.DataFrame(weeks)

        finally:
            session.close()

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
                    # Use dynamic scoring
                    points = self._get_points(pg)
                    data.append({
                        'date': game.game_date.date(),
                        'points': points,
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
                    # Use dynamic scoring
                    points = self._get_points(pg)
                    games_with_dates.append({
                        'date': game.game_date,
                        'points': points
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
        # Uses NON-OVERLAPPING sequential weeks (not rolling windows)
        # Threshold based on top 100-150 players' weekly scores (70th percentile)
        # This represents "starting worthy" performance in a competitive league
        sequential_weeks_df = self.get_player_sequential_weeks(player_id, stats_type, days_per_week=7)

        if not sequential_weeks_df.empty:
            sequential_week_points = sequential_weeks_df['week_points'].values
            useful_threshold = self._get_useful_threshold(stats_type)
            useful_weeks_mask = sequential_week_points >= useful_threshold
            useful_weeks = sequential_week_points[useful_weeks_mask]

            metrics['useful_threshold'] = float(useful_threshold)
            metrics['useful_points_total'] = float(np.sum(useful_weeks)) if len(useful_weeks) > 0 else 0
            metrics['useful_weeks_count'] = int(np.sum(useful_weeks_mask))
            metrics['useful_weeks_pct'] = float(np.sum(useful_weeks_mask) / len(sequential_week_points) * 100) if len(sequential_week_points) > 0 else 0

            # Wasted points (points from non-starting-worthy weeks)
            wasted_weeks = sequential_week_points[~useful_weeks_mask]
            metrics['wasted_points'] = float(np.sum(wasted_weeks)) if len(wasted_weeks) > 0 else 0
            metrics['wasted_weeks_count'] = int(len(wasted_weeks))

            # Efficiency: what % of total points came from starting-worthy weeks
            metrics['useful_efficiency'] = float((metrics['useful_points_total'] / total_sum * 100)) if total_sum > 0 else 0

            # Concentration: average points per useful week (spike-iness of useful production)
            metrics['useful_points_per_week'] = float(metrics['useful_points_total'] / metrics['useful_weeks_count']) if metrics['useful_weeks_count'] > 0 else 0
        else:
            # No sequential weeks data
            metrics['useful_threshold'] = 0.0
            metrics['useful_points_total'] = 0.0
            metrics['useful_weeks_count'] = 0
            metrics['useful_weeks_pct'] = 0.0
            metrics['wasted_points'] = 0.0
            metrics['wasted_weeks_count'] = 0
            metrics['useful_efficiency'] = 0.0
            metrics['useful_points_per_week'] = 0.0

        # TEAR metrics
        tear_metrics = self.calculate_tear_metrics(player_id, stats_type)
        metrics.update(tear_metrics)

        # Pitcher-specific metrics (for pitchers only)
        if stats_type == "pitching":
            # Start Levels (elite start clustering)
            start_levels = self.calculate_start_levels(player_id, stats_type)
            metrics.update(start_levels)

            # Workhorse Metrics (innings-eating reliability)
            workhorse_metrics = self.calculate_workhorse_metrics(player_id, stats_type)
            metrics.update(workhorse_metrics)

        # Weekly consistency score (inverse - lower = more volatile = better for best ball)
        cv = metrics['std_week_points'] / metrics['mean_week_points'] if metrics['mean_week_points'] > 0 else 0
        metrics['weekly_cv'] = float(cv)

        # Best Ball Score (composite metric for weekly formats)
        metrics['bestball_score'] = self._calculate_bestball_score(metrics)

        return metrics

    def calculate_workhorse_metrics(
        self,
        player_id: int,
        stats_type: str = "pitching",
        min_ip_for_start: float = 3.0
    ) -> Dict:
        """
        Calculate workhorse metrics for starting pitchers.

        Focuses on innings-eating reliability and durability - critical for
        best ball formats where you want consistent weekly innings from your
        pitcher slots (floor play vs. hitter ceiling plays).

        Args:
            player_id: MLB player ID
            stats_type: Should be 'pitching'
            min_ip_for_start: Minimum IP to count as a start (default 3.0)

        Returns:
            Dictionary with workhorse metrics:
            - total_starts: Games with min_ip_for_start+ innings
            - avg_ip_per_start: Average innings per start
            - total_innings: Total innings pitched in starts
            - ip_consistency: StdDev of IP (lower = more consistent)
            - quality_start_rate: % of starts with 6+ IP
            - deep_start_rate: % of starts with 7+ IP
            - floor_points: 25th percentile DK points per start
            - median_points: Median DK points per start
            - workhorse_score: Composite 0-100 score for innings-eating ability
        """
        player_games = self.db.get_player_games(player_id, stats_type)

        # Filter to actual starts (3+ IP)
        starts = [pg for pg in player_games if pg.innings_pitched and pg.innings_pitched >= min_ip_for_start]

        if len(starts) < 5:
            return {
                'total_starts': len(starts),
                'avg_ip_per_start': 0.0,
                'total_innings': 0.0,
                'ip_consistency': 0.0,
                'quality_start_rate': 0.0,
                'deep_start_rate': 0.0,
                'floor_points': 0.0,
                'median_points': 0.0,
                'workhorse_score': 0.0
            }

        # Gather stats from starts using current scoring system
        innings = np.array([pg.innings_pitched for pg in starts])
        points = np.array([self._get_points(pg) for pg in starts])

        total_starts = len(starts)
        total_innings = float(np.sum(innings))
        avg_ip = float(np.mean(innings))
        ip_std = float(np.std(innings))

        # Quality starts (6+ IP)
        quality_starts = np.sum(innings >= 6.0)
        quality_start_rate = float(quality_starts / total_starts * 100) if total_starts > 0 else 0.0

        # Deep starts (7+ IP)
        deep_starts = np.sum(innings >= 7.0)
        deep_start_rate = float(deep_starts / total_starts * 100) if total_starts > 0 else 0.0

        # Floor and median DK points
        floor_points = float(np.percentile(points, 25))
        median_points = float(np.median(points))

        # Calculate workhorse score (0-100)
        # Components:
        # 1. Durability (30%): Total starts / 30 (assuming ~30 starts is elite)
        # 2. Innings per start (30%): (avg_ip - 4) / 3 (scale 4-7 IP to 0-1)
        # 3. Quality start rate (20%)
        # 4. Consistency (10%): Inverse of coefficient of variation
        # 5. Floor reliability (10%): floor_points / 20 (20+ pts is solid)

        durability_score = min(100, (total_starts / 30.0) * 100)
        ip_score = min(100, max(0, ((avg_ip - 4.0) / 3.0) * 100))
        qs_score = quality_start_rate  # Already 0-100

        # Consistency: Lower CV is better (CV = std/mean)
        cv = (ip_std / avg_ip) if avg_ip > 0 else 1.0
        consistency_score = max(0, 100 - (cv * 100))  # Invert so lower CV = higher score

        floor_score = min(100, (floor_points / 20.0) * 100)

        workhorse_score = (
            durability_score * 0.30 +
            ip_score * 0.30 +
            qs_score * 0.20 +
            consistency_score * 0.10 +
            floor_score * 0.10
        )

        return {
            'total_starts': int(total_starts),
            'avg_ip_per_start': float(avg_ip),
            'total_innings': float(total_innings),
            'ip_consistency': float(ip_std),
            'quality_start_rate': float(quality_start_rate),
            'deep_start_rate': float(deep_start_rate),
            'floor_points': float(floor_points),
            'median_points': float(median_points),
            'workhorse_score': float(workhorse_score)
        }

    def calculate_start_levels(
        self,
        player_id: int,
        stats_type: str = "pitching"
    ) -> Dict:
        """
        Calculate pitcher start levels - clustering of elite starts.

        Level 1: Top 30% of starts (70th percentile+)
        Level 2: Top 20% of starts (80th percentile+)
        Level 3: Top 10% of starts (90th percentile+)

        Args:
            player_id: MLB player ID
            stats_type: 'batting' or 'pitching' (primarily for pitchers)

        Returns:
            Dictionary with L1/L2/L3 start counts, rates, and average points
        """
        player_games = self.db.get_player_games(player_id, stats_type)

        if len(player_games) < 5:
            return {
                'level1_starts': 0,
                'level2_starts': 0,
                'level3_starts': 0,
                'level1_rate': 0.0,
                'level2_rate': 0.0,
                'level3_rate': 0.0,
                'level1_avg_pts': 0.0,
                'level2_avg_pts': 0.0,
                'level3_avg_pts': 0.0
            }

        # Get all points from games using current scoring system
        points = np.array([self._get_points(pg) for pg in player_games])

        # Calculate percentile thresholds
        p70 = np.percentile(points, 70)  # Level 1: Top 30%
        p80 = np.percentile(points, 80)  # Level 2: Top 20%
        p90 = np.percentile(points, 90)  # Level 3: Top 10%

        # Count starts at each level
        level1_mask = points >= p70
        level2_mask = points >= p80
        level3_mask = points >= p90

        level1_starts = points[level1_mask]
        level2_starts = points[level2_mask]
        level3_starts = points[level3_mask]

        total_starts = len(points)

        return {
            'level1_starts': int(np.sum(level1_mask)),
            'level2_starts': int(np.sum(level2_mask)),
            'level3_starts': int(np.sum(level3_mask)),
            'level1_rate': float(np.sum(level1_mask) / total_starts * 100) if total_starts > 0 else 0.0,
            'level2_rate': float(np.sum(level2_mask) / total_starts * 100) if total_starts > 0 else 0.0,
            'level3_rate': float(np.sum(level3_mask) / total_starts * 100) if total_starts > 0 else 0.0,
            'level1_avg_pts': float(np.mean(level1_starts)) if len(level1_starts) > 0 else 0.0,
            'level2_avg_pts': float(np.mean(level2_starts)) if len(level2_starts) > 0 else 0.0,
            'level3_avg_pts': float(np.mean(level3_starts)) if len(level3_starts) > 0 else 0.0,
            'level1_threshold': float(p70),
            'level2_threshold': float(p80),
            'level3_threshold': float(p90)
        }

    def _get_useful_threshold(self, stats_type: str = "batting", player_id_list: List[int] = None) -> float:
        """
        Calculate league-wide "starting worthy" threshold for WEEKLY performance.

        Uses 70th percentile of NON-OVERLAPPING sequential weekly scores from top players.

        Args:
            stats_type: 'batting' or 'pitching'
            player_id_list: Optional list of player IDs to use (from get_top_bestball_players)

        Returns:
            Weekly point threshold for starting-worthy performance
        """
        # Cache threshold to avoid recalculating for every player
        cache_key = f'_useful_threshold_{stats_type}'
        if hasattr(self, cache_key):
            return getattr(self, cache_key)

        session = self.db.get_session()
        try:
            from sqlalchemy import func
            from ..database.models import PlayerGame

            # If we have a player list from get_top_bestball_players, use it
            # Otherwise get top 50 players by game count (much smaller subset for speed)
            if player_id_list:
                player_ids = player_id_list[:50]  # Use first 50 from the list
            else:
                top_players = session.query(
                    PlayerGame.player_id
                ).filter(
                    PlayerGame.stats_type == stats_type
                ).group_by(
                    PlayerGame.player_id
                ).having(
                    func.count(PlayerGame.game_pk) >= 20
                ).order_by(
                    func.count(PlayerGame.game_pk).desc()
                ).limit(50).all()

                if not top_players:
                    logger.warning(f"No players found for USEFUL threshold, using fallback")
                    return 35.0 if stats_type == "batting" else 40.0

                player_ids = [p[0] for p in top_players]

            # Collect SEQUENTIAL weekly scores from these players (non-overlapping)
            all_weekly_scores = []

            for player_id in player_ids:
                sequential_df = self.get_player_sequential_weeks(player_id, stats_type, days_per_week=7)
                if not sequential_df.empty:
                    all_weekly_scores.extend(sequential_df['week_points'].values.tolist())

            if not all_weekly_scores or len(all_weekly_scores) < 10:
                logger.warning(f"Insufficient weekly data for threshold, using fallback")
                return 35.0 if stats_type == "batting" else 40.0

            # Use 70th percentile of weekly totals
            # This represents a "starting worthy" week
            threshold = float(np.percentile(all_weekly_scores, 70))

            # Sanity check - weekly totals should be higher than single game
            if threshold < 15.0:
                logger.warning(f"Calculated weekly threshold too low ({threshold:.2f}), using minimum")
                threshold = 30.0 if stats_type == "batting" else 35.0

            # Cache for this instance
            setattr(self, cache_key, threshold)

            logger.info(f"Calculated USEFUL threshold for {stats_type}: {threshold:.2f} pts/week (70th percentile from {len(all_weekly_scores)} weekly windows)")

            return threshold

        except Exception as e:
            logger.error(f"Error calculating USEFUL threshold: {e}")
            return 35.0 if stats_type == "batting" else 40.0

        finally:
            session.close()

    def _calculate_bestball_score(self, metrics: Dict) -> float:
        """
        Calculate a composite Best Ball score (0-100).
        Higher = better for best ball formats.

        Emphasizes USEFUL metrics (starting-worthy production) over single-week spikes.
        For 13 batter / 7 pitcher leagues, consistency matters more than one big week.

        Args:
            metrics: Dictionary of weekly metrics

        Returns:
            Best Ball score (0-100)
        """
        # USEFUL metrics - concentration of starting-worthy production
        # When they're good, HOW good are they?
        useful_concentration = min(100, metrics.get('useful_points_per_week', 0) * 1.2)

        # What % of their weeks are actually starting-worthy?
        useful_frequency = min(100, metrics.get('useful_weeks_pct', 0) * 1.5)

        # Boom week rate (how often they have monster weeks)
        boom_score = min(100, metrics['boom_week_rate'] * 5)

        # TEAR3+ rate (3+ game hot streaks - creates multiple good weeks)
        tear_score = min(100, metrics['tear3_rate'] * 5)

        # Top weeks average (typical ceiling when they're hot)
        top3_score = min(100, metrics['top3_weeks_avg'] * 2)

        # Top 5 weeks concentration (spike-iness)
        concentration_score = min(100, metrics['top5_weeks_pct'])

        # Best single week (nice to have, but not critical)
        best_week_score = min(100, metrics['best_week'] * 1.5)

        # Weighted combination - USEFUL and boom/tear frequency dominate
        bestball_score = (
            useful_concentration * 0.25 +    # Pts per useful week (when good, how good?)
            useful_frequency * 0.20 +        # % of weeks that are starting-worthy
            boom_score * 0.20 +              # Elite week frequency
            tear_score * 0.15 +              # Multi-game hot streak ability
            top3_score * 0.10 +              # Typical ceiling weeks
            concentration_score * 0.05 +     # General spike-iness
            best_week_score * 0.05           # Best week ever (minimal weight)
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

            # Pre-calculate USEFUL threshold once for all players (efficiency optimization)
            logger.info(f"Pre-calculating USEFUL threshold for {stats_type}...")
            _ = self._get_useful_threshold(stats_type, player_ids)

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
                            player_dict = {
                                'player_id': player_id,
                                'player_name': player.player_name,
                                'bestball_score': metrics['bestball_score'],
                                'best_week': metrics['best_week'],
                                'top3_weeks_avg': metrics['top3_weeks_avg'],
                                'boom_week_rate': metrics['boom_week_rate'],
                                'tear3_rate': metrics['tear3_rate'],
                                'tear4_rate': metrics['tear4_rate'],
                                'longest_tear': metrics['longest_tear'],
                                'mean_week_points': metrics['mean_week_points'],
                                # USEFUL metrics
                                'useful_points_total': metrics.get('useful_points_total', 0),
                                'useful_weeks_count': metrics.get('useful_weeks_count', 0),
                                'useful_weeks_pct': metrics.get('useful_weeks_pct', 0),
                                'useful_points_per_week': metrics.get('useful_points_per_week', 0),
                                'useful_efficiency': metrics.get('useful_efficiency', 0),
                                'useful_threshold': metrics.get('useful_threshold', 0),
                                'wasted_points': metrics.get('wasted_points', 0)
                            }

                            # Add pitcher-specific metrics for pitchers
                            if stats_type == "pitching":
                                player_dict.update({
                                    # Start Levels
                                    'level1_starts': metrics.get('level1_starts', 0),
                                    'level2_starts': metrics.get('level2_starts', 0),
                                    'level3_starts': metrics.get('level3_starts', 0),
                                    'level1_rate': metrics.get('level1_rate', 0.0),
                                    'level2_rate': metrics.get('level2_rate', 0.0),
                                    'level3_rate': metrics.get('level3_rate', 0.0),
                                    'level1_avg_pts': metrics.get('level1_avg_pts', 0.0),
                                    'level2_avg_pts': metrics.get('level2_avg_pts', 0.0),
                                    'level3_avg_pts': metrics.get('level3_avg_pts', 0.0),
                                    # Workhorse Metrics
                                    'total_starts': metrics.get('total_starts', 0),
                                    'avg_ip_per_start': metrics.get('avg_ip_per_start', 0.0),
                                    'total_innings': metrics.get('total_innings', 0.0),
                                    'ip_consistency': metrics.get('ip_consistency', 0.0),
                                    'quality_start_rate': metrics.get('quality_start_rate', 0.0),
                                    'deep_start_rate': metrics.get('deep_start_rate', 0.0),
                                    'floor_points': metrics.get('floor_points', 0.0),
                                    'median_points': metrics.get('median_points', 0.0),
                                    'workhorse_score': metrics.get('workhorse_score', 0.0)
                                })

                            player_scores.append(player_dict)

                except Exception as e:
                    logger.error(f"Error processing player {player_id}: {e}")
                    continue

            # Sort by bestball_score
            player_scores.sort(key=lambda x: x['bestball_score'], reverse=True)

            return player_scores[:limit]

        finally:
            session.close()

    def get_top_bestball_players_combined(
        self,
        min_games: int = 20,
        limit: int = 100,
        progress_callback=None
    ) -> List[Dict]:
        """
        Get top players for best ball combining both batting and pitching.

        This creates a unified ranking where hitters and pitchers compete on the
        same bestball_score metric (0-100). Since hitters play more frequently,
        they naturally accumulate more USEFUL points and will dominate the rankings.

        Args:
            min_games: Minimum games required
            limit: Number of players to return
            progress_callback: Optional callback function(current, total, player_name, player_type)

        Returns:
            List of player dictionaries with weekly metrics and player_type field
        """
        logger.info("Calculating combined Best Ball rankings (batting + pitching)...")

        # Get batting players
        logger.info("Fetching batting players...")
        batting_players = self.get_top_bestball_players(
            stats_type="batting",
            min_games=min_games,
            limit=500,  # Get more than needed so we have a good pool
            progress_callback=lambda curr, total, name: progress_callback(
                curr, total * 2, name, "batting"
            ) if progress_callback else None
        )

        # Add player_type field to batting players
        for player in batting_players:
            player['player_type'] = 'batting'

        # Get pitching players
        logger.info("Fetching pitching players...")
        pitching_players = self.get_top_bestball_players(
            stats_type="pitching",
            min_games=min_games,
            limit=500,  # Get more than needed so we have a good pool
            progress_callback=lambda curr, total, name: progress_callback(
                curr + total, total * 2, name, "pitching"
            ) if progress_callback else None
        )

        # Add player_type field to pitching players
        for player in pitching_players:
            player['player_type'] = 'pitching'

        # Combine and sort by bestball_score
        combined_players = batting_players + pitching_players
        combined_players.sort(key=lambda x: x['bestball_score'], reverse=True)

        logger.info(f"Combined rankings: {len(batting_players)} hitters + {len(pitching_players)} pitchers = {len(combined_players)} total")

        # Return top N
        return combined_players[:limit]


if __name__ == "__main__":
    # Example usage
    from ..database import DatabaseManager

    db = DatabaseManager()
    analyzer = WeeklyAnalyzer(db)

    # Example: Get top best ball players
    # top_players = analyzer.get_top_bestball_players("batting", min_games=20, limit=25)
    # for i, p in enumerate(top_players, 1):
    #     print(f"{i}. {p['player_name']}: BB Score={p['bestball_score']:.1f}, Best Week={p['best_week']:.1f}")
