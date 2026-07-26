"""Convenience entrypoint: `python run.py`."""

import logging

from app.config import settings

logger = logging.getLogger("mediapull.run")


def main() -> None:
    import uvicorn

    # The app configures its own logging in the lifespan; this only covers the
    # pre-startup line below so it goes through a handler instead of print().
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    logger.info("Starting MediaPull API on %s:%s", settings.host, settings.port)
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        workers=settings.workers,
        access_log=settings.debug,
        reload=settings.debug,
    )


if __name__ == "__main__":
    main()
