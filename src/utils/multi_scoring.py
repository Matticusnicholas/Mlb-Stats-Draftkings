"""
Multi-scoring system support for recalculating points from raw stats.
"""
import json
import os
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class MultiScoringCalculator:
    """Calculate fantasy points using different scoring systems."""

    def __init__(self):
        """Initialize with all available scoring systems."""
        self.scoring_systems = {}
        self.load_all_scoring_systems()

    def load_all_scoring_systems(self):
        """Load all scoring system configurations."""
        config_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "config"
        )

        # Load each scoring system
        scoring_files = {
            'draftkings': 'dk_scoring.json',
            'underdog': 'underdog_scoring.json',
            'cutline': 'cutline_scoring.json'
        }

        for system_name, filename in scoring_files.items():
            filepath = os.path.join(config_dir, filename)
            if os.path.exists(filepath):
                try:
                    with open(filepath, 'r') as f:
                        config = json.load(f)
                        self.scoring_systems[system_name] = config
                        logger.info(f"Loaded scoring system: {system_name} ({config.get('platform', 'Unknown')})")
                except Exception as e:
                    logger.error(f"Error loading {filename}: {e}")

        # Add placeholder for Drafters (until we get their scoring)
        self.scoring_systems['drafters'] = {
            'platform': 'Drafters',
            'format': 'Best Ball',
            'batting': {
                '1B': 3, '2B': 5, '3B': 8, 'HR': 10,
                'RBI': 2, 'R': 2, 'BB': 2, 'IBB': 2, 'HBP': 2,
                'SB': 5, 'CS': -2
            },
            'pitching': {
                'IP': 2.25, 'SO': 2, 'W': 4, 'ER': -2,
                'H': -0.6, 'BB': -0.6, 'HBP': -0.6,
                'CG': 2.5, 'CGSO': 2.5, 'NH': 5
            },
            'note': 'Using DraftKings scoring as placeholder. Update when Drafters scoring is found.'
        }

    def get_available_systems(self) -> Dict:
        """Get list of available scoring systems."""
        return {
            name: {
                'platform': config.get('platform', 'Unknown'),
                'format': config.get('format', 'Unknown')
            }
            for name, config in self.scoring_systems.items()
        }

    def innings_to_float(self, ip_str) -> float:
        """Convert innings pitched to float."""
        if not ip_str or ip_str == 0:
            return 0.0

        ip_str = str(ip_str)
        whole, _, frac = ip_str.partition(".")

        add = 0.0
        if frac == "1":
            add = 1/3
        elif frac == "2":
            add = 2/3

        try:
            return int(whole) + add
        except ValueError:
            return 0.0

    def calculate_batting_points(self, player_game, scoring_system: str = 'draftkings') -> float:
        """
        Calculate batting points from raw stats using specified scoring system.

        Args:
            player_game: PlayerGame object with batting stats
            scoring_system: 'draftkings', 'underdog', 'drafters', or 'cutline'

        Returns:
            Total fantasy points
        """
        if scoring_system not in self.scoring_systems:
            logger.warning(f"Unknown scoring system: {scoring_system}, using draftkings")
            scoring_system = 'draftkings'

        s = self.scoring_systems[scoring_system]['batting']

        points = 0.0

        # Cutline-style scoring: uses AB and total Hits (not broken down by type)
        if s.get('AB') is not None:
            # At bats penalty (Cutline: -1 per AB)
            points += (player_game.at_bats or 0) * s.get('AB', 0)
            # Total hits (Cutline: +4 per hit, all hits equal)
            points += (player_game.hits or 0) * s.get('H', 0)
            # Home run bonus (Cutline: +6 per HR, on top of hit value)
            points += (player_game.home_runs or 0) * s.get('HR', 0)
        else:
            # Standard scoring: singles, doubles, triples, HR separately
            singles = max(0, (player_game.hits or 0) - (player_game.doubles or 0) -
                          (player_game.triples or 0) - (player_game.home_runs or 0))
            points += singles * s.get('1B', 0)
            points += (player_game.doubles or 0) * s.get('2B', 0)
            points += (player_game.triples or 0) * s.get('3B', 0)
            points += (player_game.home_runs or 0) * s.get('HR', 0)

        # Production stats
        points += (player_game.rbi or 0) * s.get('RBI', 0)
        points += (player_game.runs or 0) * s.get('R', 0)

        # Plate discipline
        points += (player_game.walks or 0) * s.get('BB', 0)
        points += (player_game.intentional_walks or 0) * s.get('IBB', 0)
        points += (player_game.hit_by_pitch or 0) * s.get('HBP', 0)

        # Base running
        points += (player_game.stolen_bases or 0) * s.get('SB', 0)
        points += (player_game.caught_stealing or 0) * s.get('CS', 0)

        return round(points, 2)

    def calculate_pitching_points(self, player_game, scoring_system: str = 'draftkings') -> float:
        """
        Calculate pitching points from raw stats using specified scoring system.

        Args:
            player_game: PlayerGame object with pitching stats
            scoring_system: 'draftkings', 'underdog', 'drafters', or 'cutline'

        Returns:
            Total fantasy points
        """
        if scoring_system not in self.scoring_systems:
            logger.warning(f"Unknown scoring system: {scoring_system}, using draftkings")
            scoring_system = 'draftkings'

        s = self.scoring_systems[scoring_system]['pitching']

        points = 0.0

        # Innings pitched
        ip = self.innings_to_float(player_game.innings_pitched or 0)
        points += ip * s.get('IP', 0)

        # Strikeouts
        points += (player_game.strikeouts_pitching or 0) * s.get('SO', 0)

        # Win
        points += (player_game.wins or 0) * s.get('W', 0)

        # Save (Cutline specific)
        points += (player_game.saves or 0) * s.get('SV', 0)

        # Quality Start (Underdog specific)
        if s.get('QS', 0) > 0:
            if ip >= 6.0 and (player_game.earned_runs or 0) <= 3:
                points += s.get('QS', 0)

        # Earned runs (negative points)
        points += (player_game.earned_runs or 0) * s.get('ER', 0)

        # Hits allowed (negative points)
        points += (player_game.hits_allowed or 0) * s.get('H', 0)

        # Walks (negative points)
        points += (player_game.walks_allowed or 0) * s.get('BB', 0)

        # Hit batters (negative points)
        points += (player_game.hit_batsmen or 0) * s.get('HBP', 0)

        # Complete game bonuses
        if (player_game.complete_games or 0) > 0:
            points += s.get('CG', 0)

        # Complete game shutout bonuses
        if (player_game.shutouts or 0) > 0:
            points += s.get('CGSO', 0)

        # No-hitter bonus
        if ((player_game.complete_games or 0) > 0 and
            (player_game.hits_allowed or 0) == 0 and
            ip >= 9.0):
            points += s.get('NH', 0)

        return round(points, 2)

    def recalculate_points(self, player_game, scoring_system: str = 'draftkings') -> float:
        """
        Recalculate points for any player game using specified scoring system.

        Args:
            player_game: PlayerGame object
            scoring_system: Scoring system to use

        Returns:
            Recalculated fantasy points
        """
        if player_game.stats_type == 'batting':
            return self.calculate_batting_points(player_game, scoring_system)
        elif player_game.stats_type == 'pitching':
            return self.calculate_pitching_points(player_game, scoring_system)
        else:
            logger.warning(f"Unknown stats_type: {player_game.stats_type}")
            return 0.0


if __name__ == "__main__":
    # Example usage
    calc = MultiScoringCalculator()
    print("Available scoring systems:")
    for name, info in calc.get_available_systems().items():
        print(f"  {name}: {info['platform']} - {info['format']}")
