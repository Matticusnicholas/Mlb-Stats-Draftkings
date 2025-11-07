"""
Visualization utilities for player performance analysis.
"""
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import numpy as np
from typing import List, Dict, Optional
from datetime import datetime
import logging

from ..database.db_manager import DatabaseManager
from ..database.models import Game

logger = logging.getLogger(__name__)

# Set style
sns.set_style("darkgrid")
plt.rcParams['figure.figsize'] = (12, 6)


class PerformanceVisualizer:
    """Create visualizations for player performance analysis."""

    def __init__(self, db_manager: DatabaseManager):
        """
        Initialize visualizer.

        Args:
            db_manager: Database manager instance
        """
        self.db = db_manager

    def plot_player_timeline(
        self,
        player_id: int,
        stats_type: str = "batting",
        save_path: Optional[str] = None
    ):
        """
        Plot player's DK points over time.

        Args:
            player_id: MLB player ID
            stats_type: 'batting' or 'pitching'
            save_path: Optional path to save figure
        """
        player_games = self.db.get_player_games(player_id, stats_type)

        if not player_games:
            logger.warning(f"No games found for player {player_id}")
            return

        # Get game dates and points
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
            df = df.sort_values('date')

            # Calculate rolling average
            df['rolling_avg'] = df['points'].rolling(window=7, min_periods=1).mean()

            # Create figure
            fig, ax = plt.subplots(figsize=(14, 7))

            # Plot actual points
            ax.plot(df['date'], df['points'], marker='o', linestyle='-',
                   alpha=0.6, label='Actual Points', color='steelblue')

            # Plot rolling average
            ax.plot(df['date'], df['rolling_avg'], linestyle='--',
                   linewidth=2, label='7-Game Rolling Avg', color='orange')

            # Add mean line
            mean_points = df['points'].mean()
            ax.axhline(y=mean_points, color='green', linestyle=':',
                      linewidth=2, label=f'Season Mean ({mean_points:.1f})')

            # Highlight boom games (20+ points)
            boom_games = df[df['points'] >= 20]
            if not boom_games.empty:
                ax.scatter(boom_games['date'], boom_games['points'],
                          color='red', s=100, zorder=5, label='Boom Games (20+)',
                          marker='*')

            # Formatting
            ax.set_xlabel('Date', fontsize=12)
            ax.set_ylabel('DraftKings Points', fontsize=12)
            ax.set_title(f'Player {player_id} Performance Timeline', fontsize=14, fontweight='bold')
            ax.legend(loc='upper left')
            ax.grid(True, alpha=0.3)

            plt.xticks(rotation=45)
            plt.tight_layout()

            if save_path:
                plt.savefig(save_path, dpi=300, bbox_inches='tight')
                logger.info(f"Saved plot to {save_path}")

            plt.show()

        finally:
            session.close()

    def plot_distribution(
        self,
        player_id: int,
        stats_type: str = "batting",
        save_path: Optional[str] = None
    ):
        """
        Plot distribution of player's DK points.

        Args:
            player_id: MLB player ID
            stats_type: 'batting' or 'pitching'
            save_path: Optional path to save figure
        """
        player_games = self.db.get_player_games(player_id, stats_type)

        if not player_games:
            logger.warning(f"No games found for player {player_id}")
            return

        points = [pg.dk_points for pg in player_games]

        # Create figure with subplots
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))

        # Histogram with KDE
        axes[0].hist(points, bins=20, alpha=0.7, color='steelblue', edgecolor='black')
        axes[0].axvline(np.mean(points), color='red', linestyle='--',
                       linewidth=2, label=f'Mean: {np.mean(points):.1f}')
        axes[0].axvline(np.median(points), color='green', linestyle=':',
                       linewidth=2, label=f'Median: {np.median(points):.1f}')
        axes[0].set_xlabel('DraftKings Points', fontsize=12)
        axes[0].set_ylabel('Frequency', fontsize=12)
        axes[0].set_title('Points Distribution', fontsize=14, fontweight='bold')
        axes[0].legend()
        axes[0].grid(True, alpha=0.3)

        # Box plot
        box = axes[1].boxplot(points, vert=True, patch_artist=True,
                             labels=['Player Performance'])
        box['boxes'][0].set_facecolor('lightblue')
        box['boxes'][0].set_alpha(0.7)

        # Add scatter of actual points
        y = points
        x = np.random.normal(1, 0.04, size=len(y))
        axes[1].scatter(x, y, alpha=0.4, color='steelblue', s=30)

        axes[1].set_ylabel('DraftKings Points', fontsize=12)
        axes[1].set_title('Points Box Plot', fontsize=14, fontweight='bold')
        axes[1].grid(True, alpha=0.3, axis='y')

        plt.suptitle(f'Player {player_id} Score Distribution Analysis',
                    fontsize=16, fontweight='bold', y=1.02)
        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            logger.info(f"Saved plot to {save_path}")

        plt.show()

    def plot_volatility_comparison(
        self,
        player_ids: List[int],
        stats_type: str = "batting",
        save_path: Optional[str] = None
    ):
        """
        Compare volatility metrics across multiple players.

        Args:
            player_ids: List of MLB player IDs
            stats_type: 'batting' or 'pitching'
            save_path: Optional path to save figure
        """
        if len(player_ids) < 2:
            logger.warning("Need at least 2 players for comparison")
            return

        session = self.db.get_session()
        try:
            from ..database.models import Player, PlayerVolatility

            data = []
            for player_id in player_ids:
                player = session.query(Player).filter_by(player_id=player_id).first()
                volatility = session.query(PlayerVolatility).filter_by(
                    player_id=player_id
                ).first()

                if player and volatility:
                    data.append({
                        'player_name': player.player_name,
                        'variance_score': volatility.variance_score,
                        'upside_score': volatility.upside_score,
                        'mean_points': volatility.mean_points,
                        'std_dev': volatility.std_dev,
                        'boom_rate': volatility.boom_rate
                    })

            if not data:
                logger.warning("No volatility data found for these players")
                return

            df = pd.DataFrame(data)

            # Create subplots
            fig, axes = plt.subplots(2, 2, figsize=(14, 10))

            # Variance Score
            axes[0, 0].barh(df['player_name'], df['variance_score'], color='steelblue')
            axes[0, 0].set_xlabel('Variance Score', fontsize=11)
            axes[0, 0].set_title('Variance Score Comparison', fontsize=12, fontweight='bold')
            axes[0, 0].grid(True, alpha=0.3, axis='x')

            # Upside Score
            axes[0, 1].barh(df['player_name'], df['upside_score'], color='coral')
            axes[0, 1].set_xlabel('Upside Score', fontsize=11)
            axes[0, 1].set_title('Upside Score Comparison', fontsize=12, fontweight='bold')
            axes[0, 1].grid(True, alpha=0.3, axis='x')

            # Mean vs Std Dev scatter
            axes[1, 0].scatter(df['mean_points'], df['std_dev'], s=200, alpha=0.6, color='green')
            for idx, row in df.iterrows():
                axes[1, 0].annotate(row['player_name'], (row['mean_points'], row['std_dev']),
                                   fontsize=8, ha='right')
            axes[1, 0].set_xlabel('Mean Points', fontsize=11)
            axes[1, 0].set_ylabel('Std Deviation', fontsize=11)
            axes[1, 0].set_title('Mean vs Volatility', fontsize=12, fontweight='bold')
            axes[1, 0].grid(True, alpha=0.3)

            # Boom Rate
            axes[1, 1].barh(df['player_name'], df['boom_rate'], color='purple')
            axes[1, 1].set_xlabel('Boom Rate (%)', fontsize=11)
            axes[1, 1].set_title('Boom Rate (20+ pt games)', fontsize=12, fontweight='bold')
            axes[1, 1].grid(True, alpha=0.3, axis='x')

            plt.suptitle('Player Volatility Comparison', fontsize=16, fontweight='bold', y=0.995)
            plt.tight_layout()

            if save_path:
                plt.savefig(save_path, dpi=300, bbox_inches='tight')
                logger.info(f"Saved plot to {save_path}")

            plt.show()

        finally:
            session.close()

    def plot_weekly_volatility(
        self,
        player_id: int,
        stats_type: str = "batting",
        save_path: Optional[str] = None
    ):
        """
        Plot rolling weekly volatility metrics.

        Args:
            player_id: MLB player ID
            stats_type: 'batting' or 'pitching'
            save_path: Optional path to save figure
        """
        from ..analytics.volatility_analyzer import VolatilityAnalyzer

        analyzer = VolatilityAnalyzer(self.db)
        df = analyzer.get_weekly_volatility(player_id, stats_type)

        if df.empty:
            logger.warning(f"No data for player {player_id}")
            return

        fig, axes = plt.subplots(2, 1, figsize=(14, 10))

        # Points with rolling average
        axes[0].plot(df['date'], df['points'], marker='o', linestyle='-',
                    alpha=0.6, label='Actual Points', color='steelblue')
        axes[0].plot(df['date'], df['week_mean'], linestyle='--',
                    linewidth=2, label='7-Game Rolling Mean', color='orange')

        # Fill between for volatility bands
        axes[0].fill_between(df['date'],
                            df['week_mean'] - df['week_std'],
                            df['week_mean'] + df['week_std'],
                            alpha=0.2, color='orange', label='±1 Std Dev')

        axes[0].set_xlabel('Date', fontsize=12)
        axes[0].set_ylabel('DraftKings Points', fontsize=12)
        axes[0].set_title('Performance with Rolling Volatility Bands', fontsize=14, fontweight='bold')
        axes[0].legend()
        axes[0].grid(True, alpha=0.3)
        plt.setp(axes[0].xaxis.get_majorticklabels(), rotation=45)

        # Z-scores
        axes[1].bar(df['date'], df['z_score'], alpha=0.7, color='steelblue')
        axes[1].axhline(y=0, color='black', linestyle='-', linewidth=1)
        axes[1].axhline(y=2, color='red', linestyle='--', linewidth=1, label='Spike Threshold (+2σ)')
        axes[1].axhline(y=-2, color='blue', linestyle='--', linewidth=1, label='Bust Threshold (-2σ)')

        axes[1].set_xlabel('Date', fontsize=12)
        axes[1].set_ylabel('Z-Score', fontsize=12)
        axes[1].set_title('Rolling Z-Scores (Weekly)', fontsize=14, fontweight='bold')
        axes[1].legend()
        axes[1].grid(True, alpha=0.3)
        plt.setp(axes[1].xaxis.get_majorticklabels(), rotation=45)

        plt.suptitle(f'Player {player_id} Weekly Volatility Analysis',
                    fontsize=16, fontweight='bold', y=0.995)
        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            logger.info(f"Saved plot to {save_path}")

        plt.show()


if __name__ == "__main__":
    # Example usage
    from ..database import DatabaseManager

    db = DatabaseManager()
    viz = PerformanceVisualizer(db)

    # Example: plot timeline for a player
    # viz.plot_player_timeline(player_id=12345, stats_type="batting")
