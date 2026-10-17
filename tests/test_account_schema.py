import unittest

from sqlalchemy import create_engine, text

from scripts.ensure_account_schema import ensure_account_schema


class AccountSchemaTests(unittest.TestCase):
    def test_missing_account_columns_are_added_once(self):
        engine = create_engine("sqlite://")
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE users (id VARCHAR(128) PRIMARY KEY, email VARCHAR(320))"))
            first = ensure_account_schema(connection)
            columns = {row[1] for row in connection.execute(text("PRAGMA table_info(users)"))}
            tables = {row[0] for row in connection.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))}
            second = ensure_account_schema(connection)
        self.assertIn("users.deleted_at", first)
        self.assertIn("users.deleted_by", first)
        self.assertIn("friends", first)
        self.assertEqual(second, [])
        self.assertIn("deleted_at", columns)
        self.assertIn("deleted_by", columns)
        self.assertIn("friends", tables)


if __name__ == "__main__":
    unittest.main()
