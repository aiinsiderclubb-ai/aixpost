"""Application factory entrypoints.

Routes currently live in run_test_v2.py for compatibility. Import create_app /
bootstrap from here so Docker/gunicorn and future blueprints share one path.
"""

from __future__ import annotations


def create_app(test_config=None):
    from run_test_v2 import create_app as _create_app
    return _create_app(test_config=test_config)


def bootstrap_background_services():
    from run_test_v2 import bootstrap_background_services as _bootstrap
    return _bootstrap()


def get_app():
    from run_test_v2 import app
    return app
