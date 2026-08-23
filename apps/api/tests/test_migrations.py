from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command


def test_fresh_database_is_created_from_migrations(tmp_path: Path) -> None:
    db_file = tmp_path / "migrations.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"

    project_root = Path(__file__).resolve().parents[1]
    alembic_config = Config(str(project_root / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(project_root / "alembic"))
    alembic_config.set_main_option("sqlalchemy.url", db_url)

    command.upgrade(alembic_config, "head")

    sync_engine = create_engine(f"sqlite:///{db_file}")
    inspector = inspect(sync_engine)
    tables = set(inspector.get_table_names())

    assert {
        "workspaces",
        "pages",
        "blocks",
        "files",
        "knowledge_index_config",
        "page_knowledge",
        "knowledge_chunks",
        "agent_tool_calls",
    }.issubset(tables)
    assert "generation" in {column["name"] for column in inspector.get_columns("page_knowledge")}
