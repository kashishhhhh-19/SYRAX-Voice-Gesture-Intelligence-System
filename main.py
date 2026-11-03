"""
main.py - Entry Point for SYRAX Voice & Gesture Intelligence System
Usage:
    python main.py             Launch futuristic dashboard control room
    python main.py --diagnose  Run comprehensive hardware and subsystem self-test
"""

import argparse
import sys
import tkinter as tk
from pathlib import Path

# Add project root to sys.path to ensure clean package resolution
sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
from core.assistant_engine import AssistantEngine
from core.logger import setup_logger
from gui.dashboard import Dashboard

logger = setup_logger("Main")

# Reconfigure standard streams for Windows terminal UTF-8 safety
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BANNER = r"""
  ==============================================================
    ____  __  ______  ___   _  __
   / __ \/ / / / __ \/   | | |/ /   S Y R A X
  / /_/ / / / / /_/ / /| | |   /    "Speak. Gesture. Control."
 / ____/ /_/ / _, _/ ___ |/   |     Voice & Gesture Intelligence
/_/    \____/_/ |_/_/  |_/_/|_|     System for Windows 10/11
  ==============================================================
  Version: 1.0.0 | Tagline: "Speak. Gesture. Control."
  ==============================================================
"""


def run_diagnostics_cli() -> int:
    """
    Execute subsystem self-test in terminal and print pass/fail report with fix hints.
    """
    print(BANNER)
    print("\n[*] Initializing SYRAX Subsystem Self-Test...\n" + "-" * 55)

    engine = AssistantEngine()
    results = engine.run_diagnostics()

    print("\n" + "=" * 55)
    print("           DIAGNOSTIC TEST RESULTS")
    print("=" * 55)

    all_passed = True
    for test in results:
        subsystem = test["subsystem"]
        passed = test["passed"]
        message = test["message"]
        fix_hint = test["fix_hint"]

        status_str = "[ PASS ]" if passed else "[ FAIL ]"
        print(f"\n{status_str} {subsystem}")
        print(f"        Details:  {message}")
        if not passed:
            all_passed = False
            print(f"        FIX HINT: {fix_hint}")

    print("\n" + "=" * 55)
    if all_passed:
        print("[+] ALL SUBSYSTEMS OPERATIONAL. You are ready to launch SYRAX!")
        print("[+] Run: python main.py")
        print("=" * 55 + "\n")
        return 0
    else:
        print("[-] SOME SUBSYSTEMS FAILED. Please review the fix hints above.")
        print("[-] Note: If PyAudio failed, SYRAX will auto-fallback to sounddevice.")
        print("=" * 55 + "\n")
        return 1


def main() -> None:
    """Parse CLI arguments and launch application."""
    parser = argparse.ArgumentParser(
        description=f"{config.APP_NAME} - Voice & Gesture Intelligence System",
        epilog="Speak. Gesture. Control."
    )
    parser.add_argument(
        "--diagnose",
        action="store_true",
        help="Run comprehensive hardware and subsystem diagnostics self-test."
    )
    args = parser.parse_args()

    if args.diagnose:
        exit_code = run_diagnostics_cli()
        sys.exit(exit_code)

    # Enable Windows DPI awareness for razor-sharp rendering on 1080p/4K displays
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    print(BANNER)
    logger.info("Starting SYRAX Voice & Gesture Intelligence System...")

    # Initialize Tkinter root
    root = tk.Tk()

    # Initialize Assistant Engine & Dashboard
    engine = AssistantEngine()
    app = Dashboard(root, engine)

    # Start engine workers and startup voice greeting
    engine.start()

    # Launch Tkinter event loop
    try:
        root.mainloop()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received. Shutting down...")
    finally:
        engine.stop()


if __name__ == "__main__":
    main()
