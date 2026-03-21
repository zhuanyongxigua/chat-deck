from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="Relay Deck TUI")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Start the TUI with two simulated agents so the layout and event flow can be exercised without external CLIs.",
    )
    args = parser.parse_args()
    try:
        from relay_deck.app import RelayDeckApp
    except ModuleNotFoundError as exc:
        if exc.name == "textual":
            parser.exit(
                1,
                "Missing dependency: textual. Install project dependencies with `pip install -e .`.\n",
            )
        raise

    app = RelayDeckApp(demo=args.demo)
    app.run()


if __name__ == "__main__":
    main()
