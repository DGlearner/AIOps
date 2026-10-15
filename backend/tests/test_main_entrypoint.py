from unittest.mock import patch

from crossst import main as crossst_main


def test_main_starts_uvicorn_with_importable_asgi_app():
    with patch("crossst.main.uvicorn.run") as run:
        crossst_main.main()

    run.assert_called_once_with(
        "crossst.main:app",
        host="0.0.0.0",
        port=8888,
        reload=True,
    )
