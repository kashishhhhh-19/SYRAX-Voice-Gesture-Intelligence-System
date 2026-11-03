"""
GestureFlow — AI Hand Gesture Controller
Main Application Entry Point.

Run:
    python main.py
    python main.py --camera-index 0
    python main.py --help
"""

import argparse
import sys
import os

# Ensure current directory is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.config import AppConfig, DEFAULT_CONFIG
from app.ui import GestureFlowApp


def parse_arguments() -> argparse.Namespace:
    """Parses optional command-line arguments for camera and configuration."""
    parser = argparse.ArgumentParser(
        prog="GestureFlow",
        description="GestureFlow — Real-Time AI Hand Gesture Controller for Presentations & Navigation"
    )
    parser.add_argument(
        "-c", "--camera-index",
        type=int,
        default=0,
        help="Webcam device index to open (default: 0)"
    )
    parser.add_argument(
        "-w", "--width",
        type=int,
        default=640,
        help="Video capture resolution width (default: 640)"
    )
    parser.add_argument(
        "-H", "--height",
        type=int,
        default=480,
        help="Video capture resolution height (default: 480)"
    )
    parser.add_argument(
        "--no-mirror",
        action="store_true",
        help="Disable horizontal frame mirroring"
    )
    return parser.parse_args()


def main():
    """Application main routine."""
    args = parse_arguments()

    # Build configuration with user CLI overrides
    config = AppConfig()
    config.camera.camera_index = args.camera_index
    config.camera.frame_width = args.width
    config.camera.frame_height = args.height
    config.camera.mirror_frame = not args.no_mirror

    print("=" * 64)
    print("  GestureFlow — AI Hand Gesture Controller")
    print("  Version: 1.0.0 | Engine: MediaPipe Hands & OpenCV")
    print("=" * 64)
    print(f"[*] Initializing camera index: {config.camera.camera_index}")
    print(f"[*] Preview resolution: {config.camera.frame_width}x{config.camera.frame_height}")
    print(f"[*] Frame mirroring: {'Enabled' if config.camera.mirror_frame else 'Disabled'}")
    print("[*] Safety: Computer controls disabled by default (Arm via GUI)")
    print("[*] Emergency Stop: Available via GUI button or [Esc] / [Q]")
    print("-" * 64)

    try:
        app = GestureFlowApp(config=config)
        app.run()
    except KeyboardInterrupt:
        print("\n[!] GestureFlow interrupted by user. Exiting cleanly.")
    except Exception as exc:
        print(f"\n[!] Unexpected application error: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
