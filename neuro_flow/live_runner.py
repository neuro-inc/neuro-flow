import dataclasses

import asyncio
import click
import datetime
import humanize
import shlex
import sys
from neuromation.api import Client, Factory, JobDescription, JobStatus, ResourceNotFound
from neuromation.cli.formatters import ftable  # TODO: extract into a separate library
from types import TracebackType
from typing import AbstractSet, List, Optional, Tuple, Type
from typing_extensions import AsyncContextManager

from . import ast
from .context import ImageCtx, LiveContext, UnknownJob, VolumeCtx


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
    when: Optional[datetime.datetime]


class LiveRunner(AsyncContextManager["LiveRunner"]):
    def __init__(self, flow: ast.LiveFlow) -> None:
        self._flow = flow
        self._ctx: Optional[LiveContext] = None
        self._client: Optional[Client] = None

    async def post_init(self) -> None:
        if self._ctx is not None:
            return
        self._ctx = await LiveContext.create(self._flow)
        self._client = await Factory().get()

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()

    async def __aenter__(self) -> "LiveRunner":
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
    def ctx(self) -> LiveContext:
        assert self._ctx is not None
        return self._ctx

    @property
    def client(self) -> Client:
        assert self._client is not None
        return self._client

    async def run_subproc(self, exe: str, *args: str) -> None:
        proc = await asyncio.create_subprocess_exec(exe, *args)
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

    async def ensure_job(self, job_id: str) -> LiveContext:
        try:
            return await self.ctx.with_job(job_id)
        except UnknownJob:
            click.secho(f"Unknown job {click.style(job_id, bold=True)}", fg="red")
            jobs = sorted([job for job in self._flow.jobs.keys()])
            jobs_str = ",".join(jobs)
            click.secho(f"Existing jobs: {jobs_str}", dim=True)
            sys.exit(1)

    async def resolve_job_by_name(
        self, name: Optional[str], tags: AbstractSet[str]
    ) -> JobDescription:
        async for job in self.client.jobs.list(
            name=name or "",
            tags=tags,
            reverse=True,
            limit=100,  # fixme: limit should be 1 but it doesn't work
        ):
            return job
        raise ResourceNotFound

    async def job_status(self, job_id: str) -> JobInfo:
        job_ctx = await self.ensure_job(job_id)
        job = job_ctx.job
        try:
            descr = await self.resolve_job_by_name(job.name, job.tags)
            if descr.status == JobStatus.PENDING:
                when = descr.history.created_at
            elif descr.status == JobStatus.RUNNING:
                when = descr.history.started_at
            else:
                when = descr.history.finished_at
            return JobInfo(job_id, descr.status, descr.id, job.tags, when)
        except ResourceNotFound:
            return JobInfo(job_id, JobStatus.UNKNOWN, None, job.tags, None)

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
                click.style("WHEN", bold=True),
            ]
        )
        tasks = []
        for job_id in sorted(self._flow.jobs):
            tasks.append(loop.create_task(self.job_status(job_id)))

        for info in await asyncio.gather(*tasks):
            if info.when is None:
                when_humanized = "N/A"
            else:
                delta = datetime.datetime.now(datetime.timezone.utc) - info.when
                if delta < datetime.timedelta(days=1):
                    when_humanized = humanize.naturaltime(delta)
                else:
                    when_humanized = humanize.naturaldate(info.when.astimezone())
            rows.append(
                [
                    info.id,
                    format_job_status(info.status),
                    info.raw_id or "N/A",
                    when_humanized,
                ]
            )

        for line in ftable.table(rows):
            click.echo(line)

    async def status(self, job_id: str) -> None:
        job_ctx = await self.ensure_job(job_id)
        job = job_ctx.job
        try:
            descr = await self.resolve_job_by_name(job.name, job.tags)
            await self.run_subproc("neuro", "status", descr.id)
        except ResourceNotFound:
            click.echo(f"Job {click.style(job_id, bold=True)} is not running")
            sys.exit(1)

    async def run(self, job_id: str) -> None:
        """Run a named job"""
        job_ctx = await self.ensure_job(job_id)
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
                    await self.run_subproc("neuro", "job", "browse", descr.id)
                if not job.detach:
                    await self.run_subproc("neuro", "attach", descr.id)
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
        for pf in job.port_forward:
            args.append(f"--port-forward={pf}")

        args.append(job.image)
        if job.cmd:
            args.extend(shlex.split(job.cmd))
        await self.run_subproc("neuro", *args)

    async def logs(self, job_id: str) -> None:
        """Return job logs"""
        job_ctx = await self.ensure_job(job_id)
        job = job_ctx.job
        try:
            descr = await self.resolve_job_by_name(job.name, job.tags)
            await self.run_subproc("neuro", "logs", descr.id)
        except ResourceNotFound:
            click.echo(f"Job {click.style(job_id, bold=True)} is not running")
            sys.exit(1)

    async def kill_job(self, job_id: str) -> bool:
        """Kill named job"""
        job_ctx = await self.ensure_job(job_id)
        job = job_ctx.job

        try:
            descr = await self.resolve_job_by_name(job.name, job.tags)
            if descr.status in (JobStatus.PENDING, JobStatus.RUNNING):
                await self.client.jobs.kill(descr.id)
                descr = await self.client.jobs.status(descr.id)
                while descr.status not in (JobStatus.SUCCEEDED, JobStatus.FAILED):
                    await asyncio.sleep(0.2)
                    descr = await self.client.jobs.status(descr.id)
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

    # volumes subsystem

    async def find_volume(self, volume: str) -> VolumeCtx:
        volume_ctx = self.ctx.volumes.get(volume)
        if volume_ctx is None:
            click.secho(f"Unknown volume {click.style(volume, bold=True)}", fg="red")
            volumes = sorted([volume for volume in self.ctx.volumes.keys()])
            volumes_str = ",".join(volumes)
            click.secho(f"Existing volumes: {volumes_str}", dim=True)
            sys.exit(1)
        if volume_ctx.local is None:
            click.echo(f"Volume's {click.style('local', bold=True)} part is not set")
            sys.exit(2)
        return volume_ctx

    async def upload(self, volume: str) -> None:
        volume_ctx = await self.find_volume(volume)
        await self.run_subproc(
            "neuro",
            "cp",
            "--recursive",
            "--update",
            "--no-target-directory",
            str(volume_ctx.full_local_path),
            str(volume_ctx.remote),
        )

    async def download(self, volume: str) -> None:
        volume_ctx = await self.find_volume(volume)
        await self.run_subproc(
            "neuro" "cp",
            "--recursive",
            "--update",
            "--no-target-directory",
            str(volume_ctx.remote),
            str(volume_ctx.full_local_path),
        )

    async def clean(self, volume: str) -> None:
        volume_ctx = await self.find_volume(volume)
        await self.run_subproc("neuro", "rm", "--recursive", str(volume_ctx.remote))

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
                await self.run_subproc(
                    "neuro", "mkdir", "--parents", str(volume_ctx.remote),
                )

    # images subsystem

    async def find_image(self, image: str) -> ImageCtx:
        image_ctx = self.ctx.images.get(image)
        if image_ctx is None:
            click.secho(f"Unknown image {click.style(image, bold=True)}", fg="red")
            images = sorted([image for image in self.ctx.images.keys()])
            images_str = ",".join(images)
            click.secho(f"Existing images: {images_str}", dim=True)
            sys.exit(1)
        if image_ctx.context is None:
            click.echo(f"Image's {click.style('context', bold=True)} part is not set")
            sys.exit(2)
        if image_ctx.dockerfile is None:
            click.echo(
                f"Image's {click.style('dockerfile', bold=True)} part is not set"
            )
            sys.exit(3)
        return image_ctx

    async def build(self, image: str) -> None:
        image_ctx = await self.find_image(image)
        cmd = []
        assert image_ctx.full_dockerfile_path is not None
        assert image_ctx.full_context_path is not None
        rel_dockerfile_path = image_ctx.full_dockerfile_path.relative_to(
            image_ctx.full_context_path
        )
        cmd.append(f"--file={rel_dockerfile_path}")
        for arg in image_ctx.build_args:
            cmd.append(f"--build-arg=arg")
        cmd.append(str(image_ctx.full_context_path))
        cmd.append(str(image_ctx.ref))
        await self.run_subproc("neuro-extras", "image", "build", *cmd)
