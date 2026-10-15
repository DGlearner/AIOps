import uvicorn

from crossst.api.app import app


def main() -> None:
    uvicorn.run(
        "crossst.main:app",
        host="0.0.0.0",
        port=8888,
        reload=True,
    )

if __name__ == "__main__":
    main()
