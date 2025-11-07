"""
MLB Stats API client for fetching game and player data.
"""
import requests
import time
from datetime import date, datetime, timedelta
from typing import List, Dict, Optional, Tuple
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MLBStatsAPI:
    """Client for interacting with MLB Stats API."""

    BASE_URL = "https://statsapi.mlb.com/api/v1"

    def __init__(self, rate_limit_delay: float = 0.3, max_retries: int = 3):
        """
        Initialize MLB Stats API client.

        Args:
            rate_limit_delay: Delay between requests in seconds
            max_retries: Maximum number of retries for failed requests
        """
        self.rate_limit_delay = rate_limit_delay
        self.max_retries = max_retries
        self.session = requests.Session()

    def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """
        Make an API request with retry logic and rate limiting.

        Args:
            endpoint: API endpoint path
            params: Query parameters

        Returns:
            JSON response as dictionary
        """
        url = f"{self.BASE_URL}{endpoint}"

        for attempt in range(self.max_retries):
            try:
                response = self.session.get(url, params=params, timeout=30)
                response.raise_for_status()
                time.sleep(self.rate_limit_delay)
                return response.json()
            except requests.exceptions.RequestException as e:
                logger.warning(f"Request failed (attempt {attempt + 1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                else:
                    raise

    def fetch_schedule(
        self,
        start_date: date,
        end_date: date,
        season: str = "2025",
        game_type: str = "R"
    ) -> List[Dict]:
        """
        Fetch game schedule for a date range.

        Args:
            start_date: Start date
            end_date: End date
            season: Season year
            game_type: Game type (R=Regular, S=Spring, P=Postseason)

        Returns:
            List of game dictionaries with gamePk and metadata
        """
        params = {
            "sportId": 1,
            "season": season,
            "gameType": game_type,
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat()
        }

        data = self._make_request("/schedule", params)

        games = []
        for date_entry in data.get("dates", []):
            for game in date_entry.get("games", []):
                games.append({
                    "gamePk": game["gamePk"],
                    "gameDate": game["gameDate"],
                    "gameType": game.get("gameType", game_type),
                    "awayTeamId": game["teams"]["away"]["team"]["id"],
                    "awayTeamName": game["teams"]["away"]["team"]["name"],
                    "homeTeamId": game["teams"]["home"]["team"]["id"],
                    "homeTeamName": game["teams"]["home"]["team"]["name"],
                    "doubleHeader": game.get("doubleHeader", "N"),
                    "gameNumber": game.get("gameNumber", 1)
                })

        logger.info(f"Fetched {len(games)} games from {start_date} to {end_date}")
        return games

    def fetch_season_schedule(self, season: str = "2025", game_type: str = "R") -> List[Dict]:
        """
        Fetch all games for an entire season in monthly chunks.

        Args:
            season: Season year
            game_type: Game type

        Returns:
            List of all games for the season
        """
        # Define monthly date ranges
        date_ranges = [
            (f"{season}-03-01", f"{season}-03-31"),
            (f"{season}-04-01", f"{season}-04-30"),
            (f"{season}-05-01", f"{season}-05-31"),
            (f"{season}-06-01", f"{season}-06-30"),
            (f"{season}-07-01", f"{season}-07-31"),
            (f"{season}-08-01", f"{season}-08-31"),
            (f"{season}-09-01", f"{season}-09-30"),
            (f"{season}-10-01", f"{season}-11-30")
        ]

        all_games = []
        for start_str, end_str in date_ranges:
            try:
                start = date.fromisoformat(start_str)
                end = date.fromisoformat(end_str)
                games = self.fetch_schedule(start, end, season, game_type)
                all_games.extend(games)
            except Exception as e:
                logger.error(f"Error fetching schedule for {start_str} to {end_str}: {e}")

        # Remove duplicates by gamePk
        unique_games = {game["gamePk"]: game for game in all_games}
        logger.info(f"Fetched {len(unique_games)} unique games for {season} season")
        return list(unique_games.values())

    def fetch_boxscore(self, game_pk: int) -> Dict:
        """
        Fetch boxscore data for a specific game.

        Args:
            game_pk: Game primary key

        Returns:
            Boxscore data dictionary
        """
        data = self._make_request(f"/game/{game_pk}/boxscore")
        return data

    def fetch_game_feed(self, game_pk: int) -> Dict:
        """
        Fetch live game feed with play-by-play data.

        Args:
            game_pk: Game primary key

        Returns:
            Game feed data dictionary
        """
        data = self._make_request(f"/game/{game_pk}/feed/live")
        return data

    def extract_player_stats(self, boxscore: Dict) -> List[Dict]:
        """
        Extract player statistics from boxscore data.

        Args:
            boxscore: Boxscore data from API

        Returns:
            List of player stat dictionaries
        """
        player_stats = []

        for team_type in ["home", "away"]:
            team_data = boxscore.get("teams", {}).get(team_type, {})
            team_id = team_data.get("team", {}).get("id")
            team_name = team_data.get("team", {}).get("name", "")

            players = team_data.get("players", {})

            for player_key, player_data in players.items():
                person = player_data.get("person", {})
                player_id = person.get("id")
                player_name = person.get("fullName", "")

                stats = player_data.get("stats", {})
                position = player_data.get("position", {}).get("abbreviation", "")

                # Extract batting stats
                batting = stats.get("batting", {})
                if batting and batting.get("atBats", 0) > 0 or batting.get("plateAppearances", 0) > 0:
                    player_stats.append({
                        "playerId": player_id,
                        "playerName": player_name,
                        "teamId": team_id,
                        "teamName": team_name,
                        "position": position,
                        "statsType": "batting",
                        "stats": batting
                    })

                # Extract pitching stats
                pitching = stats.get("pitching", {})
                if pitching and pitching.get("inningsPitched", "0") != "0":
                    player_stats.append({
                        "playerId": player_id,
                        "playerName": player_name,
                        "teamId": team_id,
                        "teamName": team_name,
                        "position": position,
                        "statsType": "pitching",
                        "stats": pitching
                    })

        return player_stats


if __name__ == "__main__":
    # Example usage
    api = MLBStatsAPI()

    # Fetch a sample schedule
    start = date(2025, 4, 1)
    end = date(2025, 4, 7)
    games = api.fetch_schedule(start, end)
    print(f"Found {len(games)} games")

    if games:
        # Fetch boxscore for first game
        game_pk = games[0]["gamePk"]
        print(f"\nFetching boxscore for game {game_pk}...")
        boxscore = api.fetch_boxscore(game_pk)

        # Extract player stats
        player_stats = api.extract_player_stats(boxscore)
        print(f"Extracted stats for {len(player_stats)} player performances")
