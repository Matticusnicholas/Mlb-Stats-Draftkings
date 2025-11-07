#!/usr/bin/env python3
"""
Launch the GUI application.
"""
import sys
import logging

from src.gui.main_window import MLBVolatilityGUI

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


def main():
    """Main entry point for GUI."""
    print("Launching MLB DraftKings Volatility Analyzer GUI...")

    try:
        app = MLBVolatilityGUI(db_path="data/mlb_stats.db")
        app.run()
    except KeyboardInterrupt:
        print("\nExiting...")
        sys.exit(0)
    except Exception as e:
        print(f"Error launching GUI: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
