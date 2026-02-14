#!/bin/bash
# Start script for Railway deployment
# Uses PORT env var from Railway, defaults to 8501 for local dev

PORT="${PORT:-8501}"
echo "Starting Streamlit on port $PORT"
exec streamlit run app.py --server.port="$PORT" --server.address=0.0.0.0
