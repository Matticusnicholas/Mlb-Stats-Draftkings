"""
Database models for MLB statistics storage.
"""
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Date, DateTime,
    Boolean, ForeignKey, Index, UniqueConstraint
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from datetime import datetime

Base = declarative_base()


class Game(Base):
    """Game information."""

    __tablename__ = "games"

    game_pk = Column(Integer, primary_key=True)
    game_date = Column(DateTime, nullable=False, index=True)
    game_type = Column(String(5), nullable=False)  # R, S, P
    away_team_id = Column(Integer, nullable=False)
    away_team_name = Column(String(100))
    home_team_id = Column(Integer, nullable=False)
    home_team_name = Column(String(100))
    double_header = Column(String(1), default="N")
    game_number = Column(Integer, default=1)
    data_fetched = Column(Boolean, default=False)
    fetch_date = Column(DateTime)

    # Relationships
    player_games = relationship("PlayerGame", back_populates="game", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_games_date", game_date),
    )

    def __repr__(self):
        return f"<Game(game_pk={self.game_pk}, date={self.game_date})>"


class Player(Base):
    """Player information."""

    __tablename__ = "players"

    player_id = Column(Integer, primary_key=True)
    player_name = Column(String(200), nullable=False)
    last_updated = Column(DateTime, default=datetime.utcnow)

    # Relationships
    player_games = relationship("PlayerGame", back_populates="player", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Player(id={self.player_id}, name={self.player_name})>"


class PlayerGame(Base):
    """Individual player game statistics and DK points."""

    __tablename__ = "player_games"

    id = Column(Integer, primary_key=True, autoincrement=True)
    game_pk = Column(Integer, ForeignKey("games.game_pk"), nullable=False)
    player_id = Column(Integer, ForeignKey("players.player_id"), nullable=False)
    team_id = Column(Integer, nullable=False)
    team_name = Column(String(100))
    position = Column(String(10))
    stats_type = Column(String(20), nullable=False)  # batting or pitching

    # Multi-platform points (cached for performance)
    dk_points = Column(Float, nullable=False)
    underdog_points = Column(Float)
    drafters_points = Column(Float)

    # Batting stats
    at_bats = Column(Integer)
    hits = Column(Integer)
    singles = Column(Integer)
    doubles = Column(Integer)
    triples = Column(Integer)
    home_runs = Column(Integer)
    rbi = Column(Integer)
    runs = Column(Integer)
    walks = Column(Integer)
    intentional_walks = Column(Integer)
    hit_by_pitch = Column(Integer)
    stolen_bases = Column(Integer)
    caught_stealing = Column(Integer)
    strikeouts_batting = Column(Integer)

    # Pitching stats
    innings_pitched = Column(Float)
    strikeouts_pitching = Column(Integer)
    wins = Column(Integer)
    losses = Column(Integer)
    saves = Column(Integer)
    earned_runs = Column(Integer)
    hits_allowed = Column(Integer)
    walks_allowed = Column(Integer)
    hit_batsmen = Column(Integer)
    complete_games = Column(Integer)
    shutouts = Column(Integer)

    # Relationships
    game = relationship("Game", back_populates="player_games")
    player = relationship("Player", back_populates="player_games")

    __table_args__ = (
        UniqueConstraint("game_pk", "player_id", "stats_type", name="uix_game_player_statstype"),
        Index("ix_player_games_player_id", player_id),
        Index("ix_player_games_game_pk", game_pk),
    )

    def __repr__(self):
        return f"<PlayerGame(game={self.game_pk}, player={self.player_id}, pts={self.dk_points})>"


class PlayerVolatility(Base):
    """Aggregated volatility metrics for players."""

    __tablename__ = "player_volatility"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(Integer, ForeignKey("players.player_id"), nullable=False, unique=True)
    stats_type = Column(String(20), nullable=False)  # batting or pitching

    # Basic stats
    games_played = Column(Integer)
    total_points = Column(Float)
    mean_points = Column(Float)
    median_points = Column(Float)

    # Volatility metrics
    std_dev = Column(Float)
    coefficient_of_variation = Column(Float)
    min_points = Column(Float)
    max_points = Column(Float)
    points_range = Column(Float)

    # Percentiles
    percentile_25 = Column(Float)
    percentile_75 = Column(Float)
    percentile_90 = Column(Float)
    percentile_95 = Column(Float)

    # Spike metrics
    top5_games_total = Column(Float)
    top5_games_pct = Column(Float)  # % of total points from top 5 games
    spike_rate = Column(Float)  # % of games above 90th percentile
    boom_rate = Column(Float)  # % of games with 20+ points
    bust_rate = Column(Float)  # % of games with <5 points

    # Streakiness
    longest_hot_streak = Column(Integer)
    longest_cold_streak = Column(Integer)
    current_streak_type = Column(String(10))  # hot, cold, neutral
    current_streak_length = Column(Integer)

    # Recent form (last 7, 14, 30 days)
    last7_mean = Column(Float)
    last14_mean = Column(Float)
    last30_mean = Column(Float)
    last7_std = Column(Float)
    last14_std = Column(Float)
    last30_std = Column(Float)

    # Correlation with high-variance
    variance_score = Column(Float)  # Custom composite score
    upside_score = Column(Float)  # Weighted toward ceiling games

    last_updated = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_volatility_variance_score", variance_score.desc()),
        Index("ix_volatility_player", player_id),
    )

    def __repr__(self):
        return f"<PlayerVolatility(player={self.player_id}, var_score={self.variance_score})>"


class CacheMetadata(Base):
    """Track when cached data was last calculated."""

    __tablename__ = "cache_metadata"

    cache_key = Column(String(100), primary_key=True)  # e.g., 'underdog_points', 'drafters_points'
    last_calculated = Column(DateTime, nullable=False)
    total_records = Column(Integer)
    calculation_duration = Column(Float)  # seconds

    def __repr__(self):
        return f"<CacheMetadata(key={self.cache_key}, last_calculated={self.last_calculated})>"


def create_database(db_path: str = "data/mlb_stats.db"):
    """
    Create database and all tables.

    Args:
        db_path: Path to SQLite database file
    """
    import os
    # Create parent directory if it doesn't exist
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    Base.metadata.create_all(engine)
    return engine


def get_session(db_path: str = "data/mlb_stats.db"):
    """
    Get a database session.

    Args:
        db_path: Path to SQLite database file

    Returns:
        SQLAlchemy session
    """
    import os
    # Create parent directory if it doesn't exist
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    Session = sessionmaker(bind=engine)
    return Session()


if __name__ == "__main__":
    # Create database (directory is created automatically)
    engine = create_database()
    print("Database created successfully!")
