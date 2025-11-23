# MLB Multi-Platform Best Ball Analyzer

A comprehensive tool for analyzing MLB player performance for **Best Ball snake drafts** across multiple fantasy platforms. This system fetches 2025 MLB season data, calculates platform-specific fantasy points, and provides advanced volatility metrics optimized for best ball formats using rolling 7-day windows.

**Perfect for:** Best ball snake drafts where you need players who go on multi-game tears and have monster weekly ceilings.

**Platforms Supported:** DraftKings, Underdog Fantasy, Drafters

## 🎯 Features

### Multi-Platform Scoring with Instant Switching 🆕
- **Three scoring systems**: DraftKings, Underdog Fantasy, Drafters
- **Pre-calculated caching**: Cache all 70k+ game records for instant switching (~12 seconds one-time setup)
- **Dynamic rankings**: Rankings reorder based on platform-specific scoring rules
- **Cache status tracking**: Always know when your data was last calculated
- Switch between platforms instantly in both CLI and web UI

### Combined Player Rankings 🆕
- **Unified rankings**: View pitchers and hitters ranked together by Best Ball Score
- **Position indicators**: Easily identify BAT vs PIT in combined view
- **Natural weighting**: Hitters dominate due to higher game frequency (as expected in best ball)
- **Platform-specific**: Rankings change dramatically based on scoring system

### Workhorse Metrics for Pitchers 🆕
Specialized metrics for innings-eating starting pitchers (3+ IP games only):
- **Workhorse Score (0-100)**: Composite reliability metric
  - Durability (30%): Total starts vs. 30-start benchmark
  - IP/Start (30%): Average innings per start (4-7 IP scale)
  - Quality Start Rate (20%): Percentage of 6+ IP starts
  - Consistency (10%): Coefficient of variation inverse
  - Floor (10%): Minimum points reliability
- **Quality Start %**: Percentage of starts with 6+ IP
- **Deep Start %**: Percentage of starts with 7+ IP
- **Total Starts**: Season durability indicator

Perfect for **8IF/8OF/4P** draft strategies where pitchers provide floor while hitters provide ceiling.

### Best Ball Weekly Analysis
Optimized for Best Ball where your best scores auto-count each week:

- **Rolling 7-day windows** - Analyzes all possible 7-day periods, not fixed weeks
- **TEAR metrics** - Identifies players who go on 2, 3, 4, or 5+ game hot streaks
- **Best week ceiling** - Finds players with the highest 7-day rolling totals
- **Boom week rate** - How often players have elite 7-day periods
- **Top weeks concentration** - Players whose points come from spike weeks (perfect for best ball!)
- **Best Ball Score** - Composite metric (0-100) optimized for weekly formats
- **USEFUL metrics** - Points from "starting-worthy" weeks (70th percentile threshold)

### Web Interface 🆕
Modern Flask-based web UI with full feature access:
- **Scoring system dropdown**: Instantly switch between DraftKings, Underdog, Drafters
- **Combined rankings option**: View all players ranked together
- **Workhorse columns**: Automatically appear for pitcher analysis
- **Export button**: Download rankings as CSV
- **Real-time filtering**: Search by name, filter by position, set minimum games
- **Responsive design**: Clean, Baseball Savant-inspired interface
- **Cache integration**: Uses pre-calculated points for instant results

### Export Functionality 🆕
- **CSV export**: Compatible with Excel and drafting tools
- **JSON export**: Structured data for custom integrations
- **Platform-specific**: Export includes active scoring system in filename
- **All metrics included**: Complete player data with workhorse metrics for pitchers
- Available in both CLI (`--export`) and web UI (Export CSV button)

### Data Collection
- Fetches complete 2025 MLB regular season schedule
- Retrieves detailed box score data for every game
- Automatic rate limiting and retry logic for API stability
- Stores all data in a local SQLite database
- Multi-platform point calculation cached for performance

### DraftKings Points Calculation
- Configurable scoring rules (easily adjustable in `config/`)
- Separate calculations for batting and pitching statistics
- Handles complex metrics like innings pitched, quality starts, etc.
- **NEW**: Underdog Fantasy and Drafters scoring configurations

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

### Desktop GUI Interface
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

**Note:** The `data` directory will be created automatically when you first run the scripts.

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

**Note:** Fetching all box scores takes 5-10 minutes for the full season.

