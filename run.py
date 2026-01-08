#!/usr/bin/env python3
"""
Railway-compatible Streamlit launcher.
Reads PORT from environment variable and launches Streamlit properly.
This avoids shell variable expansion issues.
"""
import os
import sys
import subprocess

def main():
    # Get port from environment, default to 8501
    port = os.environ.get('PORT', '8501')

    print(f"Starting Streamlit on port {port}")

    # Build the command
    cmd = [
        sys.executable,  # Use the same Python interpreter
        '-m', 'streamlit', 'run',
        'app.py',
        '--server.port', str(port),
        '--server.address', '0.0.0.0',
        '--server.headless', 'true',
        '--browser.serverAddress', '0.0.0.0',
        '--browser.gatherUsageStats', 'false'
    ]

    print(f"Running: {' '.join(cmd)}")

    # Replace current process with streamlit
    os.execvp(cmd[0], cmd)

if __name__ == '__main__':
    main()
