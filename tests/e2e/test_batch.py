import re
import secrets
from yarl import URL

from tests.e2e.conftest import RunCLI


#  TODO: remove --local-executor when projoect.yml parsing is fixed


async def test_seq_batch(run_cli: RunCLI) -> None:
    random_text = secrets.token_hex(20)
    captured = await run_cli(
        ["bake", "--local-executor", "seq", "--param", "token", random_text]
    )

    assert f"task_b_out: {random_text}" in captured.out

    # Now test the cache:

    captured = await run_cli(
        ["bake", "--local-executor", "seq", "--param", "token", random_text]
    )

    assert "cached" in captured.out


async def test_batch_with_local(
    run_cli: RunCLI,
    run_neuro_cli: RunCLI,
    project_id: str,
    username: str,
    project_role: str,
    cluster_name: str,
) -> None:
    captured = await run_cli(
        [
            "bake",
            "--local-executor",
            "print-local",
            "--param",
            "file_path",
            "rw_dir/initial_file",
        ]
    )

    assert f"file_content: initial_file_content" in captured.out

    m = re.search(r"Task print_readme (job-\S+) is", captured.out)
    assert m is not None
    job_id = m[1]
    job_uri = URL.build(scheme="job", host=cluster_name) / username / job_id
    captured = await run_neuro_cli(["acl", "list", "--shared", str(job_uri)])
    assert sorted(line.split() for line in captured.out.splitlines()) == [
        [f"job:{job_id}", "write", project_role],
    ]


async def test_batch_action(run_cli: RunCLI) -> None:
    captured = await run_cli(["bake", "prime-checks", "--local-executor"])

    assert f"5 is prime" in captured.out
    assert f"4 is not prime" in captured.out
    assert f"3 is prime" in captured.out
