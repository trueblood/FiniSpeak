"""Application extensions shared by the Flask factory and migration tooling."""

from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager


db = SQLAlchemy()
jwt = JWTManager()
