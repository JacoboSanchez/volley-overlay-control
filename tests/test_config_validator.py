import os
import pytest
import logging
from unittest.mock import patch
from app.config_validator import validate_config

@pytest.fixture
def clean_env():
    with patch.dict(os.environ, {}, clear=True):
        yield

def test_valid_integer_vars(clean_env, caplog):
    os.environ['MATCH_GAME_POINTS'] = '21'
    validate_config()
    assert os.environ['MATCH_GAME_POINTS'] == '21'
    assert not caplog.records

def test_invalid_integer_vars(clean_env, caplog):
    os.environ['MATCH_GAME_POINTS'] = 'invalid'
    os.environ['MATCH_SETS'] = '-1'
    validate_config()
    assert os.environ['MATCH_GAME_POINTS'] == '25'
    assert os.environ['MATCH_SETS'] == '5'
    assert any("Invalid MATCH_GAME_POINTS" in r.message for r in caplog.records)
    assert any("Invalid MATCH_SETS" in r.message for r in caplog.records)

def test_valid_json_vars(clean_env, caplog):
    os.environ['APP_THEMES'] = '{"theme1": {"color": "red"}}'
    validate_config()
    assert 'APP_THEMES' in os.environ
    assert not caplog.records

def test_invalid_json_vars(clean_env, caplog):
    os.environ['APP_THEMES'] = '{invalid json}'
    validate_config()
    assert 'APP_THEMES' not in os.environ
    assert any("Invalid JSON in APP_THEMES" in r.message for r in caplog.records)

def test_valid_port(clean_env, caplog):
    os.environ['APP_PORT'] = '9090'
    validate_config()
    assert os.environ['APP_PORT'] == '9090'
    assert not any("Invalid APP_PORT" in r.message for r in caplog.records)

def test_invalid_port(clean_env, caplog):
    os.environ['APP_PORT'] = 'notaport'
    validate_config()
    assert os.environ['APP_PORT'] == '8080'
    assert any("Invalid APP_PORT" in r.message for r in caplog.records)

def test_out_of_range_port(clean_env, caplog):
    os.environ['APP_PORT'] = '99999'
    validate_config()
    assert os.environ['APP_PORT'] == '8080'
    assert any("Invalid APP_PORT" in r.message for r in caplog.records)

def test_valid_hide_timeout(clean_env, caplog):
    os.environ['DEFAULT_HIDE_TIMEOUT'] = '10'
    validate_config()
    assert os.environ['DEFAULT_HIDE_TIMEOUT'] == '10'
    assert not any("Invalid DEFAULT_HIDE_TIMEOUT" in r.message for r in caplog.records)

def test_invalid_hide_timeout(clean_env, caplog):
    os.environ['DEFAULT_HIDE_TIMEOUT'] = 'never'
    validate_config()
    assert os.environ['DEFAULT_HIDE_TIMEOUT'] == '5'
    assert any("Invalid DEFAULT_HIDE_TIMEOUT" in r.message for r in caplog.records)

def test_invalid_enum_vars(clean_env, caplog):
    os.environ['APP_DARK_MODE'] = 'invalid'
    os.environ['LOGGING_LEVEL'] = 'superdebug'
    validate_config()
    assert os.environ['APP_DARK_MODE'] == 'auto'
    assert os.environ['LOGGING_LEVEL'] == 'info'
    assert any("Invalid APP_DARK_MODE" in r.message for r in caplog.records)
    assert any("Invalid LOGGING_LEVEL" in r.message for r in caplog.records)
