#!/bin/bash
# Exit immediately if a command exits with a non-zero status
set -e

echo "Starting Flask Backend on port 5000..."
python backend.py &

echo "Starting Streamlit Frontend on port 8080..."
streamlit run app.py --server.port=8080 --server.address=0.0.0.0 --server.headless=true --server.enableCORS=false
