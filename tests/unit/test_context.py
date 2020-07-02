from neuro_flow.context import InavailableContext


def test_inavailable_context_ctor() -> None:
    err = InavailableContext("job")
    assert err.args == ("Context job is not available",)
    assert str(err) == "Context job is not available"
