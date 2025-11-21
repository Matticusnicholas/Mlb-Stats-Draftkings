#!/usr/bin/env python3
"""
Update scoring cache for all platforms (DraftKings, Underdog, Drafters).
Calculates and caches points for instant switching between scoring systems.
"""
import sys
import time
from datetime import datetime
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.database.db_manager import DatabaseManager
from src.database.models import CacheMetadata
from src.utils.multi_scoring import MultiScoringCalculator
from sqlalchemy import text


def migrate_database(db):
    """Add new columns to database if they don't exist."""
    print("🔧 Checking database schema...")

    session = db.Session()
    try:
        # Check if columns exist
        result = session.execute(text("PRAGMA table_info(player_games)"))
        columns = [row[1] for row in result.fetchall()]

        needs_migration = False
        if 'underdog_points' not in columns:
            print("  Adding underdog_points column...")
            session.execute(text("ALTER TABLE player_games ADD COLUMN underdog_points FLOAT"))
            needs_migration = True

        if 'drafters_points' not in columns:
            print("  Adding drafters_points column...")
            session.execute(text("ALTER TABLE player_games ADD COLUMN drafters_points FLOAT"))
            needs_migration = True

        if needs_migration:
            session.commit()
            print("✅ Database migration completed!")
        else:
            print("✅ Database schema is up to date")

    except Exception as e:
        session.rollback()
        print(f"❌ Migration error: {e}")
        raise
    finally:
        session.close()


def calculate_and_cache_points(db, scoring_system: str):
    """Calculate and cache points for a specific scoring system."""
    print(f"\n📊 Calculating {scoring_system.upper()} points...")

    session = db.Session()
    calculator = MultiScoringCalculator()

    try:
        start_time = time.time()

        # Get all player games
        result = session.execute(text("SELECT COUNT(*) FROM player_games"))
        total_records = result.fetchone()[0]
        print(f"  Total records to process: {total_records:,}")

        # Determine which column to update
        column_name = f"{scoring_system}_points"

        # Fetch all records in batches for processing
        batch_size = 1000
        updated_count = 0

        offset = 0
        while offset < total_records:
            # Fetch batch - get all necessary columns
            query = text("""
                SELECT id, stats_type,
                       hits, doubles, triples, home_runs, singles,
                       rbi, runs, walks, intentional_walks, hit_by_pitch,
                       stolen_bases, caught_stealing, strikeouts_batting,
                       innings_pitched, strikeouts_pitching, wins, losses, saves,
                       earned_runs, hits_allowed, walks_allowed, hit_batsmen,
                       complete_games, shutouts
                FROM player_games
                LIMIT :limit OFFSET :offset
            """)

            batch = session.execute(query, {"limit": batch_size, "offset": offset}).fetchall()

            # Calculate points for each record
            for row in batch:
                record_id = row[0]
                stats_type = row[1]

                # Create a mock player_game object with the stats
                class MockPlayerGame:
                    def __init__(self, row_data):
                        # Batting stats
                        self.hits = row_data[2]
                        self.doubles = row_data[3]
                        self.triples = row_data[4]
                        self.home_runs = row_data[5]
                        self.singles = row_data[6]
                        self.rbi = row_data[7]
                        self.runs = row_data[8]
                        self.walks = row_data[9]
                        self.intentional_walks = row_data[10]
                        self.hit_by_pitch = row_data[11]
                        self.stolen_bases = row_data[12]
                        self.caught_stealing = row_data[13]
                        self.strikeouts_batting = row_data[14]
                        # Pitching stats
                        self.innings_pitched = row_data[15]
                        self.strikeouts_pitching = row_data[16]
                        self.wins = row_data[17]
                        self.losses = row_data[18]
                        self.saves = row_data[19]
                        self.earned_runs = row_data[20]
                        self.hits_allowed = row_data[21]
                        self.walks_allowed = row_data[22]
                        self.hit_batsmen = row_data[23]
                        self.complete_games = row_data[24]
                        self.shutouts = row_data[25]
                        self.stats_type = stats_type

                mock_game = MockPlayerGame(row)
                points = calculator.recalculate_points(mock_game, scoring_system)

                # Update the record
                update_query = text(f"""
                    UPDATE player_games
                    SET {column_name} = :points
                    WHERE id = :id
                """)
                session.execute(update_query, {"points": points, "id": record_id})
                updated_count += 1

            session.commit()
            offset += batch_size

            # Progress indicator
            progress = min(100, (offset / total_records) * 100)
            print(f"  Progress: {progress:.1f}% ({offset:,}/{total_records:,})", end='\r')

        print(f"\n  ✅ Updated {updated_count:,} records")

        # Update cache metadata
        duration = time.time() - start_time
        cache_key = f"{scoring_system}_points"

        # Delete old metadata if exists
        session.execute(text("DELETE FROM cache_metadata WHERE cache_key = :key"),
                       {"key": cache_key})

        # Insert new metadata
        session.execute(text("""
            INSERT INTO cache_metadata (cache_key, last_calculated, total_records, calculation_duration)
            VALUES (:key, :calc_time, :total, :duration)
        """), {
            "key": cache_key,
            "calc_time": datetime.utcnow(),
            "total": updated_count,
            "duration": duration
        })

        session.commit()
        print(f"  ⏱️  Calculation time: {duration:.2f} seconds")

    except Exception as e:
        session.rollback()
        print(f"\n❌ Error calculating {scoring_system} points: {e}")
        raise
    finally:
        session.close()


