"""SmartSpend application factory."""
import logging

from flask import Flask, flash, jsonify, redirect, render_template, request, url_for
from flask_wtf.csrf import CSRFError
from sqlalchemy.exc import OperationalError

from app import categories as category_service, monitoring
from app.extensions import csrf, db, login_manager, migrate
from app.utils import format_money
from config import Config

logger = logging.getLogger(__name__)


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # --- extensions ---
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to continue."
    login_manager.login_message_category = "warning"
    login_manager.session_protection = "strong"

    from app import models  # noqa: F401  (so Flask-Migrate can see the tables)

    # --- blueprints ---
    from app.admin.routes import bp as admin_bp
    from app.ai.routes import bp as ai_bp
    from app.analytics.routes import bp as analytics_bp
    from app.auth.routes import bp as auth_bp
    from app.budget.routes import bp as budget_bp
    from app.expenses.routes import bp as expenses_bp
    from app.ml.routes import bp as ml_bp
    from app.routes import bp as main_bp

    for blueprint in (main_bp, auth_bp, expenses_bp, analytics_bp, budget_bp, ai_bp, ml_bp, admin_bp):
        app.register_blueprint(blueprint)

    # --- template helpers ---
    app.jinja_env.filters["money"] = format_money
    app.jinja_env.filters["cat_color"] = category_service.color_for

    _register_error_handlers(app)

    from app.cli import register_cli

    register_cli(app)
    return app


def _wants_json() -> bool:
    best = request.accept_mimetypes
    return best.accept_json and not best.accept_html


def _register_error_handlers(app):
    @app.errorhandler(CSRFError)
    def handle_csrf(error):
        if _wants_json():
            return jsonify(error="Your session expired. Please refresh the page."), 400
        flash("Your form session expired. Please try again.", "warning")
        return redirect(request.referrer or url_for("main.index"))

    @app.errorhandler(OperationalError)
    def handle_db_down(error):
        db.session.rollback()
        logger.error("Database connection failure: %s", error)
        if _wants_json():
            return jsonify(error="The database is not reachable right now."), 503
        return render_template("errors/db_error.html"), 503

    @app.errorhandler(404)
    def handle_404(error):
        if _wants_json():
            return jsonify(error="Not found."), 404
        return render_template("errors/404.html"), 404

    @app.errorhandler(403)
    def handle_403(error):
        if _wants_json():
            return jsonify(error="Forbidden."), 403
        return render_template("errors/403.html"), 403

    @app.errorhandler(500)
    def handle_500(error):
        db.session.rollback()
        monitoring.record_server_error()
        if _wants_json():
            return jsonify(error="Something went wrong on our side."), 500
        return render_template("errors/500.html"), 500
