"""SQLite for local play, PostgreSQL for durable hosting (including Neon)."""
from contextlib import contextmanager
import sqlite3
import threading

# All writers share this transaction-scoped lock. This preserves the existing
# SQLite single-writer guarantees for room actions, purchases and promo limits.
WRITE_LOCK = 718246390


class PostgresConnection:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, statement, parameters=()):
        # Statements are internal, fixed SQL; values always remain parameters.
        return self.connection.execute(statement.replace('?', '%s'), parameters)

    def executescript(self, script):
        for statement in script.split(';'):
            if statement.strip() and not statement.strip().startswith('PRAGMA'):
                self.execute(statement)


class Database:
    def __init__(self, path, url=None):
        self.path = str(path)
        self.url = url
        self.postgres = bool(url)
        self.current = threading.local()
        if url:
            from psycopg.conninfo import conninfo_to_dict
            options = conninfo_to_dict(url)
            if options.get('sslmode') not in ('require', 'verify-ca', 'verify-full'):
                raise ValueError('DATABASE_URL должен включать sslmode=require.')

    @contextmanager
    def connect(self):
        active = getattr(self.current, 'connection', None)
        if active is not None:
            yield active
            return
        if self.postgres:
            import psycopg
            from psycopg.rows import dict_row
            # Short-lived connections allow Neon to sleep between requests.
            with psycopg.connect(self.url, row_factory=dict_row, connect_timeout=15,
                                 prepare_threshold=None) as connection:
                yield PostgresConnection(connection)
        else:
            connection = sqlite3.connect(self.path, timeout=10)
            connection.row_factory = sqlite3.Row
            try:
                with connection:
                    yield connection
            finally:
                connection.close()

    @contextmanager
    def transaction(self):
        if getattr(self.current, 'connection', None) is not None:
            yield self.current.connection
            return
        with self.connect() as connection:
            if self.postgres:
                connection.execute('SELECT pg_advisory_xact_lock(?)', (WRITE_LOCK,))
            else:
                connection.execute('BEGIN IMMEDIATE')
            self.current.connection = connection
            try:
                yield connection
            finally:
                del self.current.connection
