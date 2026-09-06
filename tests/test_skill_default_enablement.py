"""Default Skill startup in synthetic profiles; no real service or model calls."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

import dev_server
import launcher
import server
from code_runtime import data_dir_owner, skill_runtime_startup, skill_store
from tests.test_skill_runtime_startup import _fixture, _tree, _CrashOnce
from tests.test_skill_store_management import apply as apply_management


FLAGS = ("CODE_SKILL_IMMUTABLE_ADMISSION_V1", "CODE_SKILL_MODEL_LOADING_V1")


@pytest.mark.parametrize("value,expected", [(None, True), ("", True), ("true", True), ("0", False)])
def test_fresh_import_resolves_defaults_without_initializing_data(tmp_path, value, expected):
    env = os.environ.copy()
    for key in (*FLAGS, "CODE_SKILL_COMPLETION_ENFORCEMENT_V1", "CODE_SKILL_ACTIVATION_V1"):
        env.pop(key, None)
    if value is not None:
        env.update({key: value for key in FLAGS})
    data = tmp_path / "profile"
    env.update(CODE_DATA_DIR=str(data), PYTHONDONTWRITEBYTECODE="1")
    script = """import json, server
print(json.dumps([server._SKILL_IMMUTABLE_ADMISSION_ENABLED,
                  server._SKILL_MODEL_LOADING_ENABLED,
                  server._SKILL_COMPLETION_ENFORCEMENT_ENABLED,
                  server._SKILL_ACTIVATION_ENABLED]))
