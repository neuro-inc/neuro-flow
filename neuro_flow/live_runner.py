import dataclasses

import asyncio
import click
import datetime
import secrets
import shlex
import sys
from neuro_sdk import Client, JobDescription, JobStatus, ResourceNotFound
from rich import box
from rich.console import Console
from rich.table import Table
from types import TracebackType
from typing import (
    AbstractSet,
    AsyncIterator,
    Iterable,
    List,
    Mapping,
    Optional,
    Tuple,
    Type,
)
from typing_extensions import AsyncContextManager

from .config_loader import LiveLocalCL
from .context import ImageCtx, JobMeta, RunningLiveFlow, UnknownJob, VolumeCtx
from .parser import ConfigDir
from .storage import Storage
from .types import TaskStatus
from .utils import (
    RUNNING_JOB_STATUSES,
    TERMINATED_JOB_STATUSES,
    GlobalOptions,
    encode_global_options,
    fmt_datetime,
    fmt_id,
    make_cmd_exec,
)


@dataclasses.dataclass(frozen=True)
class JobInfo:
    id: str
    status: JobStatus
    raw_id: Optional[str]  # low-level job id, None for never runned jobs
    tags: Iterable[str]
    when: Optional[datetime.datetime]


class LiveRunner(AsyncContextManager["LiveRunner"]):
    def __init__(
        self,
        config_dir: ConfigDir,
        console: Console,
        client: Client,
        storage: Storage,
        global_options: GlobalOptions,
    ) -> None:
        self._config_dir = config_dir
        self._console = console
        self._config_loader: Optional[LiveLocalCL] = None
        self._flow: Optional[RunningLiveFlow] = None
        self._client = client
        self._storage = storage
        self._run_neuro_cli = make_cmd_exec(
            "neuro", global_options=encode_global_options(global_options)
        )
        self._run_extras_cli = make_cmd_exec("neuro-extras")

    async def post_init(self) -> None:
        if self._flow is not None:
            return
        self._config_loader = LiveLocalCL(self._config_dir, self._client)
        try:
            self._flow = await RunningLiveFlow.create(self._config_loader)
        except Exception:
            await self._config_loader.close()
            raise

    async def close(self) -> None:
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
    def flow(self) -> RunningLiveFlow:
        assert self._flow is not None
        return self._flow

    @property
    def client(self) -> Client:
        assert self._client is not None
        return self._client

    async def _ensure_meta(
        self, job_id: str, suffix: Optional[str], *, skip_check: bool = False
    ) -> JobMeta:
        try:
            meta = await self.flow.get_meta(job_id)
            if meta.multi:
                if suffix is None:
                    if not skip_check:
                        raise click.BadArgumentUsage(  # type: ignore
                            f"Please provide a suffix for multi-job {fmt_id(job_id)}"
                        )
            else:
                if suffix is not None:
                    raise click.BadArgumentUsage(  # type: ignore
                        f"Suffix is not allowed for non-multijob {fmt_id(job_id)}"
                    )
            return meta
        except UnknownJob:
            self._console.print(f"[red]Unknown job [b]{job_id}[/b]")
            jobs_str = ", ".join(self.flow.job_ids)
            self._console.print(f"[dim]Existing jobs: {jobs_str}")
            sys.exit(1)

    async def _resolve_jobs(
        self, meta: JobMeta, suffix: Optional[str]
    ) -> AsyncIterator[JobDescription]:
        found = False
        if meta.multi and not suffix:
            async for job in self.client.jobs.list(
                tags=meta.tags,
                reverse=True,
            ):
                found = True
                yield job
        else:
            tags = list(meta.tags)
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
        meta = await self._ensure_meta(job_id, None, skip_check=True)
        ret = []
        found_suffixes = set()
        try:
            async for descr in self._resolve_jobs(meta, None):
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
            ret.append(JobInfo(job_id, JobStatus.UNKNOWN, None, meta.tags, None))
        return ret

    async def list_suffixes(self, job_id: str) -> AbstractSet[str]:
        meta = await self._ensure_meta(job_id, None, skip_check=True)
        result = set()
        try:
            async for job in self._resolve_jobs(meta, None):
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
        table = Table(box=box.MINIMAL_HEAVY_HEAD)
        table.add_column("JOB", style="bold")
        table.add_column("STATUS")
        table.add_column("RAW ID", style="bright_black")
        table.add_column("WHEN")

        tasks = []
        for job_id in self.flow.job_ids:
            tasks.append(loop.create_task(self._job_status(job_id)))

        for bulk in await asyncio.gather(*tasks):
            for info in bulk:
                table.add_row(
                    info.id,
                    TaskStatus(info.status),
                    info.raw_id or "N/A",
                    fmt_datetime(info.when),
                )

        self._console.print(table)

    async def status(self, job_id: str, suffix: Optional[str]) -> None:
        meta_ctx = await self._ensure_meta(job_id, suffix)
        try:
            async for descr in self._resolve_jobs(meta_ctx, suffix):
                await self._run_neuro_cli("status", descr.id)
        except ResourceNotFound:
            self._console.print(f"Job [b]{job_id}[/b] is not running")
            sys.exit(1)

    async def _try_attach_to_running(
        self,
        job_id: str,
        suffix: Optional[str],
        args: Optional[Tuple[str]],
        params: Mapping[str, str],
    ) -> bool:
        is_multi = await self.flow.is_multi(job_id)

        if not is_multi or suffix:
            meta = await self._ensure_meta(job_id, suffix)
            try:
                jobs = []
                async for descr in self._resolve_jobs(meta, suffix):
                    jobs.append(descr)
                if len(jobs) > 1:
                    # Should never happen, but just in case
                    raise click.ClickException(  # type: ignore
                        f"Found multiple running jobs for id {job_id} and"
                        f" suffix {suffix}:\n"
                        "\n".join(job.id for job in jobs)
                    )
                assert len(jobs) == 1
                descr = jobs[0]
                if is_multi and args:
                    raise click.ClickException(  # type: ignore
                        "Multi job with such suffix is already running."
                    )
                if descr.status == JobStatus.PENDING:
                    self._console.print(
                        f"Job [b]{job_id}[/b] is pending, " "try again later"
                    )
                    sys.exit(2)
                if descr.status == JobStatus.RUNNING:
                    self._console.print(
                        f"Job [b]{job_id}[/b] is running, " "connecting..."
                    )
                    if not is_multi:
                        job = await self.flow.get_job(job_id, params)
                    else:
                        assert suffix is not None
                        job = await self.flow.get_multi_job(job_id, suffix, (), params)
                    # attach to job if needed, browse first
                    if job.browse:
                        await self._run_neuro_cli("job", "browse", descr.id)
                    if not job.detach:
                        await self._run_neuro_cli("attach", descr.id)
                    return True
                # Here the status is SUCCEED, CANCELLED or FAILED, restart
            except ResourceNotFound:
                # Job does not exist, run it
                pass
        return False

    async def run(
        self,
        job_id: str,
        suffix: Optional[str],
        args: Optional[Tuple[str]],
        params: Mapping[str, str],
        dry_run: bool,
    ) -> None:
        """Run a named job"""

        meta_ctx = await self._ensure_meta(job_id, suffix)
        is_multi = meta_ctx.multi

        if not is_multi and args:
            raise click.BadArgumentUsage(  # type: ignore
                "Additional job arguments are supported by multi-jobs only"
            )

        if await self._try_attach_to_running(job_id, suffix, args, params):
            return  # Attached to running job

        if not is_multi:
            job = await self.flow.get_job(job_id, params)
        else:
            if suffix is None:
                suffix = secrets.token_hex(5)
            job = await self.flow.get_multi_job(job_id, suffix, args, params)

        run_args = ["run"]
        if job.title:
            run_args.append(f"--description={job.title}")
        if job.name:
            run_args.append(f"--name={job.name}")
        if job.preset is not None:
            run_args.append(f"--preset={job.preset}")
        if job.schedule_timeout is not None:
            run_args.append(f"--schedule-timeout={int(job.schedule_timeout)}s")
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
        for k, v in job.env.items():
            run_args.append(f"--env={k}={v}")
        for v in job.volumes:
            run_args.append(f"--volume={v}")
        for t in job.tags:
            run_args.append(f"--tag={t}")
        if job.life_span is not None:
            run_args.append(f"--life-span={int(job.life_span)}s")
        if job.browse:
            run_args.append(f"--browse")
        if job.detach:
            run_args.append(f"--detach")
        for pf in job.port_forward:
            run_args.append(f"--port-forward={pf}")
        if job.pass_config:
            run_args.append(f"--pass-config")

        run_args.append(job.image)
        if job.cmd:
            run_args.extend(shlex.split(job.cmd))

        if job.multi and args:
            run_args.extend(args)

        if dry_run:
            run_args = ["neuro", *run_args]
            self._console.print(
                " ".join(shlex.quote(arg) for arg in run_args), soft_wrap=True
            )
            return

        jobs = []
        for job_id in self.flow.job_ids:
            job_meta = await self.flow.get_meta(job_id)
            jobs.append(job_meta)
        await self._storage.ensure_project(self.flow.flow.project_id)
        await self._storage.write_live(self.flow.flow.project_id, jobs)
        await self._run_neuro_cli(*run_args)

    async def logs(self, job_id: str, suffix: Optional[str]) -> None:
        """Return job logs"""
        meta_ctx = await self._ensure_meta(job_id, suffix)
        try:
            async for descr in self._resolve_jobs(meta_ctx, suffix):
                await self._run_neuro_cli("logs", descr.id)
        except ResourceNotFound:
            self._console.print(f"Job {fmt_id(job_id)} is not running")
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
            self._console.print(f"Killed job [b]{job_id}[/b]")
        else:
            self._console.print(f"Job [b]{job_id}[/b] is not running")

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
            tags=self.flow.tags, statuses=RUNNING_JOB_STATUSES
        ):
            tasks.append(loop.create_task(kill(descr)))

        for job_info in await asyncio.gather(*tasks):
            self._console.print(f"Killed job [b]{job_info}[/b]")

    # volumes subsystem

    async def find_volume(self, volume: str) -> VolumeCtx:
        volume_ctx = self.flow.volumes.get(volume)
        if volume_ctx is None:
            self._console.print(f"[red]Unknown volume [b]{volume}[/b]")
            volumes = sorted([volume for volume in self.flow.volumes.keys()])
            volumes_str = ",".join(volumes)
            self._console.print(f"[dim]Existing volumes: {volumes_str}")
            sys.exit(1)
        if volume_ctx.local is None:
            self._console.print(f"Volume's [b]local[/b] part is not set")
            sys.exit(2)
        return volume_ctx

    async def upload(self, volume: str) -> None:
        volume_ctx = await self.find_volume(volume)
        await self._run_neuro_cli(
            "cp",
            "--recursive",
            "--update",
            "--no-target-directory",
            str(volume_ctx.full_local_path),
            str(volume_ctx.remote),
        )

    async def download(self, volume: str) -> None:
        volume_ctx = await self.find_volume(volume)
        await self._run_neuro_cli(
            "cp",
            "--recursive",
            "--update",
            "--no-target-directory",
            str(volume_ctx.remote),
            str(volume_ctx.full_local_path),
        )

    async def clean(self, volume: str) -> None:
        volume_ctx = await self.find_volume(volume)
        await self._run_neuro_cli("rm", "--recursive", str(volume_ctx.remote))

    async def upload_all(self) -> None:
        for volume in self.flow.volumes.values():
            if volume.local is not None:
                await self.upload(volume.id)

    async def download_all(self) -> None:
        for volume in self.flow.volumes.values():
            if volume.local is not None:
                await self.download(volume.id)

    async def clean_all(self) -> None:
        for volume in self.flow.volumes.values():
            if volume.local is not None:
                await self.clean(volume.id)

    async def mkvolumes(self) -> None:
        for volume in self.flow.volumes.values():
            if volume.local is not None:
                volume_ctx = await self.find_volume(volume.id)
                self._console.print(f"Create volume [b]{volume.id}[/b]")
                await self._run_neuro_cli(
                    "mkdir",
                    "--parents",
                    str(volume_ctx.remote),
                )

    # images subsystem

    async def find_image(self, image: str) -> ImageCtx:
        image_ctx = self.flow.images.get(image)
        if image_ctx is None:
            self._console.print(f"[red]Unknown image [b]{image}[/b]")
            images = sorted([image for image in self.flow.images.keys()])
            images_str = ",".join(images)
            self._console.print(f"[dim]Existing images: {images_str}")
            sys.exit(1)
        if image_ctx.context is None:
            self._console.print(f"Image's [b]context[/b] part is not set")
            sys.exit(2)
        if image_ctx.dockerfile is None:
            self._console.print(f"Image's [b]dockerfile[/b] part is not set")
            sys.exit(3)
        return image_ctx

    async def build(self, image: str, force_overwrite: bool) -> None:
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
        if force_overwrite:
            cmd.append("--force-overwrite")
        if image_ctx.build_preset is not None:
            cmd.append(f"--preset={image_ctx.build_preset}")
        cmd.append(str(image_ctx.full_context_path))
        cmd.append(str(image_ctx.ref))
        await self._run_extras_cli("image", "build", *cmd)

    async def build_all(self, force_overwrite: bool) -> None:
        for image, image_ctx in self.flow.images.items():
            if image_ctx.context is not None:
                await self.build(image, force_overwrite=force_overwrite)
