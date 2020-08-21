from textwrap import dedent

from neuro_flow.commands import CmdProcessor


async def test_empty() -> None:
    async with CmdProcessor() as proc:
        pass

    assert proc.outputs == {}
    assert proc.states == {}


async def test_no_commands() -> None:
    out = []
    async with CmdProcessor() as proc:
        async for line in proc.feed_chunk(b"123\n34"):
            out.append(line)
        async for line in proc.feed_chunk(b"56\n78"):
            out.append(line)
        async for line in proc.feed_eof():
            out.append(line)

    assert proc.outputs == {}
    assert proc.states == {}
    assert b"".join(out).decode("utf-8") == dedent(
        """\
        123
        3456
        78"""
    )


async def test_set_output1() -> None:
    out = []
    async with CmdProcessor() as proc:
        async for line in proc.feed_chunk(b"::set-output name=key1::value1\n"):
            out.append(line)
        async for line in proc.feed_chunk(b"Just a line\n"):
            out.append(line)
        async for line in proc.feed_chunk(b"::set-output name=key2::value2\n"):
            out.append(line)
        async for line in proc.feed_eof():
            out.append(line)

    assert proc.outputs == {"key1": "value1", "key2": "value2"}
    assert proc.states == {}
    assert b"".join(out).decode("utf-8") == "Just a line\n"


async def test_set_output2() -> None:
    out = []
    async with CmdProcessor() as proc:
        async for line in proc.feed_chunk(b"::set-"):
            out.append(line)
        async for line in proc.feed_chunk(b"output name=key1::value1\n"):
            out.append(line)
        async for line in proc.feed_chunk(b"::set-output name=key2::value2\n"):
            out.append(line)
        async for line in proc.feed_eof():
            out.append(line)

    assert proc.outputs == {"key1": "value1", "key2": "value2"}
    assert proc.states == {}
    assert b"".join(out).decode("utf-8") == dedent("")


async def test_set_output3() -> None:
    out = []
    async with CmdProcessor() as proc:
        async for line in proc.feed_chunk(b"::set-"):
            out.append(line)
        async for line in proc.feed_chunk(b"output name=key1::value1\n"):
            out.append(line)
        async for line in proc.feed_chunk(
            b"::set-output name=key2::value2\nJust a line"
        ):
            out.append(line)
        async for line in proc.feed_eof():
            out.append(line)

    assert proc.outputs == {"key1": "value1", "key2": "value2"}
    assert proc.states == {}
    assert b"".join(out).decode("utf-8") == "Just a line"


async def test_save_state() -> None:
    out = []
    async with CmdProcessor() as proc:
        async for line in proc.feed_chunk(b"::save-state name=key1::value1\n"):
            out.append(line)
        async for line in proc.feed_chunk(b"Just a line\n"):
            out.append(line)
        async for line in proc.feed_chunk(b"::save-state name=key2::value2\n"):
            out.append(line)
        async for line in proc.feed_eof():
            out.append(line)

    assert proc.outputs == {}
    assert proc.states == {"key1": "value1", "key2": "value2"}
    assert b"".join(out).decode("utf-8") == "Just a line\n"


async def test_stop_commands() -> None:
    out = []
    async with CmdProcessor() as proc:
        async for line in proc.feed_chunk(b"::stop-commands::resume\n"):
            out.append(line)
        async for line in proc.feed_chunk(b"::save-state name=key1::value1\n"):
            out.append(line)
        async for line in proc.feed_chunk(b"Just a line\n"):
            out.append(line)
        async for line in proc.feed_chunk(b"::resume::\n"):
            out.append(line)
        async for line in proc.feed_chunk(b"::save-state name=key2::value2\n"):
            out.append(line)
        async for line in proc.feed_eof():
            out.append(line)

    assert proc.outputs == {}
    assert proc.states == {"key2": "value2"}
    assert b"".join(out).decode("utf-8") == dedent(
        """\
        ::save-state name=key1::value1
        Just a line
    """
    )
