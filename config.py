"""Application configuration."""

import os
import secrets

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    """Base configuration."""

    SECRET_KEY = os.environ.get("SECRET_KEY", secrets.token_hex(32))
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "sqlite:///" + os.path.join(basedir, "instance", "zendrian_warehouse.db"),
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Scan settings
    MIN_SCAN_INTERVAL = float(os.environ.get("MIN_SCAN_INTERVAL", "0.7"))

    # Default admin credentials (change in production)
    DEFAULT_ADMIN_USER = os.environ.get("DEFAULT_ADMIN_USER", "admin")
    DEFAULT_ADMIN_PASS = os.environ.get("DEFAULT_ADMIN_PASS", "warehouse")
