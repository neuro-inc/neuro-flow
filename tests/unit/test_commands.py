from neuro_flow.commands import CmdProcessor


async def test_empty():
    async with CmdProcessor() as proc:
        pass

    assert proc.outputs == {}
    assert proc.states == {}


async def test_no_commands():
    async with CmdProcessor() as proc:
        await proc.feed_chunk(b"123\n34")
        await proc.feed_chunk(b"56\n78")

    assert proc.outputs == {}
    assert proc.states == {}


async def test_set_output1():
    async with CmdProcessor() as proc:
        await proc.feed_chunk(b"::set-output name=key1::value1\n")
        await proc.feed_chunk(b"Just a line\n")
        await proc.feed_chunk(b"::set-output name=key2::value2\n")

    assert proc.outputs == {"key1": "value1", "key2": "value2"}
    assert proc.states == {}


async def test_set_output2():
    async with CmdProcessor() as proc:
        await proc.feed_chunk(b"::set-")
        await proc.feed_chunk(b"output name=key1::value1\n")
        await proc.feed_chunk(b"::set-output name=key2::value2\n")

    assert proc.outputs == {"key1": "value1", "key2": "value2"}
    assert proc.states == {}


async def test_set_output3():
    async with CmdProcessor() as proc:
        await proc.feed_chunk(b"::set-")
        await proc.feed_chunk(b"output name=key1::value1\n")
        await proc.feed_chunk(b"::set-output name=key2::value2\nJust a line")

    assert proc.outputs == {"key1": "value1", "key2": "value2"}
    assert proc.states == {}


async def test_save_state():
    async with CmdProcessor() as proc:
        await proc.feed_chunk(b"::save-state name=key1::value1\n")
        await proc.feed_chunk(b"Just a line\n")
        await proc.feed_chunk(b"::save-state name=key2::value2\n")

    assert proc.outputs == {}
    assert proc.states == {"key1": "value1", "key2": "value2"}


async def test_stop_commands():
    async with CmdProcessor() as proc:
        await proc.feed_chunk(b"::stop-commands::resume\n")
        await proc.feed_chunk(b"::save-state name=key1::value1\n")
        await proc.feed_chunk(b"Just a line\n")
        await proc.feed_chunk(b"::resume::\n")
        await proc.feed_chunk(b"::save-state name=key2::value2\n")

    assert proc.outputs == {}
    assert proc.states == {"key2": "value2"}
