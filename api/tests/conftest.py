"""Shared test configuration and fixtures.

All test database credentials are centralized here.
Tests use the `db_url` and `api_url` fixtures instead of hardcoding.
"""
import os
import pytest

TEST_DB_HOST = os.environ.get("TEST_DB_HOST", "localhost")
TEST_DB_PORT = os.environ.get("TEST_DB_PORT", "5435")
TEST_DB_NAME = os.environ.get("TEST_DB_NAME", "ecodb")
TEST_DB_USER = os.environ.get("TEST_DB_USER", "ecodb")
TEST_DB_PASS = os.environ.get("TEST_DB_PASS", "ecodb_test_pass")

TEST_DB_URL = f"postgresql://{TEST_DB_USER}:{TEST_DB_PASS}@{TEST_DB_HOST}:{TEST_DB_PORT}/{TEST_DB_NAME}"

TEST_API_URL = os.environ.get("TEST_API_URL", "http://localhost:8080")


@pytest.fixture
def db_url():
    return TEST_DB_URL


@pytest.fixture
def api_url():
    return TEST_API_URL
