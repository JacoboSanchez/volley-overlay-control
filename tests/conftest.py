import pytest
import os
from nicegui.testing import User
from typing import Generator
from app.startup import startup
from dotenv import load_dotenv

os.environ['PYTEST_CURRENT_TEST'] = 'true'

pytest_plugins = ['nicegui.testing.plugin']

@pytest.fixture(autouse=True)
def load_test_env():
    dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env.test')
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path=dotenv_path)

        
@pytest.fixture
def user(user: User) -> Generator[User, None, None]:
    startup()
    yield user