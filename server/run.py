"""Convenience entrypoint: `python run.py`."""

from app.config import settings


def main() -> None:
    import uvicorn

    print(f"Starting DirectStream API on {settings.host}:{settings.port}")
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
