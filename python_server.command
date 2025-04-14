#!/bin/bash
cd "$(dirname "$0")"
echo "Starting Python HTTP Server..."
python3 "server/server.py"
read -p "Press Enter to exit..."