"""
DraftKings fantasy points calculator for MLB.
"""
import json
import os
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class DKPointsCalculator:
    """Calculate DraftKings fantasy points for MLB players."""

    def __init__(self, scoring_config_path: Optional[str] = None):
        """
        Initialize calculator with scoring rules.

        Args:
            scoring_config_path: Path to JSON file with scoring rules
        """
        if scoring_config_path is None:
            # Default to config directory
            config_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                "config"
            )
            scoring_config_path = os.path.join(config_dir, "dk_scoring.json")

        with open(scoring_config_path, 'r') as f:
            config = json.load(f)

        self.batting_scoring = config["batting"]
        self.pitching_scoring = config["pitching"]

    def innings_to_float(self, ip_str: str) -> float:
        """
        Convert innings pitched string to float.

        Args:
            ip_str: Innings pitched (e.g., "5.2" for 5 and 2/3 innings)

        Returns:
            Float representation of innings
        """
        if not ip_str or ip_str == "0":
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
            logger.warning(f"Could not parse innings pitched: {ip_str}")
            return 0.0

    def calculate_batting_points(self, batting_stats: Dict) -> float:
        """
        Calculate DraftKings points for a hitter.

        Args:
            batting_stats: Dictionary of batting statistics from API

        Returns:
            Total DraftKings points
        """
        s = self.batting_scoring

        # Calculate singles
        hits = batting_stats.get("hits", 0)
        doubles = batting_stats.get("doubles", 0)
        triples = batting_stats.get("triples", 0)
        home_runs = batting_stats.get("homeRuns", 0)
        singles = max(0, hits - doubles - triples - home_runs)

        points = 0.0

        # Hitting stats
        points += singles * s["1B"]
        points += doubles * s["2B"]
        points += triples * s["3B"]
        points += home_runs * s["HR"]

        # Production stats
        points += batting_stats.get("rbi", 0) * s["RBI"]
        points += batting_stats.get("runs", 0) * s["R"]

        # Plate discipline
        points += batting_stats.get("baseOnBalls", 0) * s["BB"]
        points += batting_stats.get("intentionalWalks", 0) * s.get("IBB", 0)
        points += batting_stats.get("hitByPitch", 0) * s["HBP"]

        # Base running
        points += batting_stats.get("stolenBases", 0) * s["SB"]
        points += batting_stats.get("caughtStealing", 0) * s.get("CS", 0)

        return round(points, 2)

    def calculate_pitching_points(self, pitching_stats: Dict) -> float:
        """
        Calculate DraftKings points for a pitcher.

        Args:
            pitching_stats: Dictionary of pitching statistics from API

        Returns:
            Total DraftKings points
        """
        s = self.pitching_scoring

        points = 0.0

        # Innings pitched
        ip = self.innings_to_float(pitching_stats.get("inningsPitched", "0"))
        points += ip * s["IP"]

        # Strikeouts
        points += pitching_stats.get("strikeOuts", 0) * s["SO"]

        # Win
        points += pitching_stats.get("wins", 0) * s["W"]

        # Earned runs (negative points)
        points += pitching_stats.get("earnedRuns", 0) * s["ER"]

        # Hits allowed (negative points)
        points += pitching_stats.get("hits", 0) * s["H"]

        # Walks (negative points)
        points += pitching_stats.get("baseOnBalls", 0) * s["BB"]

        # Hit batters (negative points)
        points += pitching_stats.get("hitBatsmen", 0) * s["HBP"]

        # Complete game bonuses
        if pitching_stats.get("completeGames", 0) > 0:
            points += s["CG"]

        # Complete game shutout bonuses
        if pitching_stats.get("shutouts", 0) > 0:
            points += s["CGSO"]

        # No-hitter bonus (check if complete game with 0 hits)
        if (pitching_stats.get("completeGames", 0) > 0 and
            pitching_stats.get("hits", 0) == 0 and
            ip >= 9.0):
            points += s["NH"]

        return round(points, 2)

    def calculate_points(self, player_data: Dict) -> float:
        """
        Calculate DraftKings points for any player.

        Args:
            player_data: Dictionary with 'statsType' and 'stats' keys

        Returns:
            Total DraftKings points
        """
        stats_type = player_data.get("statsType")
        stats = player_data.get("stats", {})

        if stats_type == "batting":
            return self.calculate_batting_points(stats)
        elif stats_type == "pitching":
            return self.calculate_pitching_points(stats)
        else:
            logger.warning(f"Unknown stats type: {stats_type}")
            return 0.0


if __name__ == "__main__":
    # Example usage
    calculator = DKPointsCalculator()

    # Example batting stats
    batting_example = {
        "hits": 3,
        "doubles": 1,
        "triples": 0,
        "homeRuns": 1,
        "rbi": 3,
        "runs": 2,
        "baseOnBalls": 1,
        "stolenBases": 1,
        "caughtStealing": 0,
        "hitByPitch": 0,
        "intentionalWalks": 0
    }

    batting_points = calculator.calculate_batting_points(batting_example)
    print(f"Batting points: {batting_points}")

    # Example pitching stats
    pitching_example = {
        "inningsPitched": "7.0",
        "strikeOuts": 8,
        "wins": 1,
        "earnedRuns": 2,
        "hits": 5,
        "baseOnBalls": 2,
        "hitBatsmen": 0
    }

    pitching_points = calculator.calculate_pitching_points(pitching_example)
    print(f"Pitching points: {pitching_points}")
