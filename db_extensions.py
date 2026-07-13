"""Flask-SQLAlchemy 单例（与 app.py 共用，避免循环 import）。"""
from __future__ import annotations

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
