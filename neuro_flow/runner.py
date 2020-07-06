import asyncio
from typing import AsyncIterator, List, Optional

import click
from neuromation.api import Client, Factory, JobStatus, ResourceNotFound
from neuromation.cli.formatters import ftable  # TODO: extract into a separate library

from . import ast
from .context import Context


COLORS = {
    JobStatus.PENDING: "yellow",
    JobStatus.RUNNING: "blue",
    JobStatus.SUCCEEDED: "green",
    JobStatus.FAILED: "red",
    JobStatus.UNKNOWN: "yellow",
}


def format_job_status(status: JobStatus) -> str:
    return click.style(status.value, fg=COLORS.get(status, "reset"))


class InteractiveRunner:
    def __init__(self, flow: ast.InteractiveFlow) -> None:
        self._flow = flow
        self._ctx: Optional[Context] = None
        self._client: Optional[Client] = None

    async def post_init(self) -> None:
        self._ctx = await Context.create(self._flow)
        self._client = await Factory().get()

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()

    @property
    def ctx(self) -> Context:
        assert self._ctx is not None
        return self._ctx

    @property
    def client(self) -> Client:
        assert self._client is not None
        return self._client

    async def resolve_job_by_name(self, name: str) -> str:
        owner = self.client.username
        async for job in self.client.jobs.list(
            name=name, owners={owner}, reverse=True, limit=1
        ):
            return job.id
        raise ResourceNotFound

    async def ps(self) -> None:
        """Return statuses for all jobs from the flow"""
        rows: List[List[str]] = []
        rows.append([click.style("JOB", bold=True), click.style("STATUS", bold=True)])
        for job_id in sorted(self._flow.jobs):
            job_ctx = await self.ctx.with_job(job_id)
            job = job_ctx.job
            assert job.name
            try:
                raw_id = await self.resolve_job_by_name(job.name)
                descr = await self.client.jobs.status(raw_id)
                rows.append([job_id, format_job_status(descr.status)])
            except ResourceNotFound:
                rows.append([job_id, format_job_status(JobStatus.UNKNOWN)])
            for line in ftable.table(rows):
                click.echo(line)

    async def run(self, job_id: str) -> None:
        """Run a named job"""
        job_ctx = await self.ctx.with_job(job_id)
        job = job_ctx.job
        args = []
        if job.title:
            args.append(f"--description={job.title}")
        assert job.name
        args.append(f"--name={job.name}")
        if job.preset is not None:
            args.append(f"--preset={job.preset}")
        if job.http_port is not None:
            args.append(f"--http-port={job.http_port}")
        if job.http_auth is not None:
            if job.http_auth:
                args.append(f"--http-auth")
            else:
                args.append(f"--no-http-auth")
        if job.entrypoint:
            args.append(f"--entrypoint={job.entrypoint}")
        if job.workdir is not None:
            raise NotImplementedError("workdir is not supported")
        for k, v in job.env.items():
            args.append(f"--env={k}={v}")
        for v in job.volumes:
            args.append(f"--volume={v}")
        for t in job.tags:
            args.append(f"--tag={t}")
        if job.life_span is not None:
            args.append(f"--file-spen={job.life_span}")
        if job.browse:
            args.append(f"--browse")
        if job.detach:
            args.append(f"--detach")

        proc = await asyncio.create_subprocess_exec(
            "neuro", "run", *args, job.image, job.cmd
        )
        try:
            retcode = await proc.wait()
            if retcode:
                raise SystemExit(retcode)
        finally:
            proc.kill()
            await proc.wait()

    async def logs(self, job_id: str) -> AsyncIterator[str]:
        """Return job logs"""

    async def kill(self, job_id: str) -> None:
        """Kill named job"""
