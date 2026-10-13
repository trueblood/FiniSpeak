import os
import unittest
from unittest.mock import patch

from sqlalchemy.engine import URL

from app import MYSQL_ENVIRONMENT_VARIABLES, create_app


class OptionalMysqlStartupTests(unittest.TestCase):
    def mysql_environment(self, **overrides):
        values = {
            "MYSQL_HOST": "mysql.internal",
            "MYSQL_PORT": "3306",
            "MYSQL_DATABASE": "finispeak",
            "MYSQL_USER": "finispeak_app",
            "MYSQL_PASSWORD": "p@ss:/?#[] word",
        }
        values.update(overrides)
        return values

    @patch("app.db.init_app")
    def test_mysql_is_not_initialized_when_configuration_is_incomplete(self, init_app):
        environment = os.environ.copy()
        for name in MYSQL_ENVIRONMENT_VARIABLES:
            environment.pop(name, None)
        environment.update(self.mysql_environment(MYSQL_PASSWORD=""))

        with patch.dict(os.environ, environment, clear=True):
            flask_app = create_app()

        init_app.assert_not_called()
        self.assertNotIn("SQLALCHEMY_DATABASE_URI", flask_app.config)

    @patch("sqlalchemy.engine.Engine.connect")
    def test_mysql_is_initialized_with_a_safely_constructed_url(self, connect):
        environment = os.environ.copy()
        environment.update(self.mysql_environment())

        with patch.dict(os.environ, environment, clear=True):
            flask_app = create_app()

        connect.assert_not_called()
        self.assertIn("sqlalchemy", flask_app.extensions)
        database_url = flask_app.config["SQLALCHEMY_DATABASE_URI"]
        self.assertIsInstance(database_url, URL)
        self.assertEqual(database_url.drivername, "mysql+pymysql")
        self.assertEqual(database_url.host, "mysql.internal")
        self.assertEqual(database_url.port, 3306)
        self.assertEqual(database_url.database, "finispeak")
        self.assertEqual(database_url.username, "finispeak_app")
        self.assertEqual(database_url.password, "p@ss:/?#[] word")
        self.assertNotIn(
            "p@ss:/?#[] word",
            database_url.render_as_string(hide_password=False),
        )
        self.assertFalse(flask_app.config["SQLALCHEMY_TRACK_MODIFICATIONS"])


if __name__ == "__main__":
    unittest.main()
