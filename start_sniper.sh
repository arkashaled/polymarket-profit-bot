#!/bin/bash
echo "🎯 Starting Polymarket 98-Cent Sniper Bot..."
while true; do
    echo "▶️  $(date): Starting sniper..."
    python3 sniper_bot.py
    echo "⚠️  $(date): Crashed or exited. Restarting in 10s..."
    sleep 10
done