def show_cache_status(db):
    """Show current cache status for all scoring systems."""
    print("\n📋 Cache Status:")
    print("-" * 70)

    session = db.Session()
    try:
        scoring_systems = ['draftkings', 'underdog', 'drafters']

        for system in scoring_systems:
            cache_key = f"{system}_points"

            # Check if metadata exists
            result = session.execute(
                text("SELECT last_calculated, total_records, calculation_duration FROM cache_metadata WHERE cache_key = :key"),
                {"key": cache_key}
            ).fetchone()

            if result:
                last_calc, total, duration = result
                last_calc_dt = datetime.fromisoformat(last_calc) if isinstance(last_calc, str) else last_calc
                time_ago = datetime.utcnow() - last_calc_dt

                days = time_ago.days
                hours = time_ago.seconds // 3600

                if days > 0:
                    time_str = f"{days}d {hours}h ago"
                elif hours > 0:
                    time_str = f"{hours}h ago"
                else:
                    time_str = "< 1h ago"

                print(f"  {system.upper():12} ✅ Cached ({time_str}) - {total:,} records in {duration:.1f}s")
            else:
                print(f"  {system.upper():12} ⚠️  Not cached (will recalculate live)")

    finally:
        session.close()

    print("-" * 70)


def main():
    """Main execution."""
    print("=" * 70)
    print("  MLB STATS - SCORING CACHE UPDATER")
    print("=" * 70)

    # Initialize database
    db = DatabaseManager()

    # Check if user wants to see status only
    if len(sys.argv) > 1 and sys.argv[1] == '--status':
        show_cache_status(db)
        return

    # Show current status
    show_cache_status(db)

    # Confirm update
    print("\nThis will pre-calculate and cache points for Underdog Fantasy and Drafters.")
    print("DraftKings points are already cached in the database.")
    response = input("\nProceed with cache update? (y/n): ").strip().lower()

    if response != 'y':
        print("❌ Cache update cancelled")
        return

    try:
        # Migrate database (add columns if needed)
        migrate_database(db)

        # Calculate and cache points for each system
        calculate_and_cache_points(db, 'underdog')
        calculate_and_cache_points(db, 'drafters')

        # Show updated status
        print("\n" + "=" * 70)
        print("  CACHE UPDATE COMPLETE!")
        print("=" * 70)
        show_cache_status(db)

        print("\n✨ You can now switch between scoring systems instantly!")
        print("   Use --scoring-system flag in CLI or dropdown in web UI")

    except Exception as e:
        print(f"\n❌ Error during cache update: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
