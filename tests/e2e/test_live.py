import json
import pathlib
import secrets

from tests.e2e.conftest import RunCLI


def test_live_context(ws: pathlib.Path, run_cli: RunCLI, project_id: str) -> None:
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
            "project_id": project_id,
            "workspace": str(ws),
            "title": "Test live config",
        },
        "env": {"FOO": "FOO_ENV"},
        "tags": ["flow:live", f"project:{project_id.replace('_', '-')}"],
        "volumes": {
            "ro_dir": {
                "id": "ro_dir",
                "remote": f"storage:neuro-flow-e2e/{project_id}/ro_dir",
                "mount": "/project/ro_dir",
                "read_only": True,
                "local": "ro_dir",
                "full_local_path": str(ws / "ro_dir"),
            },
            "rw_dir": {
                "id": "rw_dir",
                "remote": f"storage:neuro-flow-e2e/{project_id}/rw_dir",
                "mount": "/project/rw_dir",
                "read_only": False,
                "local": "rw_dir",
                "full_local_path": str(ws / "rw_dir"),
            },
        },
        "images": {
            "img": {
                "id": "img",
                "ref": f"image:neuro-flow-e2e/{project_id}:v1.0",
                "context": str(ws),
                "full_context_path": str(ws),
                "dockerfile": str(ws / "Dockerfile"),
                "full_dockerfile_path": str(ws / "Dockerfile"),
                "build_preset": None,
                "build_args": [],
                "env": {},
                "volumes": [],
            }
        },
        "params": {"arg1": "cli-value", "arg2": "val2"},
    }


def test_volumes(ws: pathlib.Path, run_cli: RunCLI) -> None:
    run_cli(["mkvolumes"])
    run_cli(["upload", "ALL"])
    random_text = secrets.token_hex(20)
    (ws / "ro_dir/updated_file").write_text(random_text)
    captured = run_cli(["run", "volumes_test"])
    assert "initial_file_content" in captured.out
    assert random_text in captured.out


def test_image_build(run_cli: RunCLI, run_neuro_cli: RunCLI, project_id: str) -> None:
    try:
        run_cli(["build", "img"])
        random_text = secrets.token_hex(20)
        captured = run_cli(
            ["run", "image_py", "--param", "py_script", f"print('{random_text}')"]
        )
        assert random_text in captured.out
    finally:
        image_uri = f"image:neuro-flow-e2e/{project_id}"
        run_neuro_cli(["image", "rm", image_uri])
