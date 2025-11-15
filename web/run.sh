#!/bin/bash

# Run MLB Best Ball Analyzer Web App

echo "======================================"
echo "MLB Best Ball Analyzer - Web Version"
echo "======================================"
echo ""

# Check if database exists
if [ ! -f "../data/mlb_stats.db" ]; then
    echo "ERROR: Database not found!"
    echo "Please run 'python fetch_data.py' from the main directory first."
    exit 1
fi

# Check if pre-calculation has been done
echo "Have you pre-calculated the Best Ball metrics? (y/n)"
echo "If this is your first time, run: python precalculate_data.py"
echo ""

# Start Flask app
echo "Starting Flask web server..."
echo "App will be available at: http://localhost:5000"
echo ""
python app.py
