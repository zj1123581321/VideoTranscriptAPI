"""Static guards for deploy artifacts that survive the legacy-lane retirement.

The retired manual lane (`docker/pull_and_deploy.sh`, removed 2026-10-15) used
to own this file; what remains is the push-to-GHCR build-script guard and the
compose deploy-seed guards that both the D3 lane and the seed file itself
still depend on.
"""

from pathlib import Path

import yaml


COMPOSE_TEMPLATE = Path(__file__).parents[2] / "docker" / "docker-compose.deploy.yml"
PUSH_SCRIPT = Path(__file__).parents[2] / "docker" / "push_to_ghcr.sh"


def test_compose_template_uses_legacy_compatible_env_file_syntax():
    source = COMPOSE_TEMPLATE.read_text(encoding="utf-8")
    assert "required:" not in source
    assert "- .env" in source


def test_compose_template_sets_stop_grace_period():
    compose = yaml.safe_load(COMPOSE_TEMPLATE.read_text(encoding="utf-8"))
    assert compose["services"]["video-transcript-api"]["stop_grace_period"] == "30s"


def test_build_script_uses_only_git_sha_tag():
    source = PUSH_SCRIPT.read_text(encoding="utf-8")
    assert 'IMAGE_REF="${REGISTRY_IMAGE}:${GIT_SHA}"' in source
    assert ":latest" not in source
    assert '--build-arg "GIT_SHA=${GIT_SHA}"' in source
    assert "status --porcelain" in source
    assert "dirty worktree" in source