#### Step 2: Pre-Calculate Multi-Platform Scoring (Recommended) 🆕

Cache points for all platforms to enable instant switching:

```bash
# Pre-calculate Underdog Fantasy and Drafters points (~12 seconds)
python update_scoring_cache.py

# Check cache status anytime
python update_scoring_cache.py --status
```

This one-time setup calculates and caches ~70,000 game records for instant platform switching!

```
📋 Cache Status:
----------------------------------------------------------------------
  DRAFTKINGS   ✅ Already cached in database
  UNDERDOG     ✅ Cached (< 1h ago) - 69,727 records in 6.3s
  DRAFTERS     ✅ Cached (< 1h ago) - 69,727 records in 6.4s
----------------------------------------------------------------------
```

#### Step 3: Web Interface (Easiest Option) 🆕

Launch the modern web interface:

```bash
python web/app.py
```

Then open http://localhost:5000 in your browser.

**Web UI Features:**
- Dropdown to switch between DraftKings, Underdog Fantasy, Drafters
- Combined Rankings option to view all players together
- Workhorse metrics automatically appear for pitchers
- Export CSV button to download rankings
- Real-time filtering and search
- Clean, responsive design

#### Step 4: Best Ball Analysis via CLI

Analyze players using rolling 7-day windows for best ball:

```bash
# Cache status always shown before analysis
python analyze_bestball.py --cache-status

# Get top 50 best ball hitters (DraftKings scoring)
python analyze_bestball.py --stats-type batting --min-games 20 --top-n 50

# Get top 25 best ball pitchers (Underdog Fantasy scoring)
python analyze_bestball.py --stats-type pitching --min-games 10 --top-n 25 --scoring-system underdog

# Combined rankings (all players ranked together)
python analyze_bestball.py --stats-type combined --top-n 100 --scoring-system drafters

# Export to CSV
python analyze_bestball.py --stats-type batting --export rankings.csv --scoring-system underdog

# Detailed breakdown for specific player
python analyze_bestball.py --player-id 660271 --stats-type batting
```

This will show:
- **Best Ball Score** - Composite weekly performance metric
- **Best Week** - Highest 7-day rolling window DK points
- **Top 3 Weeks Average** - Typical ceiling weeks
- **Boom Week Rate** - % of elite 7-day periods
- **TEAR Metrics** - Multi-game hot streak rates (TEAR3, TEAR4, etc.)
- **Workhorse Metrics** - (Pitchers only) Innings-eating reliability scores

#### Step 5: Daily Game Volatility Analysis (Optional)

For general volatility analysis (game-by-game):

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

#### Step 6: Desktop GUI (Alternative Interface)

Launch the interactive desktop GUI:

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

### Best Ball Metrics (Rolling 7-Day Windows)

#### Best Ball Score (0-100)
Composite metric optimized for Best Ball formats. Higher = better for weekly scoring.

**Components:**
- USEFUL concentration (25%) - % of points from starting-worthy weeks
- USEFUL frequency (20%) - How often player has starting-worthy weeks
- Boom week rate (20%) - % of weeks in 90th percentile+
- TEAR streaks (15%) - Multi-game hot streak ability
- Best week percentile (10%) - Elite ceiling indicator
- Top 5 concentration (10%) - Spike potential

#### USEFUL Metrics 🆕
Points from "starting-worthy" weeks only (70th percentile threshold):
- **USEFUL Points**: Total points from elite weeks only
- **USEFUL Concentration**: % of total points from elite weeks
- **USEFUL Frequency**: % of weeks that qualify as starting-worthy

**Why it matters:** In best ball, you only care about weeks where the player would actually start. USEFUL metrics ignore mediocre weeks entirely.

#### Workhorse Score (0-100) - Pitchers Only 🆕
Composite reliability metric for innings-eating starting pitchers:

**Components:**
- Durability (30%) - Total starts vs 30-start benchmark
- IP/Start (30%) - Average innings per start (4-7 IP scale)
- Quality Start Rate (20%) - % of starts with 6+ IP
- Consistency (10%) - Inverse coefficient of variation
- Floor (10%) - Minimum points reliability

**Strategy:** Perfect for 8IF/8OF/4P drafts where you need 4 reliable pitchers for floor while hitters provide ceiling.

#### TEAR Metrics
Measures likelihood of going on multi-game hot streaks:

- **TEAR2**: Rate of 2+ consecutive hot games (per 100 games)
- **TEAR3**: Rate of 3+ consecutive hot games (per 100 games)
- **TEAR4**: Rate of 4+ consecutive hot games (per 100 games)
- **TEAR5**: Rate of 5+ consecutive hot games (per 100 games)

A "hot game" is defined as 75th percentile or better for that player.

**Why it matters for Best Ball:** When a player goes on a tear, multiple hot games cluster in the same week, creating monster weekly totals that auto-start.

#### Best Week
The highest 7-day rolling window points total. This is the player's absolute ceiling week.

#### Top 3/5 Weeks Average
Average points of the player's top 3 or 5 rolling 7-day windows. Shows typical ceiling performance.

#### Boom Week Rate
Percentage of 7-day windows in the 90th percentile or better. High boom rate = consistent elite weeks.

---

### Platform Scoring Differences 🆕

Rankings vary significantly by platform due to different scoring rules:

**DraftKings:**
- IP: 2.25, SO: 2, W: 4, ER: -2
- Favors volume pitchers with strikeouts

**Underdog Fantasy:**
- IP: 3, SO: 3, W: 5, QS: 5, ER: -3
- Quality Start bonus (6+ IP, ≤3 ER) rewards consistency
- Higher IP value favors innings eaters
- Top pitcher can differ dramatically (e.g., Joe Ryan #1 Underdog, Carlos Rodón #1 DK)

**Drafters:**
- Currently uses DraftKings scoring (public scoring rules not available)
- Will be updated when official rules are published

---

### Daily Game Metrics (Optional - Less relevant for Best Ball)

#### Variance Score (0-100)
Composite metric combining multiple volatility indicators. Higher = more volatile/better for tournaments.

**Components:**
- Coefficient of variation (25% weight)
- Top 5 games concentration (20% weight)
- Spike rate (20% weight)
- Boom rate (20% weight)
- Points range (15% weight)

#### Upside Score (0-100)
Focuses on ceiling potential and big-game capability.

**Components:**
- Maximum points achieved (40% weight)
- 95th percentile performance (35% weight)
- Boom rate (25% weight)

#### Boom Rate
Percentage of games with 20+ fantasy points. Indicates consistency of spike performances.

#### Top 5 Games %
What percentage of total season points came from the player's top 5 games. Higher = more concentrated spikes.

#### Z-Score
Standard deviations above/below rolling mean. Helps identify current hot/cold streaks.

## 🗂️ Project Structure

```
Mlb-Stats-Draftkings/
├── config/
│   ├── dk_scoring.json          # DraftKings scoring configuration
│   ├── underdog_scoring.json    # Underdog Fantasy scoring 🆕
│   └── drafters_scoring.json    # Drafters scoring 🆕
├── data/
│   └── mlb_stats.db            # SQLite database (created automatically)
├── src/
│   ├── api/
│   │   └── mlb_api.py          # MLB Stats API client
│   ├── database/
│   │   ├── models.py           # Database schema (multi-platform points)
│   │   └── db_manager.py       # Database operations
│   ├── analytics/
│   │   ├── weekly_analyzer.py       # Best Ball weekly analysis (TEAR, USEFUL, Workhorse)
│   │   ├── volatility_analyzer.py   # Daily game volatility calculations
│   │   └── roster_optimizer.py      # Lineup optimization
│   ├── utils/
│   │   ├── dk_calculator.py         # DK points calculator
│   │   ├── multi_scoring.py         # Multi-platform scoring 🆕
│   │   ├── export_rankings.py       # CSV/JSON export 🆕
│   │   └── visualizations.py        # Plotting utilities
│   └── gui/
│       └── main_window.py      # Desktop GUI application
├── web/                        # Web interface 🆕
│   ├── app.py                 # Flask backend
│   ├── templates/
│   │   └── index.html         # Web UI template
│   └── static/
│       ├── css/
│       │   └── styles.css     # Web styling
│       └── js/
│           └── app.js         # Frontend JavaScript
├── fetch_data.py               # Data fetching script
├── analyze_bestball.py         # Best Ball analysis (multi-platform)
├── analyze_volatility.py       # Daily volatility analysis
├── update_scoring_cache.py     # Pre-calculate all scoring systems 🆕
├── run_gui.py                  # Desktop GUI launcher
├── requirements.txt            # Python dependencies
└── README.md                   # This file
```

## 🔧 Configuration

### Scoring Rules

The tool supports three fantasy platforms with different scoring configurations:

#### DraftKings (`config/dk_scoring.json`)
```json
{
  "batting": {
    "1B": 3, "2B": 5, "3B": 8, "HR": 10,
    "RBI": 2, "R": 2, "BB": 2, "HBP": 2, "SB": 5, "CS": -2
  },
  "pitching": {
    "IP": 2.25, "SO": 2, "W": 4, "ER": -2,
    "H": -0.6, "BB": -0.6, "HBP": -0.6,
    "CG": 2.5, "CGSO": 2.5, "NH": 5
  }
}
```

#### Underdog Fantasy (`config/underdog_scoring.json`)
```json
{
  "batting": {
    "1B": 3, "2B": 6, "3B": 8, "HR": 10,
    "RBI": 2, "R": 2, "BB": 3, "HBP": 3, "SB": 4
  },
  "pitching": {
    "IP": 3, "SO": 3, "W": 5, "QS": 5, "ER": -3
  }
}
```

Note: Underdog includes a Quality Start bonus (6+ IP, ≤3 ER = +5 points)

#### Drafters (`config/drafters_scoring.json`)
Currently uses DraftKings scoring as placeholder. Will be updated when official rules are available.

You can edit these files to match any platform's scoring rules!

## 📈 Example Best Ball Workflow

### Complete Multi-Platform Analysis

```bash
# 1. Fetch all 2025 data (takes 5-10 minutes, one-time)
python fetch_data.py --season 2025

# 2. Pre-calculate all scoring systems (~12 seconds, one-time)
python update_scoring_cache.py

# 3. Launch web interface for interactive analysis
python web/app.py
# Open http://localhost:5000 and use dropdown to switch platforms

# OR use CLI for quick analysis:

# 4. DraftKings best ball hitters
python analyze_bestball.py --stats-type batting --top-n 50 --scoring-system draftkings

# 5. Underdog Fantasy pitchers with workhorse metrics
python analyze_bestball.py --stats-type pitching --top-n 25 --scoring-system underdog

# 6. Combined rankings (all players) for Drafters
python analyze_bestball.py --stats-type combined --top-n 100 --scoring-system drafters

# 7. Export Underdog rankings to CSV for external use
python analyze_bestball.py --stats-type batting --export underdog_hitters.csv --scoring-system underdog

# 8. Deep dive on specific player across all platforms
python analyze_bestball.py --player-id 660271 --stats-type batting --scoring-system draftkings
python analyze_bestball.py --player-id 660271 --stats-type batting --scoring-system underdog
python analyze_bestball.py --player-id 660271 --stats-type batting --scoring-system drafters
```

### Check Cache Status

```bash
# View when each platform was last cached
python analyze_bestball.py --cache-status

# OR
python update_scoring_cache.py --status
```

Output:
```
======================================================================
  SCORING CACHE STATUS
======================================================================
  DRAFTKINGS   ✅ Already cached in database
  UNDERDOG     ✅ Cached (2d 5h ago) - 69,727 records
  DRAFTERS     ✅ Cached (2d 5h ago) - 69,727 records
======================================================================
TIP: Run 'python update_scoring_cache.py' to refresh cache
```

## 💡 Tips for Best Ball Snake Drafts

### General Strategy

1. **Prioritize Weekly Ceilings**: Ignore bust rate completely - bad games don't count in best ball. Focus on Best Week and Top 3 Weeks Average.

2. **TEAR Metrics Are Gold**: Players with high TEAR3/TEAR4 rates go on hot streaks where multiple games cluster in the same week = monster weekly totals.

3. **Top Weeks Concentration**: Look for players with 30%+ of points from top 5 weeks. These spike-y players are perfect for best ball.

4. **Best Ball Score > 60**: Target players with Best Ball Score above 60 for your core roster. These have proven weekly upside.

5. **Volume Matters**: Players with more games per week (everyday players vs. platoon) have higher weekly ceilings just from volume.

6. **USEFUL Metrics**: Focus on players with high USEFUL concentration - they produce starting-worthy weeks consistently.

### Platform-Specific Tips 🆕

#### Underdog Fantasy
- **Quality Start bonus** makes consistent pitchers more valuable
- **Higher IP scoring** (3 vs DK's 2.25) rewards innings eaters
- **Workhorse pitchers shine**: Look for high QS% and IP/Start
- **Joe Ryan effect**: Some pitchers rank much higher on Underdog than DK

#### DraftKings
- **Strikeouts matter more** (2 pts each)
- **Win bonus** is lower (4 vs Underdog's 5)
- **Negative hits allowed** (-0.6) penalizes blow-ups
- Favors power pitchers over volume

#### Strategy: 8IF/8OF/4P Draft 🆕
- **Innings-eaters for pitchers**: Use Workhorse Score to find reliable floor
  - Target: Workhorse Score > 70, QS% > 50%, Total Starts > 25
- **Ceiling hunters for hitters**: Use Best Ball Score + TEAR metrics
  - Target: BB Score > 65, TEAR3 > 3.0, Best Week > 80
- **Why it works**: 4 reliable pitchers provide weekly floor, 16 hitters provide ceiling/spikes

## 🔍 Advanced Usage

### Python API

#### Multi-Platform Analysis

```python
from src.database.db_manager import DatabaseManager
from src.analytics.weekly_analyzer import WeeklyAnalyzer

db = DatabaseManager()

# Analyze with DraftKings scoring
dk_analyzer = WeeklyAnalyzer(db, scoring_system='draftkings')
dk_pitchers = dk_analyzer.get_top_bestball_players(
    stats_type="pitching",
    min_games=20,
    limit=25
)

# Analyze with Underdog scoring
ud_analyzer = WeeklyAnalyzer(db, scoring_system='underdog')
ud_pitchers = ud_analyzer.get_top_bestball_players(
    stats_type="pitching",
    min_games=20,
    limit=25
)

# Compare rankings
print(f"DK Top Pitcher: {dk_pitchers[0]['player_name']}")
print(f"Underdog Top Pitcher: {ud_pitchers[0]['player_name']}")
```

#### Workhorse Metrics

```python
# Calculate workhorse metrics for a pitcher
workhorse = dk_analyzer.calculate_workhorse_metrics(
    player_id=608566,  # Garrett Crochet
    stats_type="pitching"
)

print(f"Workhorse Score: {workhorse['workhorse_score']:.1f}")
print(f"Quality Start %: {workhorse['quality_start_rate']:.1f}%")
print(f"Avg IP/Start: {workhorse['avg_ip_per_start']:.2f}")
print(f"Total Starts: {workhorse['total_starts']}")
```

#### Export Rankings

```python
from src.utils.export_rankings import RankingsExporter

# Export to CSV
RankingsExporter.to_csv(
    players=ud_pitchers,
    filepath="underdog_pitchers.csv",
    include_workhorse=True
)

# Export to JSON
RankingsExporter.to_json(
    players=dk_pitchers,
    filepath="dk_pitchers.json"
)
```

### Custom Volatility Analysis

```python
from src.analytics.volatility_analyzer import VolatilityAnalyzer

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
from src.utils.visualizations import PerformanceVisualizer

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
- Add salary cap optimization (requires platform salary data)
- Implement position eligibility constraints
- Add weather/ballpark factor adjustments
- Create Monte Carlo simulations for lineup optimization
- Add opponent strength adjustments
- Implement correlation matrices for team stacking
- Add more fantasy platforms (Yahoo, ESPN, etc.)
- Historical season comparison across platforms

## 📝 License

This project is for educational and research purposes.

## ⚠️ Disclaimer

This tool is for analysis and research purposes only. Always do your own research before entering DFS contests. Past performance does not guarantee future results.

## 🐛 Troubleshooting

**Issue: "No games to fetch"**
- Make sure you ran `fetch_data.py` with `--schedule-only` first
- Check that the season year is correct (2025)

**Issue: Slow platform switching**
- Run `python update_scoring_cache.py` to pre-calculate all platforms
- Check cache status with `--cache-status` flag

**Issue: "Cache not available"**
- The tool will calculate live (slower but functional)
- Run `python update_scoring_cache.py` to set up cache for instant switching

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
- If migrating from old version, the cache script will auto-migrate schema

**Issue: Web interface not loading**
- Ensure Flask is installed: `pip install flask flask-cors`
- Check that port 5000 is not in use
- Try accessing http://127.0.0.1:5000 instead of localhost

## 📧 Support

For questions or issues, please open an issue on GitHub.

---

**Last Updated:** January 2025 - Added multi-platform scoring, workhorse metrics, combined rankings, and web interface.