"""
    result = subprocess.run([sys.executable, "-B", "-c", script], env=env,
                            cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True, timeout=30, check=True)
    assert json.loads(result.stdout) == [expected, expected, False, False]
    assert not data.exists()  # changing a default cannot bypass the startup owner


@pytest.mark.parametrize("entry", ["server", "dev", "launcher"])
@pytest.mark.parametrize("fresh", [False, True])
@pytest.mark.parametrize("value,enabled", [(None, True), ("", True), ("true", True), ("off", False)])
def test_all_entrypoints_use_owned_default_startup(tmp_path, monkeypatch, entry, fresh, value, enabled):
    data, bundle, _ = _fixture(tmp_path)
    if fresh:
        data = tmp_path / "fresh-profile"
        data.mkdir()
    app = tmp_path / "app"
    (app / "data").mkdir(parents=True)
    shutil.move(str(bundle), app / "data" / "skills")
    for key in FLAGS:
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    monkeypatch.setattr(server, "_SKILL_IMMUTABLE_ADMISSION_ENABLED", server._resolve_skill_immutable_admission_enabled())
    monkeypatch.setattr(server, "_SKILL_MODEL_LOADING_ENABLED", server._resolve_skill_model_loading_enabled())
    runtime = skill_runtime_startup.ImmutableSkillStartupRuntime()
    monkeypatch.setattr(server, "_immutable_skill_startup_runtime", runtime)
    monkeypatch.setattr(server, "APP_DIR", app)
    monkeypatch.setattr(server, "DATA_DIR", data)
    # Stop at the next startup phase: real owner/Skill IO, no listener, tray,
    # unrelated migrations, route catalog, or background indexing.
    class StartupObserved(Exception):
        pass

    def observe():
        assert runtime.snapshot()["status"] == ("ready" if enabled else "disabled")
        assert (runtime.admission_reader() is not None) is enabled
        assert server._SKILL_MODEL_LOADING_ENABLED is enabled
        if enabled:
            binding = runtime.admission_reader().read_registry()["bindings"][0]
            assert binding["state"] == ("blocked" if fresh and entry != "launcher" else "ready")
            if fresh and entry != "launcher":
                assert binding["reasonCode"] == "legacy-root-missing"
        raise StartupObserved

    monkeypatch.setattr(server, "_ensure_runtime_data_directories", lambda: None)
    monkeypatch.setattr(server, "_initialize_runtime_data_services", observe)
    monkeypatch.chdir(tmp_path)
    # All launcher pre-startup side effects stay within this fixture or are
    # replaced with no-ops; bundled Skill sync itself remains real.
    monkeypatch.setattr(launcher, "get_code_home", lambda: data)
    monkeypatch.setattr(launcher, "get_base_dir", lambda: app)
    monkeypatch.setattr(launcher, "ensure_dirs", lambda: data)
    monkeypatch.setattr(launcher, "migrate_old_data_dir", lambda: None)
    monkeypatch.setattr(launcher, "ensure_installed", lambda **_: None)
    monkeypatch.setattr(launcher, "should_reuse_browser", lambda _: True)
    monkeypatch.setenv("CODE_DEV_DATA_DIR", str(data))
    # Register environment/attribute restoration before entrypoint assignment.
    for key in ("CODE_PORT", "CODE_DATA_DIR", "CODE_RESTART_ENTRY", "CODE_INSTANCE_MODE"):
        monkeypatch.setenv(key, os.environ.get(key, ""))
    for key in ("SESSIONS_DIR", "MEMORY_DIR", "SKILLS_DIR", "ATTACHMENTS_DIR", "FILE_BACKUP_DIR", "CONFIG_PATH"):
        monkeypatch.setattr(server, key, getattr(server, key))
    owners = []

    def acquire(path):
        owner = data_dir_owner.acquire_data_dir_owner(path)
        owners.append(owner)
        return owner

    try:
        with pytest.raises(StartupObserved):
            if entry == "server":
                server.run_server(owner_acquire=acquire)
            elif entry == "dev":
                dev_server.run_dev_server(server_module=server, ensure_frontend=lambda: False, owner_acquire=acquire)
            else:
                launcher._main(owner_acquire=acquire)
        assert len(owners) == 1 and not owners[0].released
        assert (data / skill_store.STORE_DIRECTORY).exists() is enabled
    finally:
        for owner in owners:
            owner.release()


@pytest.mark.parametrize("profile", ["fresh", "legacy", "modified", "tombstone", "v1", "v2-disabled", "pending", "corrupt"])
@pytest.mark.parametrize("off", [False, True])
def test_default_and_opt_out_preserve_profile_contract(tmp_path, profile, off):
    data, bundle, catalog = _fixture(tmp_path)
    if profile == "fresh":
        data = tmp_path / "fresh-profile"
        data.mkdir()
    elif profile == "modified":
        (data / "skills" / "alpha" / "SKILL.md").write_text("local modification", encoding="utf-8")
    elif profile == "tombstone":
        (data / "bundled-skills-state.json").write_text(json.dumps({
            "schema": "code-bundled-skills/v1", "tombstones": ["alpha"],
        }), encoding="utf-8")
    store = skill_store.SkillStore(data, bundle, write_enabled=True)
    if profile in {"v1", "v2-disabled"}:
        store.bootstrap(catalog)
    elif profile == "pending":
        store.fault_injector = _CrashOnce("after-registry-publish")
        with pytest.raises(skill_store.SkillStoreInterruption):
            store.bootstrap(catalog)
    elif profile == "corrupt":
        store.root.mkdir()
        (store.root / "unknown").write_text("preserve", encoding="utf-8")
    with data_dir_owner.acquire_data_dir_owner(data) as owner:
        if profile == "v2-disabled":
            from code_runtime.skill_store_management import SkillStoreManager
            manager = SkillStoreManager(store, owner=owner)
            apply_management(manager, "convert", {"kind": "convert-v2"})
            item = store.read_registry()["installations"][0]
            apply_management(manager, "disable", {"kind": "set-enabled", "installationId": item["installationId"], "enabled": False})
        before = _tree(data)
        legacy_before = _tree(data / "skills")
        runtime = skill_runtime_startup.ImmutableSkillStartupRuntime()
        enabled = server._resolve_skill_immutable_admission_enabled({FLAGS[0]: "off"} if off else {})
        kwargs = dict(owner=owner, data_root=data, bundled_root=bundle, admission_enabled=enabled)
        if profile == "corrupt" and not off:
            with pytest.raises(skill_runtime_startup.ImmutableSkillStartupError) as error:
                runtime.initialize(**kwargs)
            assert error.value.code == "store_layout_unknown"
        else:
            state = runtime.initialize(**kwargs)
            assert state["status"] == ("unavailable" if profile == "corrupt" else
                                       "disabled" if off and profile not in {"v1", "v2-disabled", "pending"} else "ready")
        if profile in {"v1", "v2-disabled", "corrupt"} or (off and profile != "pending"):
            assert _tree(data) == before
        assert _tree(data / "skills") == legacy_before
        reader = runtime.recovery_reader()
        assert (runtime.admission_reader() is not None) is (reader is not None and not off)
        if reader:
            registry = reader.read_registry()
            assert registry["schema"] == ("code-skill-install-registry/v2" if profile == "v2-disabled" else "code-skill-install-registry/v1")
            if profile == "v2-disabled":
                assert registry["installations"][0]["enabled"] is False
            if profile in {"fresh", "modified", "tombstone"}:
                binding = registry["bindings"][0]
                assert binding["state"] == "blocked" and binding["activeCandidate"] is None
