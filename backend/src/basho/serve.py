"""Launcher local da API que funciona no Windows (``python -m basho.serve``).

O psycopg assíncrono exige ``SelectorEventLoop``; no Windows o padrão é o Proactor e o
``uvicorn --loop none``/``asyncio`` não o troca. Em Linux/macOS use o uvicorn direto.
"""

import asyncio
import os
import selectors

import uvicorn


def main() -> None:
    config = uvicorn.Config(
        "basho.main:app",
        factory=True,
        host=os.environ.get("API_HOST", "127.0.0.1"),
        port=int(os.environ.get("API_PORT", "8000")),
    )
    asyncio.run(
        uvicorn.Server(config).serve(),
        loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
    )


if __name__ == "__main__":
    main()
