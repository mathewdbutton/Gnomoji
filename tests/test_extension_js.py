"""Runs the extension's plain-JS unit tests (tests/extension/test_*.js) with gjs."""

import subprocess
from pathlib import Path

import pytest

from conftest import require

JS_TESTS = sorted((Path(__file__).parent / "extension").glob("test_*.js"))


@pytest.mark.parametrize("script", JS_TESTS, ids=lambda p: p.name)
def test_js(script):
    require("gjs")
    result = subprocess.run(
        ["gjs", "-m", str(script)], capture_output=True, text=True, timeout=30, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_js_tests_exist():
    assert JS_TESTS, "no tests/extension/test_*.js found"
