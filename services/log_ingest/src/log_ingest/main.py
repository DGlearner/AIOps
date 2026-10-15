import uvicorn

from log_ingest.app import app


def main() -> None:
    uvicorn.run(
        "log_ingest.main:app",
        host="0.0.0.0",
        port=8100,
        reload=True,
    )


if __name__ == "__main__":
    main()
