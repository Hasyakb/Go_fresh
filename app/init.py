from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_bootstrap import Bootstrap
import os

db = SQLAlchemy()
login_manager = LoginManager()
bootstrap = Bootstrap()

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'your-secret-key-here-change-in-production'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///record_book.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    login_manager.login_message = 'Please log in to access this page.'
    bootstrap.init_app(app)
    
    from app import routes
    app.register_blueprint(routes.bp)
    
    with app.app_context():
        db.create_all()
    
    return app