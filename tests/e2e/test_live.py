import json
import pathlib
import secrets

from tests.e2e.conftest import RunCLI


def test_live_context(assets: pathlib.Path, run_cli: RunCLI):
    captured = run_cli(["run", "job_ctx_full", "--param", "arg1", "cli-value"])

    DUMP_START_MARK = "DUMP_START"
    DUMP_START_END = "DUMP_END"
    mark_found = False
    json_str = ""

    for line in captured.out.splitlines():
        if line == DUMP_START_MARK:
            mark_found = True
        elif line == DUMP_START_END:
            break
        elif mark_found:
            json_str += line

    assert json.loads(json_str) == {
        "flow": {
            "flow_id": "live",
            "project_id": "e2e_test_project",
            "workspace": str(assets / "ws"),
            "title": "Test live config",
        },
        "env": {"FOO": "FOO_ENV"},
        "tags": ["flow:live", "project:e2e-test-project"],
        "volumes": {
            "ro_dir": {
                "id": "ro_dir",
                "remote": "storage:neuro-flow-e2e/e2e_test_project/ro_dir",
                "mount": "/project/ro_dir",
                "read_only": True,
                "local": "ro_dir",
                "full_local_path": str(assets / "ws/ro_dir"),
            },
            "rw_dir": {
                "id": "rw_dir",
                "remote": "storage:neuro-flow-e2e/e2e_test_project/rw_dir",
                "mount": "/project/rw_dir",
                "read_only": False,
                "local": "rw_dir",
                "full_local_path": str(assets / "ws/rw_dir"),
            },
        },
        "images": {
            "img": {
                "id": "img",
                "ref": "image:e2e_test_project:v1.0",
                "context": str(assets / "ws"),
                "full_context_path": str(assets / "ws"),
                "dockerfile": str(assets / "ws/Dockerfile"),
                "full_dockerfile_path": str(assets / "ws/Dockerfile"),
                "build_args": [],
                "env": {},
                "volumes": [],
            }
        },
        "params": {"arg1": "cli-value", "arg2": "val2"},
    }


def test_volumes(assets: pathlib.Path, run_cli: RunCLI):
    run_cli(["mkvolumes"])
    run_cli(["upload", "ALL"])
    random_text = secrets.token_hex(20)
    (assets / "ws/ro_dir/updated_file").write_text(random_text)
    captured = run_cli(["run", "volumes_test"])
    assert "initial_file_content" in captured.out
    assert random_text in captured.out


def test_image_build(assets: pathlib.Path, run_cli: RunCLI):
    run_cli(["build", "img"])
    random_text = secrets.token_hex(20)
    captured = run_cli(
        ["run", "image_py", "--param", "py_script", f"print('{random_text}')"]
    )
    assert random_text in captured.out
