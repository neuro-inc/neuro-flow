# Actions syntax

## Action file

Neuro Flow supports two sources of action files: local filesystem and Github repository.

For filesystem action, you can place a config file in any location inside the project workspace. No special name is required.

For action stored on Github, you should name config file either `config.yml` or `config.yaml` and place it in the repository root. To make your action usable, there should be a tagged commit inside the repository.  
  
The following YAML attributes are supported:

## `kind`

**Required** The action kind defines its behavior. Different kinds have some additional attributes.  It can be one of:

* [`live`](actions-syntax.md#kind-live-actions) action that defines a single job the _live_ workflow.
* [`batch`](actions-syntax.md#kind-batch-actions) action that defines a set of tasks that can be used as a single in the _batch_ workflow. 
* [`stateful`](actions-syntax.md#kind-stateful-actions) action for utilizing resources that require cleanup in the _batch_ workflow.
* [`local`](actions-syntax.md#kind-local-actions) action that allows executing a command on the user's machine before running _batch_ workflow. 

**Expression contexts:** This attribute only allows expressions that do not access contexts. 

## `name`

The action's name.

**Expression contexts:** This attribute only allows expressions that do not access contexts.

## `author`

The action's author.

**Expression contexts:** This attribute only allows expressions that do not access contexts.

## `descr`

A description of the action.

**Expression contexts:** This attribute only allows expressions that do not access contexts.

## `inputs`

A mapping of key-value pairs that can be passed to the action. Each key can have an optional default value and description specified.

The input can be specified in a _short_ and _long_ form.

The short form is compact but allows to specify the input name and default value only:

```yaml
inputs:
  name1: default1
  name2: ~   # None by default
  name3: ""  # Empty string by default
```

The long form allows to point the input description also \(can be useful for documenting usage of the action and generation a more verbose error message if needed\):

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

Both examples above are equal but the last has inputs descriptions.  
  
The inputs can be used in expressions for calculating all other action attributes.

**Expression contexts:** This attribute only allows expressions that do not access contexts.

## Kind `live` actions

Action with a single job that can be integrated into a _live_ workflow.

It has the following additional attributes:

### `job`

**Required** A job to run when action is called. All attributes are the same as in a [`job`](live-workflow-syntax.md#attributes-for-jobs) in a _live_ workflow. 

{% hint style="warning" %}
Even though attributes are the same as in [_live_ workflow](live-workflow-syntax.md), the expressions contexts available are different: action has no access to `defauls`, `volumes` and `images` of the main workflow.
{% endhint %}

**Expression contexts:** action job defenition can only access [`inputs` context](live-actions-contexts.md#inputs-context).

## Kind `batch` actions

Action with a set of tasks that can be integrated into a _batch_ workflow as a single task.

It has the following additional attributes:

### `outputs`

A mapping of key-value pairs that the action exposes. Tasks in the workflow that contains actions call will be able to access them through &lt;NeedsContext&gt;.

If this attribute is missing, the action does not expose any outputs and the action call will be always successful.

### `outputs.needs`

**Required.** The array of strings identifying all tasks from this action's [`tasks`](actions-syntax.md#tasks) list that must complete successfully to consider action run is successful. If a task fails the action call is also considered failed. If a task was skipped due to [`enable`](batch-workflow-syntax.md#tasks-enable) the action call is also considered skipped.  
This attribute defines what tasks outputs will be available in &lt;NeedsContext&gt; in [`outputs.<output-name>.value`](actions-syntax.md#outputs-less-than-output-name-greater-than-value).

{% hint style="info" %}
This attribute cannot have all action's tasks as a default: in such case, the action can be suddenly considered skipped because of an optional task with [`enable`](batch-workflow-syntax.md#tasks-enable) attribute. 
{% endhint %}

**Example:**

```yaml
outputs:
  needs: [task_2, task_3]
tasks:
  - id: task_1
  - id: task_2
  - id: task_3
```

**Expression contexts:** This attribute only allows expressions that do not access contexts.

### `outputs.<output-name>`

The key `output-name` is a string and its value is a map that defines single output. You must replace `<output-name>` with a string that is unique to the `outputs` object. 

### `outputs.<output-name>.value`

**Required.** An expression to calculate output value. Can only access outputs of tasks that are specified in [`outputs.needs`](actions-syntax.md#outputs-needs).

**Example:**

```yaml
outputs:
  needs: [last_task]
  name: 
    value: ${{ needs.last_task.name }}
```

**Expression contexts:**  [`inputs` context](live-actions-contexts.md#inputs-context),  [`needs` context](batch-contexts.md#needs-context) with tasks specified in [`outputs.needs`](actions-syntax.md#outputs-needs).

### `outputs.<output-name>.descr`

The output description. It can be useful for documenting the action.  

**Example:**

```yaml
outputs:
  name: 
    descr: The output description
```

**Expression contexts:** This attribute only allows expressions that do not access contexts.

### `cache`

A mapping that defines how caching of outputs of this action tasks works. It can be overridden by [`tasks.cache`](batch-workflow-syntax.md#tasks-cache)

### `cache.strategy`

The default strategy to use for caching. Available options are:

* `"none"` Do not use caching at all.
* `"inherit"` Use the value from the _batch_ workflow that uses this action.
* `"default"` The basic caching algorithm, that reuses cached outputs in case task definition and all [expression contexts](expression-syntax.md#contexts) available in task expressions are the same.

Default: `"default"`

**Example:**

```yaml
cache:
    strategy: "default"
```

**Expression contexts:**  [`inputs` context](live-actions-contexts.md#inputs-context), [`strategy` context](batch-contexts.md#strategy-context) containing main flow settings.

### `cache.life_span`

The default cache invalidation duration. The attribute accepts either a `float` number of seconds or a string in`1d6h15m45s` \(1 day 6 hours, 15 minutes, 45 seconds\). Default: `14d` \(two weeks\)

{% hint style="info" %}
If you decrease this value and re-run flow, `neuro-flow` will ignore cache entries that were added more than the new value of`cache.life_span` seconds ago.
{% endhint %}

**Example:**

```yaml
cache:
  life_span: 31d # Cache is valid for one month
```

**Expression contexts:**  [`inputs` context](live-actions-contexts.md#inputs-context), [`strategy` context](batch-contexts.md#strategy-context) containing main flow settings.

### `tasks`

A list of tasks to run when action is called. All attributes are the same as in a [`tasks`](batch-workflow-syntax.md#tasks) in a _batch_ workflow. 

**Expression contexts:**  [`inputs` context](live-actions-contexts.md#inputs-context) , [`strategy` context](batch-contexts.md#strategy-context) are available for all attributes, [`matrix` context](batch-contexts.md#matrix-context),  [`needs` context](batch-contexts.md#needs-context) are available for same attributes as in _batch_ workflow. 

## Kind `stateful` actions

Action that defines two tasks - [main](actions-syntax.md#main) one to initialize some resource and pass it to the calling side and [post](actions-syntax.md#post) one that is executed after the main workflow is completed and can be used to properly deinitalize it. The [post](actions-syntax.md#post) task is optional.

The [main](actions-syntax.md#main) and [post](actions-syntax.md#post) tasks can only communicate over the state context. &lt;link to expression syntax docs&gt;.

It has the following additional attributes:

### `outputs`

A mapping of key-value pairs that the action exposes. In `statefull` actions it serves only documentation purposes. The real outputs are generated by `main` task.

### `outputs.<output-name>`

The key `output-name` is a string and its value is a mapping that contains output description. You must replace `<output-name>` with a string that is unique to the `outputs` object. 

### `outputs.<output-name>.descr`

The output description.

**Example:**

```yaml
outputs:
  resource_id: 
    descr: The identifier of the created resource 
```

**Expression contexts:** This attribute only allows expressions that do not access contexts.

### `cache`

A mapping that defines how caching of outputs of the `main` and `post` tasks works. 

### `cache.strategy`

The strategy to use for caching. Available options are:

* `"none"` Do not use caching at all.
* `"inherit"` Use the value from the _batch_ workflow that uses this action.
* `"default"` The basic caching algorithm, that reuses cached outputs in case task definition and all [expression contexts](expression-syntax.md#contexts) available in task expressions are the same.

Default: `"default"`

**Example:**

```yaml
cache:
    strategy: "default"
```

**Expression contexts:**  [`inputs` context](live-actions-contexts.md#inputs-context).

### `cache.life_span`

The cache invalidation duration. The attribute accepts either a `float` number of seconds or a string in`1d6h15m45s` \(1 day 6 hours, 15 minutes, 45 seconds\). Default: `14d` \(two weeks\)

{% hint style="info" %}
If you decrease this value and re-run flow, `neuro-flow` will ignore cache entries that were added more than the new value of`cache.life_span` seconds ago.
{% endhint %}

**Example:**

```yaml
cache:
  life_span: 31d # Cache is valid for one month
```

**Expression contexts:**  [`inputs` context](live-actions-contexts.md#inputs-context).

### `main`

**Required** A mapping that defines the main task that is executed when action is called. The action call is successful if this task is successful and it is failed if this task fails. Outputs of this task are passed to the main workflow as action call outputs.

This mapping supports only the subset of [`tasks`](batch-workflow-syntax.md#tasks) attributes from _batch_ workflows. The unsupported attributes are: `id`, `needs`, `strategy`, `enable`, `cache`.

**Expression contexts:**  [`inputs` context](live-actions-contexts.md#inputs-context).

### `post`

A mapping that defines post task that is executed after the main workflow completes. If the main workflow uses more than one `stateful` action, then post tasks run in reversed order: the first post task corresponds to the last main task.

This mapping supports only the subset of [`tasks`](batch-workflow-syntax.md#tasks) attributes from _batch_ workflows. The unsupported attributes are: `id`, `needs`, `strategy`, `enable`, `cache`.

**Expression contexts:**  [`state` context](live-actions-contexts.md#state-context).

### `post_if`

The flag to conditionally prevent a post task from running unless a condition is met. To learn how to write conditions refer to [expression syntax](expression-syntax.md). Default: `${{ always() }}`

**Example:**

```yaml
post_if: ${{ state.created }} # Run post only if resource was created
```

**Expression contexts:**  [`state` context](live-actions-contexts.md#state-context).

## Kind `local` actions

Action that defines `cmd` to be executed on the user's machine before running a _batch_ workflow. Calls to actions of this kind precede all other tasks and actions calls in main workflow.

It has the following additional attributes:

### `outputs`

A mapping of key-value pairs that the action exposes. In `local` actions, it serves only documentation purposes. The real outputs are generated by `cmd`.

### `outputs.<output-name>`

The key `output-name` is a string and its value is a mapping that contains output description. You must replace `<output-name>` with a string that is unique to the `outputs` object. 

### `outputs.<output-name>.descr`

The output description.

**Example:**

```yaml
outputs:
  exit_code: 
    descr: The exit code of shell program  
```

**Expression contexts:** This attribute only allows expressions that do not access contexts. 

### `cmd`

A command-line code to execute locally. The shell type and what commands are available depends on the user's system configuration, but you can safely assume that `neuro` low-level command line is available.

**Example:**

```yaml
cmd:
  neuro cp -r ${{ inputs.from }} ${{ inputs.to }} # Copy files to storage
```

**Expression contexts:**  [`inputs` context](live-actions-contexts.md#inputs-context).

