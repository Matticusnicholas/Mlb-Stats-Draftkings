# MLB Best Ball Analyzer - Web Version Quick Start

Your own Baseball Savant for Best Ball MLB! 🎯⚾

## What You Get

A beautiful web interface that shows **individual percentile bars for each stat** - just like Baseball Savant:

- **BB Score**: 75.3 ██████████░░ (75th percentile - red/hot)
- **TEAR3**: 45.2 ▒▒▒▒▒░░░░░ (45th percentile - neutral)
- **Best Week**: 15.8 ░░········ (15th percentile - blue/cold)

Each stat is independently ranked with color-coded bars:
- 🔴 **Red (Hot)**: 80-100th percentile
- 🟠 **Orange (Warm)**: 60-80th percentile
- 🟡 **Yellow (Average)**: 40-60th percentile
- 🔵 **Blue (Cool)**: 0-40th percentile

## Quick Start (3 Steps)

### 1. Pre-Calculate All Metrics (First Time Only)

This analyzes all players in your database and stores the results. Only needs to be done once:

```bash
python web/precalculate_data.py
```

This will:
- Analyze all batting players (may take 5-10 minutes)
- Analyze all pitching players
- Store all Best Ball metrics in the database
- Print progress as it goes

**Note**: This only needs to be re-run when you fetch new MLB data.

### 2. Start the Web Server

```bash
cd web
python app.py
```

Or use the convenience script:

```bash
./web/run.sh
```

### 3. Open in Browser

Visit: **http://localhost:5000**

That's it! 🎉

## Using the Web App

1. **Select Position**: Batting or Pitching
2. **Set Filters**:
   - Min Games (default: 20)
   - Max Players to display (50, 100, 200, or 300)
3. **Click "Load Players"**
4. **Sort**: Click any column header to sort
5. **View Percentiles**: Each stat shows its own percentile bar

## Features

### Baseball Savant-Style Percentile Bars
Every stat gets its own independent percentile ranking:
- TEAR3 might be 90th percentile (██████████ red)
- While TEAR4 is 40th percentile (▒▒▒▒······ yellow)
- Each bar shows exactly where that player ranks in that specific metric

### Interactive Sorting
Click any column header to sort:
- First click: Descending (▼)
- Second click: Ascending (▲)
- Third click: Back to original order

### Real-Time Filtering
- Switch between batting and pitching instantly
- Adjust minimum games threshold
- Control how many players to display
- Click "Refresh Data" to reload with new filters

## API Endpoints (For Advanced Users)

### Get Players
```bash
GET /api/players?stats_type=batting&min_games=20&limit=100
```

### Get Player Detail
```bash
GET /api/player/123?stats_type=batting
```

### Get Database Stats
```bash
GET /api/stats
```

## Metrics Explained

- **BB Score**: Composite 0-100 metric (25% best week + 20% top3 avg + 20% boom rate + 20% TEAR + 15% concentration)
- **Best Week**: Highest 7-day rolling window points
- **Top3 Avg**: Average of top 3 best weeks
- **Boom%**: Percentage of weeks scoring 75th percentile+
- **TEAR3/TEAR4**: Multi-game hot streak rates (3+ or 4+ consecutive elite games)
- **Longest**: Longest streak of elite performances

## Performance Tips

- Pre-calculation makes the web app **lightning fast**
- 100 players load in ~200ms
- 300 players load in ~500ms
- Sorting is instant (client-side)
- Percentiles calculated server-side for accuracy

## Updating Data

When you fetch new MLB data:

```bash
# 1. Fetch new data
python fetch_data.py

# 2. Re-calculate metrics
python web/precalculate_data.py

# 3. Restart web server
python web/app.py
```

## Troubleshooting

**Q: No players showing up?**
A: Make sure you've run `python fetch_data.py` first to populate the database.

**Q: Pre-calculation taking forever?**
A: It analyzes 300+ players with rolling 7-day windows. First time can take 10-15 minutes. Subsequent loads are instant!

**Q: Port 5000 already in use?**
A: Edit `web/app.py` and change the port number at the bottom: `app.run(port=5001)`

**Q: Percentile bars not showing?**
A: Make sure you ran `precalculate_data.py` - it calculates the percentiles for all stats.

## Tech Stack

- **Backend**: Flask (Python web framework)
- **Frontend**: Vanilla JavaScript (no framework needed!)
- **Database**: SQLite (same as main app)
- **Styling**: Custom CSS (Baseball Savant-inspired)

Enjoy your own Baseball Savant for Best Ball! 🚀⚾
