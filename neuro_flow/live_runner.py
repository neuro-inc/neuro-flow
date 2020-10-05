import dataclasses

import asyncio
import click
import datetime
import humanize
import secrets
import shlex
import sys
from neuromation.api import Client, Factory, JobDescription, JobStatus, ResourceNotFound
from neuromation.cli.formatters import ftable  # TODO: extract into a separate library
from types import TracebackType
from typing import AbstractSet, AsyncIterator, Iterable, List, Optional, Tuple, Type
from typing_extensions import AsyncContextManager

from .config_loader import LiveLocalCL
from .context import ImageCtx, LiveContext, UnknownJob, VolumeCtx
from .parser import ConfigDir
from .utils import (
    RUNNING_JOB_STATUSES,
    TERMINATED_JOB_STATUSES,
    fmt_id,
    fmt_raw_id,
    fmt_status,
)


@dataclasses.dataclass(frozen=True)
class JobInfo:
    id: str
    status: JobStatus
    raw_id: Optional[str]  # low-level job id, None for never runned jobs
    tags: Iterable[str]
    when: Optional[datetime.datetime]


class LiveRunner(AsyncContextManager["LiveRunner"]):
    def __init__(self, config_dir: ConfigDir) -> None:
        self._config_dir = config_dir
        self._config_loader: Optional[LiveLocalCL] = None
        self._ctx: Optional[LiveContext] = None
        self._client: Optional[Client] = None

    async def post_init(self) -> None:
        if self._ctx is not None:
            return
        self._config_loader = LiveLocalCL(self._config_dir)
        self._ctx = await LiveContext.create(self._config_loader, "live")
        self._client = await Factory().get()

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
        if self._config_loader is not None:
            await self._config_loader.close()

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

    async def _run_subproc(self, exe: str, *args: str) -> None:
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

    async def _ensure_meta(
        self, job_id: str, suffix: Optional[str], *, skip_check: bool = False
    ) -> LiveContext:
        try:
            ctx = await self.ctx.with_meta(job_id)
            if ctx.meta.multi:
                if suffix is None:
                    if not skip_check:
                        raise click.BadArgumentUsage(
                            f"Please provide a suffix for multi-job {fmt_id(job_id)}"
                        )
            else:
                if suffix is not None:
                    raise click.BadArgumentUsage(
                        f"Suffix is not allowed for non-multijob {fmt_id(job_id)}"
                    )
            return ctx
        except UnknownJob:
            click.secho(f"Unknown job {fmt_id(job_id)}", fg="red")
            jobs_str = ",".join(self.ctx.job_ids)
            click.secho(f"Existing jobs: {jobs_str}", dim=True)
            sys.exit(1)

    async def _resolve_jobs(
        self, meta_ctx: LiveContext, suffix: Optional[str]
    ) -> AsyncIterator[JobDescription]:
        meta = meta_ctx.meta
        found = False
        if meta.multi and not suffix:
            async for job in self.client.jobs.list(
                tags=meta_ctx.tags,
                reverse=True,
            ):
                found = True
                yield job
        else:
            tags = list(meta_ctx.tags)
            if meta.multi and suffix:
                tags.append(f"multi:{suffix}")
            async for job in self.client.jobs.list(
                tags=tags,
                reverse=True,
                limit=1,
            ):
                found = True
                yield job
                return
        if not found:
            raise ResourceNotFound

    async def _job_status(self, job_id: str) -> List[JobInfo]:
        meta_ctx = await self._ensure_meta(job_id, None, skip_check=True)
        ret = []
        found_suffixes = set()
        try:
            async for descr in self._resolve_jobs(meta_ctx, None):
                if descr.status == JobStatus.PENDING:
                    when = descr.history.created_at
                elif descr.status == JobStatus.RUNNING:
                    when = descr.history.started_at
                else:
                    when = descr.history.finished_at
                real_id: Optional[str] = None
                for tag in descr.tags:
                    key, sep, val = tag.partition(":")
                    if sep and key == "multi":
                        if val in found_suffixes:
                            break
                        else:
                            found_suffixes.add(val)
                        real_id = f"{job_id} {val}"
                        break
                else:
                    real_id = job_id
                if real_id is not None:
                    ret.append(
                        JobInfo(real_id, descr.status, descr.id, descr.tags, when)
                    )
        except ResourceNotFound:
            ret.append(JobInfo(job_id, JobStatus.UNKNOWN, None, meta_ctx.tags, None))
        return ret

    async def list_suffixes(self, job_id: str) -> AbstractSet[str]:
        meta_ctx = await self._ensure_meta(job_id, None, skip_check=True)
        result = set()
        try:
            async for job in self._resolve_jobs(meta_ctx, None):
                for tag in job.tags:
                    key, sep, val = tag.partition(":")
                    if sep and key == "multi":
                        result.add(val)
        except ResourceNotFound:
            pass
        return result

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
        for job_id in self.ctx.job_ids:
            tasks.append(loop.create_task(self._job_status(job_id)))

        for bulk in await asyncio.gather(*tasks):
            for info in bulk:
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
                        fmt_id(info.id),
                        fmt_status(info.status),
                        fmt_raw_id(info.raw_id or "N/A"),
                        when_humanized,
                    ]
                )

        for line in ftable.table(rows):
            click.echo(line)

    async def status(self, job_id: str, suffix: Optional[str]) -> None:
        meta_ctx = await self._ensure_meta(job_id, suffix)
        try:
            async for descr in self._resolve_jobs(meta_ctx, suffix):
                await self._run_subproc("neuro", "status", descr.id)
        except ResourceNotFound:
            click.echo(f"Job {fmt_id(job_id)} is not running")
            sys.exit(1)

    async def _try_attach_to_running(
        self, job_id: str, suffix: Optional[str], args: Optional[Tuple[str]]
    ) -> bool:
        is_multi = await self.ctx.is_multi(job_id)

        if not is_multi or suffix:
            meta_ctx = await self._ensure_meta(job_id, suffix)
            try:
                jobs = []
                async for descr in self._resolve_jobs(meta_ctx, suffix):
                    jobs.append(descr)
                if len(jobs) > 1:
                    # Should never happen, but just in case
                    raise click.ClickException(
                        f"Found multiple running jobs for id {job_id} and"
                        f" suffix {suffix}:\n"
                        "\n".join(job.id for job in jobs)
                    )
                assert len(jobs) == 1
                descr = jobs[0]
                if is_multi and args:
                    raise click.ClickException(
                        "Multi job with such suffix is already running."
                    )
                if descr.status == JobStatus.PENDING:
                    click.echo(f"Job {fmt_id(job_id)} is pending, " "try again later")
                    sys.exit(2)
                if descr.status == JobStatus.RUNNING:
                    click.echo(f"Job {fmt_id(job_id)} is running, " "connecting...")
                    if not is_multi:
                        job_ctx = await meta_ctx.with_job(job_id)
                        job = job_ctx.job
                    else:
                        assert suffix is not None
                        multi_ctx = await meta_ctx.with_multi(suffix=suffix, args=())
                        job_ctx = await multi_ctx.with_job(job_id)
                        job = job_ctx.job
                    # attach to job if needed, browse first
                    if job.browse:
                        await self._run_subproc("neuro", "job", "browse", descr.id)
                    if not job.detach:
                        await self._run_subproc("neuro", "attach", descr.id)
                    return True
                # Here the status is SUCCEED, CANCELLED or FAILED, restart
            except ResourceNotFound:
                # Job does not exist, run it
                pass
        return False

    async def run(
        self, job_id: str, suffix: Optional[str], args: Optional[Tuple[str]]
    ) -> None:
        """Run a named job"""

        is_multi = await self.ctx.is_multi(job_id)

        if not is_multi and args:
            raise click.BadArgumentUsage(
                "Additional job arguments are supported by multi-jobs only"
            )

        if await self._try_attach_to_running(job_id, suffix, args):
            return  # Attached to running job

        if not is_multi:
            meta_ctx = await self._ensure_meta(job_id, suffix)
            job_ctx = await meta_ctx.with_job(job_id)
            job = job_ctx.job
        else:
            if suffix is None:
                suffix = secrets.token_hex(5)
            meta_ctx = await self._ensure_meta(job_id, suffix)
            multi_ctx = await meta_ctx.with_multi(suffix=suffix, args=args)
            job_ctx = await multi_ctx.with_job(job_id)
            job = job_ctx.job

        run_args = ["run"]
        if job.title:
            run_args.append(f"--description={job.title}")
        if job.name:
            run_args.append(f"--name={job.name}")
        if job.preset is not None:
            run_args.append(f"--preset={job.preset}")
        if job.http_port is not None:
            run_args.append(f"--http={job.http_port}")
        if job.http_auth is not None:
            if job.http_auth:
                run_args.append(f"--http-auth")
            else:
                run_args.append(f"--no-http-auth")
        if job.entrypoint:
            run_args.append(f"--entrypoint={job.entrypoint}")
        if job.workdir is not None:
            run_args.append(f"--workdir={job.workdir}")
        for k, v in job_ctx.env.items():
            run_args.append(f"--env={k}={v}")
        for v in job.volumes:
            run_args.append(f"--volume={v}")
        for t in job_ctx.tags:
            run_args.append(f"--tag={t}")
        if job.life_span is not None:
            run_args.append(f"--life-span={int(job.life_span)}s")
        if job.browse:
            run_args.append(f"--browse")
        if job.detach:
            run_args.append(f"--detach")
        for pf in job.port_forward:
            run_args.append(f"--port-forward={pf}")

        run_args.append(job.image)
        if job.cmd:
            run_args.extend(shlex.split(job.cmd))

        if job.multi and args:
            run_args.extend(args)

        await self._run_subproc("neuro", *run_args)

    async def logs(self, job_id: str, suffix: Optional[str]) -> None:
        """Return job logs"""
        meta_ctx = await self._ensure_meta(job_id, suffix)
        try:
            async for descr in self._resolve_jobs(meta_ctx, suffix):
                await self._run_subproc("neuro", "logs", descr.id)
        except ResourceNotFound:
            click.echo(f"Job {fmt_id(job_id)} is not running")
            sys.exit(1)

    async def kill_job(self, job_id: str, suffix: Optional[str]) -> bool:
        """Kill named job"""
        meta_ctx = await self._ensure_meta(job_id, suffix)

        try:
            async for descr in self._resolve_jobs(meta_ctx, suffix):
                if descr.status in RUNNING_JOB_STATUSES:
                    await self.client.jobs.kill(descr.id)
                    descr = await self.client.jobs.status(descr.id)
                    while descr.status not in TERMINATED_JOB_STATUSES:
                        await asyncio.sleep(0.2)
                        descr = await self.client.jobs.status(descr.id)
                    return True
        except ResourceNotFound:
            pass
        return False

    async def kill(self, job_id: str, suffix: Optional[str]) -> None:
        """Kill named job"""
        if await self.kill_job(job_id, suffix):
            click.echo(f"Killed job {fmt_id(job_id)}")
        else:
            click.echo(f"Job {fmt_id(job_id)} is not running")

    async def kill_all(self) -> None:
        """Kill all jobs"""
        tasks = []
        loop = asyncio.get_event_loop()

        async def kill(descr: JobDescription) -> str:
            tag_dct = {}
            for tag in descr.tags:
                key, sep, val = tag.partition(":")
                if sep:
                    tag_dct[key] = val
            job_id = tag_dct["job"]
            suffix = tag_dct.get("multi")
            await self.client.jobs.kill(descr.id)
            try:
                descr = await self.client.jobs.status(descr.id)
                while descr.status not in TERMINATED_JOB_STATUSES:
                    await asyncio.sleep(0.2)
                    descr = await self.client.jobs.status(descr.id)
            except ResourceNotFound:
                pass
            if suffix:
                return f"{job_id} {suffix}"
            else:
                return job_id

        async for descr in self.client.jobs.list(
            tags=self.ctx.tags, statuses=RUNNING_JOB_STATUSES
        ):
            tasks.append(loop.create_task(kill(descr)))

        for job_id, ret in await asyncio.gather(*tasks):
            click.echo(f"Killed job {fmt_id(job_id)}")

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
        await self._run_subproc(
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
        await self._run_subproc(
            "neuro",
            "cp",
            "--recursive",
            "--update",
            "--no-target-directory",
            str(volume_ctx.remote),
            str(volume_ctx.full_local_path),
        )

    async def clean(self, volume: str) -> None:
        volume_ctx = await self.find_volume(volume)
        await self._run_subproc("neuro", "rm", "--recursive", str(volume_ctx.remote))

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
                click.echo(f"Create volume {fmt_id(volume.id)}")
                await self._run_subproc(
                    "neuro",
                    "mkdir",
                    "--parents",
                    str(volume_ctx.remote),
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
            cmd.append(f"--build-arg={arg}")
        for vol in image_ctx.volumes:
            cmd.append(f"--volume={vol}")
        for k, v in image_ctx.env.items():
            cmd.append(f"--env={k}={v}")
        cmd.append(str(image_ctx.full_context_path))
        cmd.append(str(image_ctx.ref))
        await self._run_subproc("neuro-extras", "image", "build", *cmd)

    async def build_all(self) -> None:
        for image, image_ctx in self.ctx.images.items():
            if image_ctx.context is not None:
                await self.build(image)
