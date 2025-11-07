"""
Database manager for storing and retrieving MLB statistics.
"""
from typing import List, Dict, Optional, Tuple
from datetime import datetime, date
import logging
from sqlalchemy import func, and_, or_
from sqlalchemy.orm import Session

from .models import Game, Player, PlayerGame, PlayerVolatility, create_database, get_session

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages database operations for MLB statistics."""

    def __init__(self, db_path: str = "data/mlb_stats.db"):
        """
        Initialize database manager.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.engine = create_database(db_path)
        self.Session = get_session

    def get_session(self) -> Session:
        """Get a new database session."""
        return get_session(self.db_path)

    # ==================== GAME OPERATIONS ====================

    def add_games(self, games: List[Dict]) -> int:
        """
        Add multiple games to the database.

        Args:
            games: List of game dictionaries from API

        Returns:
            Number of games added
        """
        session = self.get_session()
        added = 0

        try:
            for game_data in games:
                # Check if game already exists
                existing = session.query(Game).filter_by(game_pk=game_data["gamePk"]).first()

                if not existing:
                    game = Game(
                        game_pk=game_data["gamePk"],
                        game_date=datetime.fromisoformat(game_data["gameDate"].replace("Z", "+00:00")),
                        game_type=game_data.get("gameType", "R"),
                        away_team_id=game_data["awayTeamId"],
                        away_team_name=game_data.get("awayTeamName", ""),
                        home_team_id=game_data["homeTeamId"],
                        home_team_name=game_data.get("homeTeamName", ""),
                        double_header=game_data.get("doubleHeader", "N"),
                        game_number=game_data.get("gameNumber", 1)
                    )
                    session.add(game)
                    added += 1

            session.commit()
            logger.info(f"Added {added} new games to database")
            return added

        except Exception as e:
            session.rollback()
            logger.error(f"Error adding games: {e}")
            raise
        finally:
            session.close()

    def get_games_to_fetch(self, limit: Optional[int] = None) -> List[int]:
        """
        Get list of game PKs that haven't had their boxscores fetched yet.

        Args:
            limit: Maximum number of games to return

        Returns:
            List of game PKs
        """
        session = self.get_session()
        try:
            query = session.query(Game.game_pk).filter_by(data_fetched=False)

            if limit:
                query = query.limit(limit)

            game_pks = [row[0] for row in query.all()]
            return game_pks

        finally:
            session.close()

    def mark_game_fetched(self, game_pk: int):
        """Mark a game as having its data fetched."""
        session = self.get_session()
        try:
            game = session.query(Game).filter_by(game_pk=game_pk).first()
            if game:
                game.data_fetched = True
                game.fetch_date = datetime.utcnow()
                session.commit()
        finally:
            session.close()

    # ==================== PLAYER OPERATIONS ====================

    def add_or_update_player(self, player_id: int, player_name: str) -> Player:
        """
        Add a new player or update existing player's info.

        Args:
            player_id: MLB player ID
            player_name: Player's full name

        Returns:
            Player object
        """
        session = self.get_session()
        try:
            player = session.query(Player).filter_by(player_id=player_id).first()

            if player:
                player.player_name = player_name
                player.last_updated = datetime.utcnow()
            else:
                player = Player(player_id=player_id, player_name=player_name)
                session.add(player)

            session.commit()
            return player

        finally:
            session.close()

    # ==================== PLAYER GAME OPERATIONS ====================

    def add_player_game(self, game_pk: int, player_data: Dict, dk_points: float):
        """
        Add a player's game performance.

        Args:
            game_pk: Game primary key
            player_data: Player data dictionary from API
            dk_points: Calculated DraftKings points
        """
        session = self.get_session()
        try:
            # Ensure player exists
            player_id = player_data["playerId"]
            player_name = player_data["playerName"]
            self.add_or_update_player(player_id, player_name)

            # Check if this player game already exists
            existing = session.query(PlayerGame).filter_by(
                game_pk=game_pk,
                player_id=player_id,
                stats_type=player_data["statsType"]
            ).first()

            if existing:
                # Update existing record
                self._update_player_game_stats(existing, player_data, dk_points)
            else:
                # Create new record
                player_game = PlayerGame(
                    game_pk=game_pk,
                    player_id=player_id,
                    team_id=player_data["teamId"],
                    team_name=player_data.get("teamName", ""),
                    position=player_data.get("position", ""),
                    stats_type=player_data["statsType"],
                    dk_points=dk_points
                )
                self._update_player_game_stats(player_game, player_data, dk_points)
                session.add(player_game)

            session.commit()

        except Exception as e:
            session.rollback()
            logger.error(f"Error adding player game: {e}")
            raise
        finally:
            session.close()

    def _update_player_game_stats(self, player_game: PlayerGame, player_data: Dict, dk_points: float):
        """Update player game statistics."""
        player_game.dk_points = dk_points
        stats = player_data["stats"]

        if player_data["statsType"] == "batting":
            player_game.at_bats = stats.get("atBats", 0)
            player_game.hits = stats.get("hits", 0)
            player_game.doubles = stats.get("doubles", 0)
            player_game.triples = stats.get("triples", 0)
            player_game.home_runs = stats.get("homeRuns", 0)
            player_game.singles = max(0, player_game.hits - player_game.doubles -
                                     player_game.triples - player_game.home_runs)
            player_game.rbi = stats.get("rbi", 0)
            player_game.runs = stats.get("runs", 0)
            player_game.walks = stats.get("baseOnBalls", 0)
            player_game.intentional_walks = stats.get("intentionalWalks", 0)
            player_game.hit_by_pitch = stats.get("hitByPitch", 0)
            player_game.stolen_bases = stats.get("stolenBases", 0)
            player_game.caught_stealing = stats.get("caughtStealing", 0)
            player_game.strikeouts_batting = stats.get("strikeOuts", 0)

        elif player_data["statsType"] == "pitching":
            ip_str = stats.get("inningsPitched", "0")
            player_game.innings_pitched = self._innings_to_float(ip_str)
            player_game.strikeouts_pitching = stats.get("strikeOuts", 0)
            player_game.wins = stats.get("wins", 0)
            player_game.losses = stats.get("losses", 0)
            player_game.saves = stats.get("saves", 0)
            player_game.earned_runs = stats.get("earnedRuns", 0)
            player_game.hits_allowed = stats.get("hits", 0)
            player_game.walks_allowed = stats.get("baseOnBalls", 0)
            player_game.hit_batsmen = stats.get("hitBatsmen", 0)
            player_game.complete_games = stats.get("completeGames", 0)
            player_game.shutouts = stats.get("shutouts", 0)

    def _innings_to_float(self, ip_str: str) -> float:
        """Convert innings pitched to float."""
        if not ip_str or ip_str == "0":
            return 0.0
        ip_str = str(ip_str)
        whole, _, frac = ip_str.partition(".")
        add = 0.0
        if frac == "1":
            add = 1/3
        elif frac == "2":
            add = 2/3
        return int(whole) + add

    def get_player_games(
        self,
        player_id: int,
        stats_type: str = "batting",
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[PlayerGame]:
        """
        Get all games for a player.

        Args:
            player_id: MLB player ID
            stats_type: 'batting' or 'pitching'
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            List of PlayerGame objects
        """
        session = self.get_session()
        try:
            query = session.query(PlayerGame).filter_by(
                player_id=player_id,
                stats_type=stats_type
            ).join(Game)

            if start_date:
                query = query.filter(Game.game_date >= start_date)
            if end_date:
                query = query.filter(Game.game_date <= end_date)

            games = query.order_by(Game.game_date).all()
            return games

        finally:
            session.close()

    # ==================== VOLATILITY OPERATIONS ====================

    def save_player_volatility(self, player_id: int, stats_type: str, metrics: Dict):
        """
        Save or update player volatility metrics.

        Args:
            player_id: MLB player ID
            stats_type: 'batting' or 'pitching'
            metrics: Dictionary of volatility metrics
        """
        session = self.get_session()
        try:
            volatility = session.query(PlayerVolatility).filter_by(
                player_id=player_id
            ).first()

            if volatility:
                # Update existing
                for key, value in metrics.items():
                    if hasattr(volatility, key):
                        setattr(volatility, key, value)
                volatility.last_updated = datetime.utcnow()
            else:
                # Create new - remove stats_type from metrics to avoid duplicate
                metrics_copy = metrics.copy()
                metrics_copy.pop('stats_type', None)  # Remove if exists
                volatility = PlayerVolatility(
                    player_id=player_id,
                    stats_type=stats_type,
                    **metrics_copy
                )
                session.add(volatility)

            session.commit()

        except Exception as e:
            session.rollback()
            logger.error(f"Error saving player volatility: {e}")
            raise
        finally:
            session.close()

    def get_high_variance_players(
        self,
        stats_type: str = "batting",
        min_games: int = 20,
        limit: int = 50
    ) -> List[Tuple[Player, PlayerVolatility]]:
        """
        Get players with highest variance scores.

        Args:
            stats_type: 'batting' or 'pitching'
            min_games: Minimum games played threshold
            limit: Number of players to return

        Returns:
            List of (Player, PlayerVolatility) tuples
        """
        session = self.get_session()
        try:
            results = session.query(Player, PlayerVolatility).join(
                PlayerVolatility, Player.player_id == PlayerVolatility.player_id
            ).filter(
                PlayerVolatility.stats_type == stats_type,
                PlayerVolatility.games_played >= min_games
            ).order_by(
                PlayerVolatility.variance_score.desc()
            ).limit(limit).all()

            return results

        finally:
            session.close()

    def get_database_stats(self) -> Dict:
        """Get summary statistics about the database."""
        session = self.get_session()
        try:
            stats = {
                "total_games": session.query(Game).count(),
                "games_fetched": session.query(Game).filter_by(data_fetched=True).count(),
                "total_players": session.query(Player).count(),
                "total_player_games": session.query(PlayerGame).count(),
                "batting_performances": session.query(PlayerGame).filter_by(stats_type="batting").count(),
                "pitching_performances": session.query(PlayerGame).filter_by(stats_type="pitching").count(),
                "players_with_volatility": session.query(PlayerVolatility).count()
            }
            return stats

        finally:
            session.close()


if __name__ == "__main__":
    # Test database manager
    db = DatabaseManager()
    stats = db.get_database_stats()
    print("Database Statistics:")
    for key, value in stats.items():
        print(f"  {key}: {value}")
