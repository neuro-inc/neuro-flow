# Workflows

A workflow is a configurable automated process made up of one or more job, task, or action call. You must create a YAML file to define your workflow configuration.

## Workflow _kinds_

There are two _kinds_ of workflows: _live_ and _batch_.

### _Live_ workflows

[_Live_](live-workflow-syntax.md#live-workflow) workflows are executed locally on the developer's machine. They contain a set of job definitions that spawn jobs in the Neu.ro cloud.

Here's an example of a typical job: 
1. Executing a Jupyter Notebook server in the cloud on a powerful node with a lot of memory and a high-performant GPU
2. Opening a browser with a Jupyter web client connected to this server

### _Batch_ workflows

[_Batch_](batch-workflow-syntax.md) workflows serve for orchestration of a set of remote tasks that depend on each other. _Batch_ workflows are executed by the main job that manages workflow graphs by spawning required jobs, waiting for their results, and starting dependent tasks when all of their requirements are satisfied.

