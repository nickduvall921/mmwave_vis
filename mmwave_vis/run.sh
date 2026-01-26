#!/bin/bash

echo "Starting mmWave Visualizer..."

# Limit the container to ~200 MB of RAM (200,000 KB)
ulimit -v 200000 

python3 /app/app.py