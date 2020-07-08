import asyncio
import dataclasses
import sys
from types import TracebackType
from typing import AbstractSet, List, Optional, Tuple, Type

import click
from neuromation.api import Client, Factory, JobDescription, JobStatus, ResourceNotFound
from neuromation.cli.formatters import ftable  # TODO: extract into a separate library
from typing_extensions import AsyncContextManager

from . import ast
from .context import Context, VolumeCtx


COLORS = {
    JobStatus.PENDING: "yellow",
    JobStatus.RUNNING: "blue",
    JobStatus.SUCCEEDED: "green",
    JobStatus.FAILED: "red",
    JobStatus.UNKNOWN: "yellow",
}


def format_job_status(status: JobStatus) -> str:
    return click.style(status.value, fg=COLORS.get(status, "reset"))


@dataclasses.dataclass(frozen=True)
class JobInfo:
    id: str
    status: JobStatus
    raw_id: Optional[str]  # low-level job id, None for never runned jobs
    tags: AbstractSet[str]


class InteractiveRunner(AsyncContextManager["InteractiveRunner"]):
    def __init__(self, flow: ast.InteractiveFlow) -> None:
        self._flow = flow
        self._ctx: Optional[Context] = None
        self._client: Optional[Client] = None

    async def post_init(self) -> None:
        if self._ctx is not None:
            return
        self._ctx = await Context.create(self._flow)
        self._client = await Factory().get()

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()

    async def __aenter__(self) -> "InteractiveRunner":
        await self.post_init()
        return self

    async def __aexit__(
        self,
        exc_typ: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        await self.close()

    @property
    def ctx(self) -> Context:
        assert self._ctx is not None
        return self._ctx

    @property
    def client(self) -> Client:
        assert self._client is not None
        return self._client

    async def resolve_job_by_name(
        self, name: Optional[str], tags: AbstractSet[str]
    ) -> JobDescription:
        async for job in self.client.jobs.list(
            name=name or "",
            tags=tags,
            reverse=True,
            limit=10,  # fixme: limit should be 1 but it doesn't work
            # statuses={JobStatus.PENDING, JobStatus.RUNNING, JobStatus.FAILED},
        ):
            return job
        raise ResourceNotFound

    async def job_status(self, job_id: str) -> JobInfo:
        job_ctx = await self.ctx.with_job(job_id)
        job = job_ctx.job
        try:
            descr = await self.resolve_job_by_name(job.name, job.tags)
            return JobInfo(job_id, descr.status, descr.id, job.tags)
        except ResourceNotFound:
            return JobInfo(job_id, JobStatus.UNKNOWN, None, job.tags)

    async def ps(self) -> None:
        """Return statuses for all jobs from the flow"""

        # TODO: make concurent queries for job statuses
        loop = asyncio.get_event_loop()
        rows: List[List[str]] = []
        rows.append(
            [
                click.style("JOB", bold=True),
                click.style("STATUS", bold=True),
                click.style("RAW ID", bold=True),
                click.style("TAGS", bold=True),
            ]
        )
        tasks = []
        for job_id in sorted(self._flow.jobs):
            tasks.append(loop.create_task(self.job_status(job_id)))

        for info in await asyncio.gather(*tasks):
            rows.append(
                [
                    info.id,
                    format_job_status(info.status),
                    info.raw_id or "N/A",
                    ",".join(sorted(info.tags)),
                ]
            )

        for line in ftable.table(rows):
            click.echo(line)

    async def status(self, job_id: str) -> None:
        job_ctx = await self.ctx.with_job(job_id)
        job = job_ctx.job
        try:
            descr = await self.resolve_job_by_name(job.name, job.tags)
            await self.run_neuro("status", descr.id)
        except ResourceNotFound:
            click.echo(f"Job {click.style(job_id, bold=True)} is not running")
            sys.exit(1)

    async def run(self, job_id: str) -> None:
        """Run a named job"""
        job_ctx = await self.ctx.with_job(job_id)
        job = job_ctx.job

        try:
            descr = await self.resolve_job_by_name(job.name, job.tags)
            if descr.status == JobStatus.PENDING:
                click.echo(
                    f"Job {click.style(job_id, bold=True)} is pending, try again later"
                )
                sys.exit(2)
            if descr.status == JobStatus.RUNNING:
                click.echo(
                    f"Job {click.style(job_id, bold=True)} is running, connecting..."
                )
                # attach to job if needed, browse first
                if job.browse:
                    await self.run_neuro("job", "browse", descr.id)
                if not job.detach:
                    await self.run_neuro("attach", descr.id)
                return
            # Here the status is SUCCEDED or FAILED, restart
        except ResourceNotFound:
            # Job does not exist, run it
            pass
        args = ["run"]
        if job.title:
            args.append(f"--description={job.title}")
        if job.name:
            args.append(f"--name={job.name}")
        if job.preset is not None:
            args.append(f"--preset={job.preset}")
        if job.http_port is not None:
            args.append(f"--http={job.http_port}")
        if job.http_auth is not None:
            if job.http_auth:
                args.append(f"--http-auth")
            else:
                args.append(f"--no-http-auth")
        if job.entrypoint:
            args.append(f"--entrypoint={job.entrypoint}")
        if job.workdir is not None:
            raise NotImplementedError("workdir is not supported")
        for k, v in job_ctx.env.items():
            args.append(f"--env={k}={v}")
        for v in job.volumes:
            args.append(f"--volume={v}")
        for t in job.tags:
            args.append(f"--tag={t}")
        if job.life_span is not None:
            args.append(f"--life-span={int(job.life_span)}s")
        if job.browse:
            args.append(f"--browse")
        if job.detach:
            args.append(f"--detach")

        args.append(job.image)
        if job.cmd:
            args.append(job.cmd)
        await self.run_neuro(*args)

    async def run_neuro(self, *args: str) -> None:
        proc = await asyncio.create_subprocess_exec("neuro", *args)
        try:
            retcode = await proc.wait()
            if retcode:
                raise SystemExit(retcode)
        finally:
            if proc.returncode is None:
                # Kill neuro process if not finished
                # (e.g. if KeyboardInterrupt or cancellation was received)
                proc.kill()
                await proc.wait()

    async def logs(self, job_id: str) -> None:
        """Return job logs"""
        job_ctx = await self.ctx.with_job(job_id)
        job = job_ctx.job
        try:
            descr = await self.resolve_job_by_name(job.name, job.tags)
            await self.run_neuro("logs", descr.id)
        except ResourceNotFound:
            click.echo(f"Job {click.style(job_id, bold=True)} is not running")
            sys.exit(1)

    async def kill_job(self, job_id: str) -> bool:
        """Kill named job"""
        job_ctx = await self.ctx.with_job(job_id)
        job = job_ctx.job

        try:
            descr = await self.resolve_job_by_name(job.name, job.tags)
            if descr.status in (JobStatus.PENDING, JobStatus.RUNNING):
                await self.client.jobs.kill(raw_id)
                descr = await self.client.jobs.status(raw_id)
                while descr.status not in (JobStatus.SUCCEEDED, JobStatus.FAILED):
                    await asyncio.sleep(0.2)
                    descr = await self.client.jobs.status(raw_id)
                return True
        except ResourceNotFound:
            pass
        return False

    async def kill(self, job_id: str) -> None:
        """Kill named job"""
        if await self.kill_job(job_id):
            click.echo(f"Killed job {click.style(job_id, bold=True)}")
        else:
            click.echo(f"Job {click.style(job_id, bold=True)} is not running")

    async def kill_all(self) -> None:
        """Kill all jobs"""
        tasks = []
        loop = asyncio.get_event_loop()

        async def kill(job_id: str) -> Tuple[str, bool]:
            return job_id, await self.kill_job(job_id)

        for job_id in sorted(self._flow.jobs):
            tasks.append(loop.create_task(kill(job_id)))

        for job_id, ret in await asyncio.gather(*tasks):
            if ret:
                click.echo(f"Killed job {click.style(job_id, bold=True)}")
            else:
                click.echo(f"Job {click.style(job_id, bold=True)} is not running")

    async def find_volume(self, volume: str) -> VolumeCtx:
        volume_ctx = self.ctx.volumes.get(volume)
        if volume_ctx is None:
            click.echo(f"Unknown volume {click.style(volume, bold=True)}")
            sys.exit(1)
        if volume_ctx.local is None:
            click.echo(f"Volume's {click.style('local', bold=True)} part is not set")
            sys.exit(2)
        return volume_ctx

    async def upload(self, volume: str) -> None:
        volume_ctx = await self.find_volume(volume)
        await self.run_neuro(
            "cp",
            "--recursive",
            "--update",
            "--no-target-directory",
            str(volume_ctx.local),
            str(volume_ctx.uri),
        )

    async def download(self, volume: str) -> None:
        volume_ctx = await self.find_volume(volume)
        await self.run_neuro(
            "cp",
            "--recursive",
            "--update",
            "--no-target-directory",
            str(volume_ctx.uri),
            str(volume_ctx.local),
        )

    async def clean(self, volume: str) -> None:
        volume_ctx = await self.find_volume(volume)
        await self.run_neuro("rm", "--recursive", str(volume_ctx.uri))

    async def upload_all(self) -> None:
        for volume in self.ctx.volumes.values():
            if volume.local is not None:
                await self.upload(volume.id)

    async def download_all(self) -> None:
        for volume in self.ctx.volumes.values():
            if volume.local is not None:
                await self.download(volume.id)

    async def clean_all(self) -> None:
        for volume in self.ctx.volumes.values():
            if volume.local is not None:
                await self.clean(volume.id)

    async def mkvolumes(self) -> None:
        for volume in self.ctx.volumes.values():
            if volume.local is not None:
                volume_ctx = await self.find_volume(volume.id)
                click.echo(f"Create volume {click.style(volume.id, bold=True)}")
                await self.run_neuro(
                    "mkdir", "--parents", str(volume_ctx.uri),
                )
