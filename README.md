# MLB DraftKings Volatility Analyzer

A comprehensive tool for analyzing MLB player volatility and building high-variance DraftKings lineups for tournament play. This system fetches 2025 MLB season data, converts box score statistics into DraftKings points, and provides advanced volatility metrics to identify players with the highest spike potential.

## 🎯 Features

### Data Collection
- Fetches complete 2025 MLB regular season schedule
- Retrieves detailed box score data for every game
- Automatic rate limiting and retry logic for API stability
- Stores all data in a local SQLite database

### DraftKings Points Calculation
- Configurable scoring rules (easily adjustable in `config/dk_scoring.json`)
- Separate calculations for batting and pitching statistics
- Handles complex metrics like innings pitched, caught stealing, complete games, etc.

### Volatility Analysis
Multiple advanced metrics for measuring player variance:

**Core Volatility Metrics:**
- Standard deviation and coefficient of variation
- Percentile analysis (25th, 75th, 90th, 95th)
- Min/max points and range
- Boom rate (% of 20+ point games)
- Bust rate (% of sub-5 point games)
- Spike rate (games above 90th percentile)

**Streakiness Analysis:**
- Longest hot and cold streaks
- Current streak identification
- Rolling z-scores
- Weekly volatility tracking

**Advanced Metrics:**
- Top 5 games concentration (% of total points)
- Composite variance score (0-100)
- Upside score (ceiling-focused metric)
- Recent form analysis (7, 14, 30-day windows)

### Roster Optimization
- Build max-variance lineups optimized for tournament upside
- Multiple optimization strategies (variance score, upside score)
- Roster evaluation with ceiling projections
- Support for generating multiple unique lineups

### GUI Interface
- Modern, user-friendly interface for analysis
- Filter players by position, games played, variance thresholds
- Sort by multiple metrics
- View detailed player statistics
- Build and export optimal lineups
- Real-time database statistics

### Visualization Tools
- Player performance timelines with rolling averages
- Score distribution histograms and box plots
- Multi-player volatility comparisons
- Weekly z-score analysis
- Boom game highlighting

## 📋 Requirements

- Python 3.8+
- See `requirements.txt` for package dependencies

## 🚀 Quick Start

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd Mlb-Stats-Draftkings
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create data directory:
```bash
mkdir -p data
```

### Usage Workflow

#### Step 1: Fetch Game Data

Fetch the 2025 MLB schedule and box scores:

```bash
# Fetch schedule only
python fetch_data.py --season 2025 --schedule-only

# Fetch schedule and all box scores
python fetch_data.py --season 2025

# Fetch limited number of games (for testing)
python fetch_data.py --season 2025 --limit 100
```

This will:
- Download all 2025 regular season games
- Fetch box score data for each game
- Calculate DraftKings points for all players
- Store everything in `data/mlb_stats.db`

**Note:** Fetching all box scores for a full season takes several hours due to API rate limiting. Start with `--limit 100` for testing.

#### Step 2: Analyze Volatility

Once you have data, analyze player volatility:

```bash
# Analyze batting volatility
python analyze_volatility.py --stats-type batting --min-games 20

# Analyze pitching volatility
python analyze_volatility.py --stats-type pitching --min-games 10

# Generate report without re-analyzing
python analyze_volatility.py --skip-analysis --top-n 50

# Build a sample max-variance roster
python analyze_volatility.py --build-roster --min-variance 35.0
```

This will:
- Calculate volatility metrics for all eligible players
- Generate a report of top high-variance players
- Optionally build optimal rosters

#### Step 3: Use the GUI

Launch the interactive GUI:

```bash
python run_gui.py
```

The GUI allows you to:
- Filter players by various criteria
- Sort by different volatility metrics
- View detailed player statistics
- Build custom max-variance rosters
- Export lineups for DraftKings

## 📊 Understanding the Metrics

### Variance Score (0-100)
Composite metric combining multiple volatility indicators. Higher = more volatile/better for tournaments.

**Components:**
- Coefficient of variation (25% weight)
- Top 5 games concentration (20% weight)
- Spike rate (20% weight)
- Boom rate (20% weight)
- Points range (15% weight)

### Upside Score (0-100)
Focuses on ceiling potential and big-game capability.

**Components:**
- Maximum points achieved (40% weight)
- 95th percentile performance (35% weight)
- Boom rate (25% weight)

### Boom Rate
Percentage of games with 20+ DraftKings points. Indicates consistency of spike performances.

### Top 5 Games %
What percentage of total season points came from the player's top 5 games. Higher = more concentrated spikes.

### Z-Score
Standard deviations above/below rolling mean. Helps identify current hot/cold streaks.

## 🗂️ Project Structure

