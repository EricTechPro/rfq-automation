"""
Main Entry Point

Unified entry point for running the RFQ Automation tool in different modes.
"""

import subprocess
import sys


def print_usage():
    """Print usage information."""
    print("""
RFQ Automation Tool

Usage:
  python main.py <mode> [args...]

Modes:
  api        Start the FastAPI REST server (default port: 8000)
  cli        Run the command line interface
  streamlit  Start the Streamlit web app

Examples:
  python main.py api
  python main.py cli --nsns "4520-01-261-9675,4030-01-097-6471"
  python main.py cli --file nsns.txt --csv
  python main.py streamlit
    """)


def run_api():
    """Start the FastAPI server."""
    import uvicorn
    print("Starting FastAPI server on http://0.0.0.0:8000")
    print("API docs available at http://localhost:8000/docs")
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)


def run_cli():
    """Run the CLI with remaining arguments."""
    from cli import main as cli_main
    # Remove 'main.py' and 'cli' from sys.argv so cli.py sees the correct args
    sys.argv = ["cli.py"] + sys.argv[2:]
    cli_main()


def run_streamlit():
    """Start the Streamlit app."""
    print("Starting Streamlit app...")
    subprocess.run(["streamlit", "run", "app.py"])


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)

    mode = sys.argv[1].lower()

    if mode == "api":
        run_api()
    elif mode == "cli":
        run_cli()
    elif mode == "streamlit":
        run_streamlit()
    elif mode in ["-h", "--help", "help"]:
        print_usage()
    else:
        print(f"Unknown mode: {mode}")
        print_usage()
        sys.exit(1)


if __name__ == "__main__":
    main()
