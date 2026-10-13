from logging.config import fileConfig

from alembic import context
from flask import current_app

from app import create_app
from extensions import db
from models import sql_models  # noqa: F401 - registers migration metadata


config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

target_metadata = db.metadata


def database_url():
    app = create_app()
    if "SQLALCHEMY_DATABASE_URI" not in app.config:
        raise RuntimeError("All MYSQL_* environment variables are required for Alembic commands.")
    return app, app.config["SQLALCHEMY_DATABASE_URI"].render_as_string(hide_password=False)


def run_migrations_offline():
    _, url = database_url()
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    app, _ = database_url()
    with app.app_context():
        with db.engine.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
            with context.begin_transaction():
                context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
