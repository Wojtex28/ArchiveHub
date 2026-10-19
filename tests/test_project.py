import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.core.management import call_command

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.django_db
def test_no_missing_migrations():
    call_command("makemigrations", "--check", "--dry-run", verbosity=0)


def _manage(*args, extra_env):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("DJANGO_", "ARCHIVEHUB_"))}
    env.update(extra_env)
    return subprocess.run(
        [sys.executable, "manage.py", *args], cwd=ROOT, env=env, capture_output=True, text=True
    )


def test_production_settings_pass_deploy_check(tmp_path):
    result = _manage(
        "check",
        "--deploy",
        "--fail-level",
        "WARNING",
        extra_env={
            "DJANGO_DEBUG": "0",
            "DJANGO_SECRET_KEY": "x" * 30 + "-test-key-" + "y" * 30,
            "DJANGO_ALLOWED_HOSTS": "archiwum.example.com",
            "ARCHIVEHUB_DATA_DIR": str(tmp_path),
        },
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_production_refuses_to_start_without_secret_key(tmp_path):
    result = _manage(
        "check",
        extra_env={"DJANGO_DEBUG": "0", "ARCHIVEHUB_DATA_DIR": str(tmp_path)},
    )
    assert result.returncode != 0
    assert "DJANGO_SECRET_KEY" in result.stderr
