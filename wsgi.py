"""WSGI entry point for PythonAnywhere (or gunicorn: `gunicorn wsgi:application`)."""
from app import create_app

application = create_app()
