# Live workflow syntax

## _Live_ workflow

The live workflow is always located at `.neuro/live.yml` file under the project root;`.neuro/live.yaml` is also supported if you prefer a longer suffix for some reason. The following YAML attributes are supported:

## `kind`

**Required** The workflow _kind_, __must be `live` for _live_ workflows.

## `id`

Identifier of the workflow. By default, the `id` is `live`.

## `title`

Workflow title

## `defaults`

A map of default settings that will apply to all jobs in the workflow. You can override these global default settings for a particular job.

### `defaults.env`

A mapping of environment variables that are available to all jobs in the workflow. You can also set environment variables that are only available to a job or step. For more information, see [`jobs.<job-id>.env`](live-workflow-syntax.md#jobs-job-id-env).

When more than one environment variable is defined with the same name, `neuro-flow` uses the most specific environment variable. For example, an environment variable defined in a step will override job and workflow variables with the same name, while the step executes. A variable defined for a job will override a workflow variable with the same name, while the job executes.

**Example**:

```yaml
env:
  SERVER: production
```

### `defaults.life_span`

The default life span for jobs run by the workflow.  It can be overridden  by [`jobs.<job-id>.life_span`](live-workflow-syntax.md#jobs-less-than-job-id-greater-than-life_span).  In not set, the default job's life span is 1 day.  The value is a float number of seconds \(`3600` for an hour\) or expression in the following format: `1d6h15m`  \(1 day 6 hours, 15 minutes\). Use `0` for disabling the life-span feature \(it can be dangerous, a forgotten job consumes the cluster resources\).

{% hint style="warning" %}
life spans shorter than _1 minute_ are forbidden.
{% endhint %}

**Example:**

```yaml
defaults:
  life_span: 14d
```

### `defaults.preset`

The default preset name used by all jobs if not overridden by [`jobs.<job-id>.preset`](live-workflow-syntax.md#jobs-less-than-job-id-greater-than-preset).

**Example:**

```yaml
defaults:
  preset: gpu-small
```

### `defaults.tags`

A list of tags that add added to every job created by the workflow. A particular job definition can extend this global list by [`jobs.<job-id>.tags`](live-workflow-syntax.md#jobs-less-than-job-id-greater-than-tags).

**Example with a tag per line:**

```yaml
defaults:
  tags:
  - tag-a
  - tag-b
```

**Example with the compact one-line list:**

```yaml
defaults:
  tags: [tag-a, tag-b]
```

## `images`

Workflow images

## `volumes`

Workflow volumes

## `jobs`

A _live_ workflow can run jobs by their identifiers using `neuro-flow run <job-id>` command. Each job runs remotely on the Neu.ro platform.

### `jobs.<job-id>.env` <a id="jobs-job-id-env"></a>

### `jobs.<job-id>.life_span`

### `jobs.<job-id>.preset`

### `jobs.<job-id>.tags`



