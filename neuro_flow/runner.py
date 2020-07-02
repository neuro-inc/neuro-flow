from typing import AsyncIterator, Dict, Optional

from neuromation.api import Client, Factory, JobDescription, ResourceNotFound

from . import ast, context


class InteractiveRunner:
    def __init__(self, flow: ast.InteractiveFlow) -> None:
        self._flow = flow
        self._ctx = context.Context.create(self._flow)
        self._client: Optional[Client] = None

    async def post_init(self) -> None:
        self._client = await Factory().get()

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()

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

    async def ps(self) -> Dict[str, Optional[JobDescription]]:
        """Return statuses for all jobs from the flow"""
        ret: Dict[str, Optional[JobDescription]] = {}
        for job_id in self._flow.jobs:
            job_ctx = self._ctx.with_job(job_id)
            job = job_ctx.job
            name = job.name
            try:
                raw_id = await self.resolve_job_by_name(name)
                ret[job_id] = await self.client.jobs.status(raw_id)
            except ResourceNotFound:
                ret[job_id] = None
        return ret

    async def start(self, job_id: str) -> str:
        """Start a named job, return job id"""
        # job_ctx = self._ctx.with_job(job_id)
        # job = job_ctx.job
        # descr = await self.client.jobs.run()
        # job = self._get_job_ast(job_id)

    async def run(self, job_id: str) -> str:
        """Start a named job, wait for the job finish.

        Return the job id.
        """

    async def logs(self, job_id: str) -> AsyncIterator[str]:
        """Return job logs"""

    async def kill(self, job_id: str) -> None:
        """Kill named job"""
