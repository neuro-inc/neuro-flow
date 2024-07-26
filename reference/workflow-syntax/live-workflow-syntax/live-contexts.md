# Live contexts

This page describes the contexts a [live workflow](./#live-workflow) can use in expressions for calculating YAML attribute values.

## Live Contexts

| Context name | Description                                                                                                                          |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------ |
| `env`        | Contains environment variables set in a workflow or a job. For more information, see [`env` context](live-contexts.md#env-context) . |
| `flow`       | Information about the main workflow settings, defaults, etc. See [`flow` context](live-contexts.md#flow-context) for details.        |
| `project`    | Information about the project. See [`project` context](live-contexts.md#project-context) for details.                                |
| `images`     | Contains a mapping of images on the Apolo registry. See [`images` context](live-contexts.md#images-context) for details.            |
| `multi`      | Multi-job context. For more information, see [`multi` context](live-contexts.md#multi-context).                                      |
| `params`     | A mapping of global workflow parameters. For more information, see [`params` context](live-contexts.md#params-context).              |
| `tags`       | A set of job tags set in a workflow or a job. See [`tags` context](live-contexts.md#tags-context) for details.                       |
| `volumes`    | Contains a mapping of volume definitions. For more information, see [`volumes` context](live-contexts.md#volumes-context).           |
| `git`        | A mapping of the flow's workspace to a git repository. For more information, see [`git` context](live-contexts.md#git-context).      |

### `env` context

The `env` context contains environment variables that have been set in a workflow or a job. For more information about setting environment variables in your workflow, see "[Live workflow syntax](./#live-workflow)."

The `env` context syntax allows you to use the value of an environment variable in your workflow file. If you want to use the value of an environment variable inside a job, use your operating system's standard method for reading environment variables.

| Property name    | Type  | Description                                   |
| ---------------- | ----- | --------------------------------------------- |
| `env.<env-name>` | `str` | The value of a specific environment variable. |

### `flow` context

The `flow` context contains information about the workflow: its id, title, etc.

| Property name     | Type        | Description                                                                                                                                                                                                                                                         |
| ----------------- | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `flow.flow_id`    | `str`       | The workflow's ID. It's automatically generated based on the workflow's YAML filename with a dropped suffix (this will always `'live'` in live mode). You can override the property by setting the [`flow.id`](./#id) attribute.                                    |
| `flow.project_id` | `str`       | The project's ID. It is automatically generated based on the name of the flow folder. You can override it using [`project.id`](../project-configuration-syntax.md#id) attribute. Check [the project configuration](../project-configuration-syntax.md) for details. |
| `flow.workspace`  | `LocalPath` | A path to the workspace (the root folder of the flow).                                                                                                                                                                                                              |
| `flow.title`      | `str`       | The workflow title. Set the [`flow.title`](./#title) attribute to override the auto-generated value.                                                                                                                                                                |

### `project` context

The `project`context contains information about the project: its ID, owner, etc.

| Property name          | Type  | Description                                                                                                                                                                                                                                                                                                                  |
| ---------------------- | ----- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `project.id`           | `str` | The project's ID. It is automatically generated based on the name of the flow folder. You can override it using [`project.id`](../project-configuration-syntax.md#id) attribute. Check [the project configuration](../project-configuration-syntax.md) for details. This context property is an alias to `flow.project_id` . |
| `project.owner`        | `str` | The project's owner. See also: [the project configuration](../project-configuration-syntax.md#owner).                                                                                                                                                                                                                        |
| `project.project_name` | `str` | The platform project name. Set the [project.project\_name](../project-configuration-syntax.md#project\_name) attribute to override the auto-calculated value.                                                                                                                                                                |

### `images` context

Contains information about images defined in the [`images` section](./#images) of a _live_ workflow.

| Property name                            | Type                  | Description                                                                                                                                                                                                                                                                                                                                     |
| ---------------------------------------- | --------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `images.<image-id>.id`                   | `str`                 | The image definition identifier. For more information, see [`images.<image-id>`](./#images-less-than-image-id-greater-than) section.                                                                                                                                                                                                            |
| `images.<image-id>.ref`                  | `str`                 | The image reference. For more information, see [`images.<image-id>.ref`](./#images-less-than-image-id-greater-than-ref) attribute.                                                                                                                                                                                                              |
| `images.<image-id>.context`              | `LocalPath` or `None` | <p>The context directory used for building the image or <code>None</code> if the context is not set. The path is relative to the flow's root (<code>flow.workspace</code> property).</p><p>For more information, see <a href="./#images-less-than-image-id-greater-than-context"><code>images.&#x3C;image-id>.context</code> attribute</a>.</p> |
| `images.<image-id>.full_context_path`    | `LocalPath` or `None` | The absolute path, pointing to the `context` folder if set.                                                                                                                                                                                                                                                                                     |
| `images.<image-id>.dockerfile`           | `LocalPath`or `None`  | <p>A path to <code>Dockerfile</code> or <code>None</code> if not set.</p><p>For more information, see <a href="./#images-less-than-image-id-greater-than-dockerfile"><code>images.&#x3C;image-id>.dockerfile</code> attribute</a>.</p>                                                                                                          |
| `images.<image-id>.full_dockerfile_path` | `LocalPath` or `None` | Full version of the `dockerfile` attribute.                                                                                                                                                                                                                                                                                                     |
| `images.<image-id>.build_args`           | `list[str]`           | <p>A sequence of additional build arguments.</p><p>For more information, see <a href="./#images-less-than-image-id-greater-than-build_args"><code>images.&#x3C;image-id>.build_args</code> attribute</a>.</p>                                                                                                                                   |
| `images.<image-id>.env`                  | `dict[str, str]`      | <p>Environment variables passed to the image builder.</p><p>For more information, see <a href="./#images-less-than-image-id-greater-than-env"><code>images.&#x3C;image-id>.env</code> attribute</a>.</p>                                                                                                                                        |
| `images.<image-id>.volumes`              | `list[str]`           | <p>A sequence of volume definitions passed to the image builder.</p><p>For more information, see <a href="./#images-less-than-image-id-greater-than-volumes"><code>images.&#x3C;image-id>.volumes</code> attribute.</a></p>                                                                                                                     |

### `multi` context

The additional arguments passed to _multi-job_.

| Property name  | Type  | Description                                                                                                                                                                                                                                                                                                                                                                                                         |
| -------------- | ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `multi.args`   | `str` | <p>Additional command line arguments passed to <em>multi-job</em>.<br>The command line run defines the field as <code>apolo-flow run &#x3C;job-id> -- &#x3C;args></code>.</p><p><code>multi.args</code> is mainly used for passing args to command line parameters accepted by <em>multi-job</em>, see <a href="./#jobs-less-than-job-id-greater-than-cmd"><code>jobs.&#x3C;job-id>.cmd</code></a> for details.</p> |
| `multi.suffix` | `str` | _multi-job_ suffix added to [`jobs.<job-id>`](./#jobs-job-id-env).                                                                                                                                                                                                                                                                                                                                                  |

### `params` context

Parameter described in the [`jobs.<job-id>.params` attribute](./#jobs-less-than-job-id-greater-than-params) and available for substitution - for example, in [`jobs.<job-id>.cmd`](./#jobs-less-than-job-id-greater-than-cmd) calculation.

| Property name         | Type  | Description                        |
| --------------------- | ----- | ---------------------------------- |
| `params.<param-name>` | `str` | The value of a specific parameter. |

Supported parameter values: `project`, `flow`, `env`, `tags`, `volumes`, `images`.

### `tags` context

A set of job tags.

Tags are combined from system tags (`project:<project-id>`, `job:<job-id>`), flow default tags (see [`defaults.tags` attribute](./#defaults-tags)), and job-specific tags (see `jobs.<job-id>.tags` attribute).

| Property name | Type       | Description                                                                  |
| ------------- | ---------- | ---------------------------------------------------------------------------- |
| `tags`        | `set[str]` | This context changes for each job. You can access this context from any job. |

### `volumes` context

Contains information about volumes defined in the [`volumes` section ](./#volumes)of a _live_ workflow.

| Property name                         | Type                  | Description                                                                                                                                                                                                                                                                                                                                            |
| ------------------------------------- | --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `volumes.<volume-id>.id`              | `str`                 | The volume definition identifier. For more information, see [`volumes.<volume-id>` section](./#volumes-less-than-volume-id-greater-than).                                                                                                                                                                                                              |
| `volumes.<volume-id>.remote`          | `URL`                 | <p>Remote volume URI, e.g. <code>storage:path/to</code>.<br>For more information, see <a href="./#volumes-less-than-volume-id-greater-than-remote"><code>volumes.&#x3C;volume-id>.remote</code> attribute</a>.</p>                                                                                                                                     |
| `volumes.<volume-id>.mount`           | `RemotePath`          | <p>The path inside a job by which the volume should be mounted.</p><p>For more information, see <a href="./#volumes-less-than-volume-id-greater-than-mount"><code>volumes.&#x3C;volume-id>.mount</code> attribute</a>.</p>                                                                                                                             |
| `volumes.<volume-id>.read_only`       | `bool`                | <p><code>True</code> if the volume is mounted in read-only mode, <code>False</code> otherwise.</p><p>For more information, see <a href="./#volumes-less-than-volume-id-greater-than-read_only"><code>volumes.&#x3C;volume-id>.read_only</code> attribute</a>.</p>                                                                                      |
| `volumes.<volume-id>.local`           | `LocalPath`or `None`  | <p>A path in the workspace folder to synchronize with remote Apolo storage or <code>None</code> if not set.</p><p>For more information, see <a href="./#volumes-less-than-volume-id-greater-than-local"><code>volumes.&#x3C;volume-id>.local</code> attribute</a>.</p>                                                                                |
| `volumes.<volume-id>.full_local_path` | `LocalPath` or `None` | Full version of `local` property.                                                                                                                                                                                                                                                                                                                      |
| `volumes.<volume-id>.ref`             | `str`                 | <p>A volume reference that can be used as a <a href="./#jobs-less-than-job-id-greater-than-volumes"><code>jobs.&#x3C;job-id>.volumes</code> item</a>. The calculated value looks like <code>storage:path/to:/mnt/path:rw</code>.</p><p>The value is assembled from <code>remote</code>, <code>mount</code>, and <code>read_only</code> properties.</p> |
| `volumes.<volume-id>.ref_ro`          | `str`                 | Like `ref` but _read-only_ mode is enforced.                                                                                                                                                                                                                                                                                                           |
| `volumes.<volume-id>.ref_rw`          | `str`                 | Like `ref` but _read-write_ mode is enforced.                                                                                                                                                                                                                                                                                                          |

### `git` context

The `git` context contains a mapping of your flow's workspace to a git repository.

This context can only be used if the flow's workspace is inside some git repository.

| Property name | Type        | Description                                    |
| ------------- | ----------- | ---------------------------------------------- |
| `git.sha`     | `str`       | SHA of the current commit.                     |
| `git.branch`  | `str`       | Name of the current branch.                    |
| `git.tags`    | `list[str]` | List of tags that point to the current commit. |
