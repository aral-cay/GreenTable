"""GreenTable Flask entry point."""
from flask import Flask, jsonify

from config import Config
from routes.users import users_bp
from routes.friends import friends_bp
from routes.sessions import sessions_bp
from routes.invitations import invitations_bp


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["JSON_SORT_KEYS"] = False

    app.register_blueprint(users_bp)
    app.register_blueprint(friends_bp)
    app.register_blueprint(sessions_bp)
    app.register_blueprint(invitations_bp)

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.errorhandler(404)
    def not_found(_):
        return jsonify({"error": "not found"}), 404

    @app.errorhandler(405)
    def method_not_allowed(_):
        return jsonify({"error": "method not allowed"}), 405

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host=Config.FLASK_HOST, port=Config.FLASK_PORT, debug=True)