```
Mlb-Stats-Draftkings/
├── config/
│   └── dk_scoring.json          # DraftKings scoring configuration
├── data/
│   └── mlb_stats.db            # SQLite database (created automatically)
├── src/
│   ├── api/
│   │   └── mlb_api.py          # MLB Stats API client
│   ├── database/
│   │   ├── models.py           # Database schema
│   │   └── db_manager.py       # Database operations
│   ├── analytics/
│   │   ├── volatility_analyzer.py   # Volatility calculations
│   │   └── roster_optimizer.py      # Lineup optimization
│   ├── utils/
│   │   ├── dk_calculator.py    # DK points calculator
│   │   └── visualizations.py   # Plotting utilities
│   └── gui/
│       └── main_window.py      # GUI application
├── fetch_data.py               # Data fetching script
├── analyze_volatility.py       # Analysis script
├── run_gui.py                  # GUI launcher
├── requirements.txt            # Python dependencies
└── README.md                   # This file
```

## 🔧 Configuration

### DraftKings Scoring Rules

Edit `config/dk_scoring.json` to adjust scoring rules:

```json
{
  "batting": {
    "1B": 3,
    "2B": 5,
    "3B": 8,
    "HR": 10,
    "RBI": 2,
    "R": 2,
    "BB": 2,
    "HBP": 2,
    "SB": 5,
    "CS": -2
  },
  "pitching": {
    "IP": 2.25,
    "SO": 2,
    "W": 4,
    "ER": -2,
    "H": -0.6,
    "BB": -0.6,
    "HBP": -0.6,
    "CG": 2.5,
    "CGSO": 2.5,
    "NH": 5
  }
}
```

## 📈 Example Analysis Workflow

```bash
# 1. Fetch first 500 games for testing
python fetch_data.py --season 2025 --limit 500

# 2. Analyze batting volatility
python analyze_volatility.py --stats-type batting --min-games 15 --top-n 100

# 3. Build sample roster with high-variance players
python analyze_volatility.py --skip-analysis --build-roster --min-variance 30

# 4. Launch GUI for interactive analysis
python run_gui.py
```

## 💡 Tips for Tournament Play

1. **High Variance is Key**: In large-field GPPs, you need differentiation. High variance players give you spike weeks that others miss.

2. **Balance Ceiling and Floor**: While variance is important, players who are too bust-prone hurt your chances. Look for boom rate > 15% and bust rate < 30%.

3. **Stack Correlated Players**: When one team's hitters spike, multiple players spike together. The correlation analysis helps identify stacking opportunities.

4. **Recent Form Matters**: Use the last 7/14 day metrics to identify players entering hot streaks.

5. **Diversity in Multi-Entry**: If building multiple lineups, ensure sufficient uniqueness between rosters.

## 🔍 Advanced Usage

### Custom Volatility Analysis

```python
from src.database import DatabaseManager
from src.analytics import VolatilityAnalyzer

db = DatabaseManager()
analyzer = VolatilityAnalyzer(db)

# Analyze specific player
metrics = analyzer.calculate_player_volatility(
    player_id=12345,
    stats_type="batting",
    min_games=20
)

print(f"Variance Score: {metrics['variance_score']}")
print(f"Boom Rate: {metrics['boom_rate']}%")
```

### Visualizations

```python
from src.utils import PerformanceVisualizer

viz = PerformanceVisualizer(db)

# Plot player timeline
viz.plot_player_timeline(player_id=12345, stats_type="batting")

# Compare multiple players
viz.plot_volatility_comparison([12345, 67890, 11111])

# Weekly volatility
viz.plot_weekly_volatility(player_id=12345)
```

## 🤝 Contributing

Suggestions for enhancements:
- Add salary cap optimization (requires DraftKings salary data)
- Implement position eligibility constraints
- Add weather/ballpark factor adjustments
- Create Monte Carlo simulations for lineup optimization
- Add opponent strength adjustments
- Implement correlation matrices for team stacking

## 📝 License

This project is for educational and research purposes.

## ⚠️ Disclaimer

This tool is for analysis and research purposes only. Always do your own research before entering DFS contests. Past performance does not guarantee future results.

## 🐛 Troubleshooting

**Issue: "No games to fetch"**
- Make sure you ran `fetch_data.py` with `--schedule-only` first
- Check that the season year is correct (2025)

**Issue: "Insufficient players for roster building"**
- Lower the `--min-variance` threshold
- Lower the `--min-games` threshold
- Ensure you have fetched enough game data

**Issue: API rate limiting errors**
- The script includes automatic retry logic
- If persistent, increase `rate_limit_delay` in `MLBStatsAPI.__init__`

**Issue: Database errors**
- Delete `data/mlb_stats.db` and start fresh
- Ensure data directory exists and is writable

## 📧 Support

For questions or issues, please open an issue on GitHub.
