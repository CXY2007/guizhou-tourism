"""生产入口：交给 waitress 跑（Windows / Linux 都能用）。

    python -m waitress --host=127.0.0.1 --port=8900 wsgi:app
    # 或
    python serve.py

开发调试仍用 `python run.py`（带自动重载）。
"""
from app import create_app

app = create_app()

if __name__ == "__main__":
    import os

    from waitress import serve

    host = os.getenv("SITE_HOST", "127.0.0.1")
    port = int(os.getenv("SITE_PORT", "8900"))
    threads = int(os.getenv("SITE_THREADS", "4"))
    print(f"waitress serving on http://{host}:{port} (threads={threads})")
    serve(app, host=host, port=port, threads=threads)
