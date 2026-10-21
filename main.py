import asyncio

from roomloop.server import app, server

__all__ = ["app", "server"]


def main() -> None:
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
