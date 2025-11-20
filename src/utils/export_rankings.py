"""
Export rankings to various formats for drafting platforms.
"""
import csv
import json
from typing import List, Dict
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class RankingsExporter:
    """Export player rankings to various formats."""

    @staticmethod
    def to_csv(players: List[Dict], filepath: str, include_workhorse: bool = False) -> None:
        """
        Export players to CSV format compatible with DraftKings and other platforms.

        Args:
            players: List of player dictionaries with metrics
            filepath: Output CSV file path
            include_workhorse: Include workhorse metrics for pitchers (default False)
        """
        if not players:
            logger.warning("No players to export")
            return

        # Determine if we have combined rankings (check for player_type)
        has_player_type = 'player_type' in players[0]

        # Base columns
        columns = [
            'Rank',
            'Player Name',
            'Player ID',
        ]

        if has_player_type:
            columns.append('Position')  # BAT or PIT

        # Best Ball metrics (common to all players)
        columns.extend([
            'BB Score',
            'Best Week',
            'Top3 Weeks Avg',
            'Mean Week',
            'Boom Week %',
            'TEAR3 Rate',
            'TEAR4 Rate',
            'Longest TEAR',
            'Useful Points',
            'Useful Weeks',
            'Useful Weeks %',
            'Useful Pts/Wk',
            'Wasted Points'
        ])

        # Check if we have any pitchers (look for pitcher-specific metrics)
        has_pitchers = any(p.get('player_type') == 'pitching' or
                          'pitching' in str(p.get('total_starts', '')).lower() or
                          p.get('level1_starts') is not None
                          for p in players)

        # Add pitcher-specific columns if needed
        if has_pitchers:
            columns.extend([
                'Level1 Starts',
                'Level2 Starts',
                'Level3 Starts',
                'QS Rate %'
            ])

            if include_workhorse:
                columns.extend([
                    'Total Starts',
                    'Avg IP/Start',
                    'Total Innings',
                    'Quality Start %',
                    'Deep Start %',
                    'Floor Points',
                    'Workhorse Score'
                ])

        try:
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=columns)
                writer.writeheader()

                for rank, player in enumerate(players, 1):
                    row = {
                        'Rank': rank,
                        'Player Name': player.get('player_name', ''),
                        'Player ID': player.get('player_id', ''),
                    }

                    if has_player_type:
                        player_type = player.get('player_type', 'batting')
                        row['Position'] = 'PIT' if player_type == 'pitching' else 'BAT'

                    # Best Ball metrics
                    row.update({
                        'BB Score': f"{player.get('bestball_score', 0):.1f}",
                        'Best Week': f"{player.get('best_week', 0):.1f}",
                        'Top3 Weeks Avg': f"{player.get('top3_weeks_avg', 0):.1f}",
                        'Mean Week': f"{player.get('mean_week_points', 0):.1f}",
                        'Boom Week %': f"{player.get('boom_week_rate', 0):.1f}",
                        'TEAR3 Rate': f"{player.get('tear3_rate', 0):.1f}",
                        'TEAR4 Rate': f"{player.get('tear4_rate', 0):.1f}",
                        'Longest TEAR': player.get('longest_tear', 0),
                        'Useful Points': f"{player.get('useful_points_total', 0):.1f}",
                        'Useful Weeks': player.get('useful_weeks_count', 0),
                        'Useful Weeks %': f"{player.get('useful_weeks_pct', 0):.1f}",
                        'Useful Pts/Wk': f"{player.get('useful_points_per_week', 0):.1f}",
                        'Wasted Points': f"{player.get('wasted_points', 0):.1f}"
                    })

                    # Pitcher-specific metrics
                    if has_pitchers:
                        is_pitcher = (player.get('player_type') == 'pitching' or
                                     player.get('level1_starts') is not None)

                        if is_pitcher:
                            row.update({
                                'Level1 Starts': player.get('level1_starts', 0),
                                'Level2 Starts': player.get('level2_starts', 0),
                                'Level3 Starts': player.get('level3_starts', 0),
                                'QS Rate %': f"{player.get('quality_start_rate', 0):.1f}" if include_workhorse else ""
                            })

                            if include_workhorse:
                                row.update({
                                    'Total Starts': player.get('total_starts', 0),
                                    'Avg IP/Start': f"{player.get('avg_ip_per_start', 0):.2f}",
                                    'Total Innings': f"{player.get('total_innings', 0):.1f}",
                                    'Quality Start %': f"{player.get('quality_start_rate', 0):.1f}",
                                    'Deep Start %': f"{player.get('deep_start_rate', 0):.1f}",
                                    'Floor Points': f"{player.get('floor_points', 0):.1f}",
                                    'Workhorse Score': f"{player.get('workhorse_score', 0):.1f}"
                                })
                        else:
                            # Leave pitcher columns blank for hitters
                            row.update({
                                'Level1 Starts': '',
                                'Level2 Starts': '',
                                'Level3 Starts': '',
                                'QS Rate %': ''
                            })

                            if include_workhorse:
                                row.update({
                                    'Total Starts': '',
                                    'Avg IP/Start': '',
                                    'Total Innings': '',
                                    'Quality Start %': '',
                                    'Deep Start %': '',
                                    'Floor Points': '',
                                    'Workhorse Score': ''
                                })

                    writer.writerow(row)

            logger.info(f"Exported {len(players)} players to {filepath}")

        except Exception as e:
            logger.error(f"Error exporting to CSV: {e}")
            raise

    @staticmethod
    def to_json(players: List[Dict], filepath: str) -> None:
        """
        Export players to JSON format.

        Args:
            players: List of player dictionaries with metrics
            filepath: Output JSON file path
        """
        if not players:
            logger.warning("No players to export")
            return

        try:
            export_data = {
                'generated_at': datetime.now().isoformat(),
                'count': len(players),
                'players': players
            }

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2)

            logger.info(f"Exported {len(players)} players to {filepath}")

        except Exception as e:
            logger.error(f"Error exporting to JSON: {e}")
            raise


if __name__ == "__main__":
    # Example usage
    print("Rankings export utility")
    print("Use the web API or CLI to export rankings")
