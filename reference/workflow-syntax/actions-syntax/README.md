# Actions syntax

## Action file

Apolo Flow supports two sources of action files: local filesystem and Github repository.

For filesystem actions, you can place a config file in any location inside the flow's workspace. No special name is required.

For actions stored on Github, you should name the config file either `config.yml` or `config.yaml` and place it in the repository's root. To make your action usable, there should be a tagged commit inside the repository.

The following YAML attributes are supported:

## `kind`

**Required** The action's kind defines its behavior. Different kinds have some additional attributes. Here are the available kinds of actions:

* [`live`](./#kind-live-actions) actions define a single jobs inside a _live_ workflow.
* [`batch`](./#kind-batch-actions) actions define sets of tasks that can be used as singles inside a _batch_ workflow.
* [`stateful`](./#kind-stateful-actions) actions help with utilizing resources that require cleanup in _batch_ workflows.
* [`local`](./#kind-local-actions) actions allow executing a command on the user's machine before running a _batch_ workflow.

**Expression contexts:** This attribute only allows expressions that don't access contexts.

## `name`

The action's name.

**Expression contexts:** This attribute only allows expressions that don't access contexts.

## `author`

The action's author.

**Expression contexts:** This attribute only allows expressions that don't access contexts.

## `descr`

A description of the action.

**Expression contexts:** This attribute only allows expressions that don't access contexts.

## `inputs`

A mapping of key-value pairs that can be passed to the action. Each key can also have an optional default value and description.

The input can be specified in a _short_ and _long_ form.

The short form is compact, but only allows to specify the input name and its default value:

```yaml
inputs:
  name1: default1
  name2: ~   # None by default
  name3: ""  # Empty string by default
```

The long form allows to also specify the input's description. This can be useful for documenting the usage of the action and generating more detailed error messages.

```yaml
inputs:
  name1:
    default: default1
    descr: The name1 description
  name2:
    default: ~
    descr: The name2 description
  name3:
    default: ""
    descr: The name3 description
```

The inputs can be used in expressions for calculating all other action attributes.

**Expression contexts:** This attribute only allows expressions that don't access contexts.

## `live` actions

Actions with single jobs that can be integrated into a _live_ workflow.

These actions have the following additional attributes:

### `job`

**Required** A job that will run when the action is called. Attributes are the same as for a [`job`](../live-workflow-syntax/#attributes-for-jobs) in a _live_ workflow.�

{% hint style="warning" %}
Even though attributes are the same as in [_live_ workflows](../live-workflow-syntax/), the available expression contexts are different: actions have no access to `defauls`, `volumes`, and `images` of the main workflow.
{% endhint %}

**Expression contexts:** action job defenitions can only access the [`inputs` context](live-actions-contexts.md#inputs-context).

## `batch` actions

Actions with sets of tasks that can be integrated into a _batch_ workflow as a single task.

These have the following additional attributes:

### `outputs`

A mapping of key-value pairs that the action exposes. Tasks in the workflow that contain action calls will be able to access them through the [`needs` context](../batch-workflow-syntax/batch-contexts.md#needs-context).

If this attribute is missing, the action will not expose any outputs and the action call will always be successful.

### `outputs.<output-name>`

The key `output-name` is a string and its value is a map that defines a single output. You must replace `<output-name>` with a string that is unique to the `outputs` object.

### `outputs.<output-name>.value`

**Required.** An expression that calculates the value of an output. Can only access outputs of tasks that are specified in [`outputs.needs`](./#outputs-needs).

**Example:**

```yaml
outputs:
  needs: [last_task]
  name: 
    value: ${{ needs.last_task.name }}
```

**Expression contexts:** [`inputs` context](live-actions-contexts.md#inputs-context), [`needs` context](../batch-workflow-syntax/batch-contexts.md#needs-context) with tasks specified in [`outputs.needs`](./#outputs-needs).

### `outputs.<output-name>.descr`

Description of an output. It can be useful for documenting actions.

**Example:**

```yaml
outputs:
  name: 
    descr: The output description
```

**Expression contexts:** This attribute only allows expressions that don't access contexts.

### `cache`

A mapping that defines how the outputs of this action's tasks are cached. It can be overridden by [`tasks.cache`](../batch-workflow-syntax/#tasks-cache)

### `cache.strategy`

The default strategy to use for caching. Available options are:

* `"none"` Don't use caching at all.
* `"inherit"` Inherit the value from the _batch_ workflow that uses this action.
* `"default"` The basic caching algorithm that reuses cached outputs in case the task definition and all [expression contexts](../expression-syntax.md#contexts) available in task expressions are the same.

Default: `"default"`

**Example:**

```yaml
cache:
    strategy: "default"
```

**Expression contexts:** [`inputs` context](live-actions-contexts.md#inputs-context), [`strategy` context](../batch-workflow-syntax/batch-contexts.md#strategy-context) containing main flow settings.

### `cache.life_span`

The default cache invalidation duration.

This attribute can accept the following values:

* A `float` number representing an amount of seconds
* A string in the following format: `1d6h15m45s` (1 day, 6 hours, 15 minutes, 45 seconds).

Default: `14d` (two weeks)

{% hint style="info" %}
If you decrease this value and re-run the workflow, `apolo-flow` will ignore all cache entries that were added longer ago than the new `cache.life_span` value specifies.
{% endhint %}

**Example:**

```yaml
cache:
  life_span: 31d # Cache is valid for one month
```

**Expression contexts:** [`inputs` context](live-actions-contexts.md#inputs-context), [`strategy` context](../batch-workflow-syntax/batch-contexts.md#strategy-context) containing main flow settings.

### `tasks`

A list of tasks to run when the action is called. All attributes are the same as in [`tasks`](../batch-workflow-syntax/#tasks) in a _batch_ workflow.�

**Expression contexts:** [`inputs` context](live-actions-contexts.md#inputs-context) , [`strategy` context](../batch-workflow-syntax/batch-contexts.md#strategy-context) are available for all attributes, [`matrix` context](../batch-workflow-syntax/batch-contexts.md#matrix-context), [`needs` context](../batch-workflow-syntax/batch-contexts.md#needs-context) are available for same attributes as in _batch_ workflow.

## `stateful` actions

A stateful action defines two tasks:

* A [main](./#main) task to initialize some resource and pass it to the calling side
* An optional [post](./#post) task that's executed after the main workflow is completed and can be used to properly deinitalize it.

The [main](./#main) and [post](./#post) tasks can only communicate over the [`state` context](live-actions-contexts.md#state-context).

It has the following additional attributes:

### `outputs`

A mapping of key-value pairs that the action exposes. This only serves documentation purposes in `stateful` actions. The real outputs are generated by the `main` task.

### `outputs.<output-name>`

The key `output-name` is a string and its value is a mapping that contains the output's description. You must replace `<output-name>` with a string that is unique to the `outputs` object.

### `outputs.<output-name>.descr`

The output's description.

**Example:**

```yaml
outputs:
  resource_id: 
    descr: The identifier of the created resource
```

**Expression contexts:** This attribute only allows expressions that don't access contexts.

### `cache`

A mapping that defines how the outputs of the `main` and `post` tasks are cached.

### `cache.strategy`

The strategy to use for caching. Available options are:

* `"none"` Don't use caching at all.
* `"inherit"` Inherit the value from the _batch_ workflow that uses this action.
* `"default"` The basic caching algorithm that reuses cached outputs in case the task definition and all [expression contexts](../expression-syntax.md#contexts) available in task expressions are the same.

Default: `"default"`

**Example:**

```yaml
cache:
    strategy: "default"
```

**Expression contexts:** [`inputs` context](live-actions-contexts.md#inputs-context).

### `cache.life_span`

The cache invalidation duration.

This attribute can accept one of the following values:

* A `float` number representing an amount of seconds
* A string in the following format: `1d6h15m45s` (1 day, 6 hours, 15 minutes, 45 seconds).

Default: `14d` (two weeks)

{% hint style="info" %}
If you decrease this value and re-run the flow, `apolo-flow` will ignore all cache entries that were added longer ago than the new `cache.life_span` value specifies.
{% endhint %}

**Example:**

```yaml
cache:
  life_span: 31d # Cache is valid for one month
```

**Expression contexts:** [`inputs` context](live-actions-contexts.md#inputs-context).

### `main`

**Required** A mapping that defines the main task that is executed when the action is called. The action call is successful if this task is successful and will be failed if this task fails. Outputs of this task are passed to the main workflow as action call outputs.

This mapping only supports the subset of [`tasks`](../batch-workflow-syntax/#tasks) attributes from _batch_ workflows. The unsupported attributes are: `id`, `needs`, `strategy`, `enable`, `cache`.

**Expression contexts:** [`inputs` context](live-actions-contexts.md#inputs-context).

### `post`

A mapping that defines a post task that is executed after the main workflow is completed. If the main workflow uses more than one `stateful` action, the post tasks will run in reversed order: the first post task corresponds to the last main task.

This mapping only supports the subset of [`tasks`](../batch-workflow-syntax/#tasks) attributes from _batch_ workflows. The unsupported attributes are: `id`, `needs`, `strategy`, `enable`, `cache`.

**Expression contexts:** [`state` context](live-actions-contexts.md#state-context).

### `post_if`

The flag to conditionally prevent a post task from running unless a condition is met. To learn more about writing conditions, refer to [expression syntax](../expression-syntax.md). Default: `${{ always() }}`

**Example:**

```yaml
post_if: ${{ state.created }} # Run post only if the resource was created
```

**Expression contexts:** [`state` context](live-actions-contexts.md#state-context).

## `local` actions

Actions that define `cmd` to be executed on the user's machine before running a _batch_ workflow. Calls to actions of this kind precede all other tasks and action calls in the main workflow.

It has the following additional attributes:

### `outputs`

A mapping of key-value pairs that the action exposes. This only serves documentation purposes in `local` actions. The real outputs are generated by `cmd`.

### `outputs.<output-name>`

The key `output-name` is a string, and its value is a mapping that contains the output's description. You must replace `<output-name>` with a string that is unique to the `outputs` object.

### `outputs.<output-name>.descr`

The output's description.

**Example:**

```yaml
outputs:
  exit_code: 
    descr: The exit code of the shell program
```

**Expression contexts:** This attribute only allows expressions that don't access contexts.

### `cmd`

A command line code to execute locally. The shell type and the available commands depend on the user's system configuration, but you can safely assume that the low-level `apolo` commands are available.

**Example:**

```yaml
cmd:
  apolo cp -r ${{ inputs.from }} ${{ inputs.to }} # Copy files to storage
```

**Expression contexts:** [`inputs` context](live-actions-contexts.md#inputs-context).
