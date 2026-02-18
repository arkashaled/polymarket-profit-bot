#!/bin/bash
echo "🚀 Starting Polymarket Profit-Taking Bot..."
while true; do
    echo "▶️  $(date): Starting..."
    python3 profit_taking_bot.py
    echo "⚠️  $(date): Crashed or exited. Restarting in 10s..."
    sleep 10
done
