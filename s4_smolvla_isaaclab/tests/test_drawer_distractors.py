from __future__ import annotations

import os

from s4_pipeline.drawer_distractors import (
    DISTRACTOR_CANS_ENV,
    apply_distractor_spawn_env,
    can_xy_enabled_from_scripted,
    distractor_cans_enabled_from_scripted,
)
from tasks.drawer_insert_close_controller import load_scripted_config


def test_scripted_defaults_randomize_can_without_distractors():
    cfg = load_scripted_config()
    assert can_xy_enabled_from_scripted(cfg) is True
    assert distractor_cans_enabled_from_scripted(cfg) is False


def test_apply_distractor_spawn_env_toggles_process_env(monkeypatch):
    monkeypatch.delenv(DISTRACTOR_CANS_ENV, raising=False)
    apply_distractor_spawn_env(True)
    assert os.environ[DISTRACTOR_CANS_ENV] == "1"
    apply_distractor_spawn_env(False)
    assert DISTRACTOR_CANS_ENV not in os.environ
