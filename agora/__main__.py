"""
Module entrypoint: `python -m agora`

Starts the SABP pilot server.
"""

from __future__ import annotations


def main() -> None:
    from .api_server import main as server_main
    server_main()


if __name__ == "__main__":
    main()

