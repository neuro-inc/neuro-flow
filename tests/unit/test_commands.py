from neuro_flow.commands import CmdProcessor


async def test_empty():
    async with CmdProcessor() as proc:
        pass

    assert proc.outputs == {}
    assert proc.envs == {}
    assert proc.states == {}


async def test_no_commands():
    async with CmdProcessor() as proc:
        await proc.feed_chunk(b"123\n34")
        await proc.feed_chunk(b"56\n78")

    assert proc.outputs == {}
    assert proc.envs == {}
    assert proc.states == {}
