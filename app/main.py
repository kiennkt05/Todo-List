import os

from app.factory import create_app


app = create_app(
    database_url=os.getenv("DATABASE_URL", "sqlite:///./data/todo.db"),
    token_secret=os.environ["TOKEN_SECRET"],
)
