#!/usr/bin/with-contenv bashio

echo "Starting mmWave Visualizer..."

# Wait for Home Assistant Core to be ready before connecting.
# The Supervisor WebSocket proxy returns HTTP 502 if HA Core isn't up yet.
bashio::net.wait_for 8123 homeassistant 60

# Limit the container to ~200 MB of RAM (200,000 KB)
ulimit -v 200000

exec python3 /app/app.py