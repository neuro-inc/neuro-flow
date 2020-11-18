# Workflows

A workflow is a configurable automated process made up of one or more jobs, task, or action call. You must create a YAML file to define your workflow configuration.

## Workflow _kinds_

There are two _kinds_ of workflow: _live_ and _batch_.

The [_live_](live-workflow-syntax.md#live-workflow) workflow is executed locally on the developer's machine. It contains a set of job definitions that spawn jobs in the Neu.ro cloud.

The typical job is executing a Jupyter Notebook server in the cloud on a powerful node with a lot of memory and high-performant GPU and opening a browser with a Jupyter web-client connected to this server.

The [_batch_](batch-workflow-syntax.md) workflow is for the orchestration of a set of remote tasks that depend on each other. The _batch_ workflow is executed by the main job that manages the workflow's graph by spawning required jobs, waiting for their results, and starting dependent tasks when all pre-requirements are satisfied.
