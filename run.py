import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=int(os.getenv("SITE_PORT", "8900")),
        debug=os.getenv("FLASK_DEBUG", "0") == "1",
    )
