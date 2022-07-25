from pathlib import Path

from neuro_flow.cli.flow import Spec, gen_cmd


def test_gen_cmd_no_checkout() -> None:
    spec = Spec("gh:neuro-inc/project1")
    outdir = Path("/outdir")
    cmd = gen_cmd(spec, outdir)
    assert cmd == [
        "cookiecutter",
        "gh:neuro-inc/project1",
        "--output-dir",
        str(outdir),
    ]


def test_gen_cmd_with_checkout() -> None:
    spec = Spec("gh:neuro-inc/project2", checkout="release")
    outdir = Path("/outdir")
    cmd = gen_cmd(spec, outdir)
    assert cmd == [
        "cookiecutter",
        "gh:neuro-inc/project2",
        "--checkout",
        "release",
        "--output-dir",
        str(outdir),
    ]
