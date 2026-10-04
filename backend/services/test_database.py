import unittest

from backend.database import normalize_database_url


class DatabaseUrlTests(unittest.TestCase):
    def test_normalizes_render_postgres_url(self):
        self.assertEqual(
            normalize_database_url("postgres://user:pass@host:5432/app"),
            "postgresql+psycopg://user:pass@host:5432/app",
        )

    def test_normalizes_postgresql_url(self):
        self.assertEqual(
            normalize_database_url("postgresql://user:pass@host:5432/app"),
            "postgresql+psycopg://user:pass@host:5432/app",
        )

    def test_preserves_sqlite_url(self):
        self.assertEqual(
            normalize_database_url("sqlite:///./dev.db"),
            "sqlite:///./dev.db",
        )


if __name__ == "__main__":
    unittest.main()
