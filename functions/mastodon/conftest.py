"""
Pytest configuration for Mastodon service tests.
"""

import os
import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--integration",
        action="store_true",
        default=False,
        help="Run integration tests that hit external services.",
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: mark test as integration")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--integration"):
        return

    skip_integration = pytest.mark.skip(reason="need --integration to run")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)


def has_firebase_env():
    return bool(os.getenv("RSS_FIREBASE_KEY"))
