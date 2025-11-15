# MLB Best Ball Analyzer - Web Version

A Baseball Savant-style web interface for analyzing MLB players for DraftKings Best Ball snake drafts.

## Features

- **Baseball Savant-Style UI**: Clean, professional interface with percentile-based visualizations
- **Individual Stat Percentiles**: Each metric gets its own percentile bar with color gradient (blue=cold, red=hot)
- **Pre-Calculated Metrics**: All Best Ball analysis is done in advance for instant loading
- **Interactive Sorting**: Click any column header to sort
- **Responsive Design**: Works on desktop and mobile
- **Real-time Filtering**: Filter by position type, minimum games, player count

## Metrics Explained

- **BB Score**: Composite 0-100 metric combining weekly ceiling, consistency, and hot streak ability
- **Best Week**: Highest 7-day rolling window points total
- **Top3 Avg**: Average of top 3 best weeks
- **Boom%**: Percentage of weeks scoring 75th percentile or higher
- **TEAR3/TEAR4**: Multi-game hot streak rates (3+ or 4+ consecutive elite games)
- **Longest**: Longest streak of consecutive elite performances

## Setup

### 1. Install Dependencies

```bash
cd web
pip install -r requirements.txt
```

### 2. Pre-Calculate Data (First Time Only)

This analyzes all players and stores the results in the database:

```bash
python precalculate_data.py
```

This may take several minutes but only needs to be done once (or when you update your data).

### 3. Run the Web App

```bash
python app.py
```

The app will be available at: http://localhost:5000

## Usage

1. **Select Position**: Choose batting or pitching
2. **Set Filters**: Adjust minimum games and max players
3. **Load Players**: Click "Load Players" to fetch data
4. **Sort**: Click any column header to sort by that metric
5. **View Percentiles**: Colored bars show where each stat ranks (blue=low, red=high)

## API Endpoints

### GET /api/players

Get player data with Best Ball metrics.

**Query Parameters:**
- `stats_type`: 'batting' or 'pitching' (default: batting)
- `min_games`: Minimum games played (default: 20)
- `limit`: Max players to return (default: 100)
- `sort_by`: Field to sort by (default: bestball_score)

**Response:**
```json
{
  "success": true,
  "players": [...],
  "count": 100
}
```

### GET /api/player/<player_id>

Get detailed stats for a specific player.

**Query Parameters:**
- `stats_type`: 'batting' or 'pitching' (default: batting)

### GET /api/stats

Get database statistics.

## Technology Stack

- **Backend**: Flask (Python)
- **Frontend**: Vanilla JavaScript, HTML5, CSS3
- **Data**: SQLite database
- **Metrics**: NumPy for percentile calculations

## Updating Data

When you fetch new MLB data:

1. Run `python fetch_data.py` from the main project directory
2. Re-run `python precalculate_data.py` from the web directory
3. Refresh the web app

## Performance

- Pre-calculated metrics enable instant page loads
- Percentile calculations done server-side
- Optimized for 100-300 player datasets
- Sub-second API response times

## Baseball Savant Comparison

This app is inspired by Baseball Savant's percentile visualizations:
- Color-coded percentile bars for each stat
- Blue (cold/low) to red (hot/high) gradient
- Clean, data-focused interface
- Advanced metrics for fantasy analysis
