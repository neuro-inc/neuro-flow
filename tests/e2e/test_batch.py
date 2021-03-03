import secrets

from tests.e2e.conftest import RunCLI


#  TODO: remove --local-executor when projoect.yml parsing is fixed


def test_seq_batch(run_cli: RunCLI) -> None:
    random_text = secrets.token_hex(20)
    captured = run_cli(
        ["bake", "--local-executor", "seq", "--param", "token", random_text]
    )

    assert f"task_b_out: {random_text}" in captured.out

    # Now test the cache:

    captured = run_cli(
        ["bake", "--local-executor", "seq", "--param", "token", random_text]
    )

    assert "cached" in captured.out


def test_batch_with_local(run_cli: RunCLI) -> None:
    captured = run_cli(
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


def test_batch_action(run_cli: RunCLI) -> None:
    captured = run_cli(["bake", "prime-checks", "--local-executor"])

    assert f"5 is prime" in captured.out
    assert f"4 is not prime" in captured.out
    assert f"3 is prime" in captured.out
