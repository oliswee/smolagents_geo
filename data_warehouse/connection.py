"""PostgreSQL + PostGIS connection manager."""
from sqlalchemy import create_engine, text
import pandas as pd
import json
from typing import Tuple, Optional, Any


class DatabaseManager:
    """Manages PostgreSQL/PostGIS connections and query execution."""

    def __init__(self, config: dict):
        self.host = config["database"]["host"]
        self.port = config["database"]["port"]
        self.db_name = config["database"]["db_name"]
        self.user = config["database"]["user"]
        self.password = config["database"]["password"]
        self.schema = config["database"]["schema"]
        self._engine = None

    def connect(self) -> Tuple[Any, Any]:
        """Create SQLAlchemy engine and connection."""
        url = (
            f"postgresql+psycopg2://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.db_name}"
        )
        self._engine = create_engine(url, echo=False)
        conn = self._engine.connect()
        return self._engine, conn

    @staticmethod
    def connect_from_credentials(credential_filepath: str) -> Tuple[Any, Any]:
        """Connect using a JSON credentials file."""
        with open(credential_filepath) as f:
            creds = json.load(f)
        url = (
            f"postgresql+psycopg2://{creds['user']}:{creds['password']}"
            f"@{creds['host']}:{creds['port']}/{creds.get('db_name', creds['user'])}"
        )
        engine = create_engine(url, echo=False)
        conn = engine.connect()
        return engine, conn

    @staticmethod
    def get_config_from_credentials(credential_filepath: str = "Credentials.json") -> dict:
        """Build a config dict from a JSON credentials file."""
        with open(credential_filepath) as f:
            creds = json.load(f)
        return {
            "database": {
                "host": creds["host"],
                "port": creds["port"],
                "db_name": creds.get("db_name", creds["user"]),
                "user": creds["user"],
                "password": creds["password"],
                "schema": "public",
            }
        }

    @staticmethod
    def query(conn, sql: str, params: Optional[dict] = None, df: bool = True):
        """Execute SQL and return DataFrame or raw results."""
        try:
            if df:
                return pd.read_sql_query(sql, conn, params=params)
            result = conn.execute(text(sql), params or {}).fetchall()
            return result[0] if len(result) == 1 else result
        except Exception as e:
            print(f"Query error: {e}")
            return pd.DataFrame() if df else None

    def get_cursor(self, conn):
        """Get a server-side cursor for large result sets."""
        return conn.connection.cursor()

    def execute_ddl(self, conn, ddl_filepath: str):
        """Execute a DDL SQL file, handling dollar-quoted PL/pgSQL blocks."""
        with open(ddl_filepath, "r", encoding="utf-8") as f:
            sql = f.read()
        # Use raw psycopg2 connection to execute entire file at once
        # This avoids issues with semicolons inside $$...$$ function bodies
        raw_conn = conn.connection
        with raw_conn.cursor() as cur:
            cur.execute(sql)
        raw_conn.commit()
        print(f"Executed {ddl_filepath} successfully")
