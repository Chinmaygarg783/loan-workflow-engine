import sys
import os

# Make the project root importable from the tests/ directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    """FastAPI test client — reused across the entire test module."""
    import main
    with TestClient(main.app) as c:
        yield c