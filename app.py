"""Flask application factory."""

import json
import os
from flask import Flask
from flask_login import LoginManager
from werkzeug.middleware.proxy_fix import ProxyFix
from config import Config
from models import db, User


login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message_category = "info"


@login_manager.user_loader
def load_user(user_id):
    """Load a user by ID for Flask-Login."""
    return db.session.get(User, int(user_id))


def create_app(config_class=Config):
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Trust reverse proxy headers (X-Forwarded-For, X-Forwarded-Proto, etc.)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    # Ensure instance directory exists
    os.makedirs(os.path.join(app.root_path, "instance"), exist_ok=True)

    # Initialise extensions
    db.init_app(app)
    login_manager.init_app(app)

    # Register custom Jinja filters
    app.jinja_env.filters["from_json"] = json.loads

    # Register blueprints
    from routes.auth import bp as auth_bp
    from routes.dashboard import bp as dashboard_bp
    from routes.scanning import bp as scanning_bp
    from routes.admin import admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(scanning_bp)
    app.register_blueprint(admin_bp)

    # Create tables and seed default user
    with app.app_context():
        db.create_all()

        # Enable SQLite WAL mode for better concurrent read performance
        if "sqlite" in app.config["SQLALCHEMY_DATABASE_URI"]:
            with db.engine.connect() as conn:
                conn.execute(db.text("PRAGMA journal_mode=WAL"))
                conn.commit()

        _seed_default_user(app)

    return app


def _seed_default_user(app):
    """Create the default admin user if no users exist."""
    if User.query.count() == 0:
        username = app.config["DEFAULT_ADMIN_USER"]
        password = app.config["DEFAULT_ADMIN_PASS"]
        user = User(
            username=username,
            display_name="Admin",
            is_admin=True,
            is_active=True,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        print(f"Created default admin user: {username}")


# Run directly for development
if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, host="0.0.0.0", port=5000)
