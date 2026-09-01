from __future__ import annotations

import os

import uvicorn


def main() -> None:
    """Run the pipelign-diagrams API server."""
    host = os.getenv("HOST", "0.0.0.0")
    try:
        port = int(os.getenv("PORT", "8080"))
    except ValueError:
        port = 8080
    uvicorn.run("app.main:app", host=host, port=port)


if __name__ == "__main__":
    main()
