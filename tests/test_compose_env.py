"""Regression guards for Docker Compose environment pass-through."""

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPOSE_FILES = (
    "docker-compose.yml",
    "docker-compose.traefik.yml",
)


@pytest.mark.parametrize("filename", COMPOSE_FILES)
def test_app_service_loads_optional_dotenv(filename):
    document = yaml.safe_load(
        (REPO_ROOT / filename).read_text(encoding="utf-8")
    )
    env_files = document["services"]["app"]["env_file"]
    assert {"path": ".env", "required": False} in env_files


def test_optional_env_file_compose_version_is_documented():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "Docker Compose 2.24.0+" in readme
