# Live contexts

YAML file that describes the [Live workflow](live-workflow-syntax.md#live-workflow) can use expressions for calculating YAML attribute values.

The following contexts are available:

## Live Contexts

| Context name | Description |
| :--- | :--- |
| env | Contains environment variables set in a workflow or job. For more information, see [`env` context](https://docs.github.com/en/free-pro-team@latest/actions/reference/context-and-expression-syntax-for-github-actions#env-context) . |
| flow | Information about the main workflow settings, defaults, etc. See &lt;link&gt; for details |
| images | Contains a mapping of images on the Neu.ro registry. |
| multi | Multi-job context. |
| params | A mapping of workflow-global parameters \(see also &lt;params&gt; section in YAML\). |
| tags | A set of job tags set in a workflow or job |
| volumes | Contains a mapping of volumes and secret files. |

### `env` context

The `env` context contains environment variables that have been set in a workflow or job. For more information about setting environment variables in your workflow, see "[Live workflow syntax](live-workflow-syntax.md#live-workflow)."

The `env` context syntax allows you to use the value of an environment variable in your workflow file. If you want to use the value of an environment variable inside a job, use the operating system's normal method for reading environment variables.

You can only use the `env` context in the value of the `with` and `name` keys, or in a step's `if` conditional. For more information on the step syntax, see "[Workflow syntax for GitHub Actions](https://docs.github.com/en/free-pro-team@latest/actions/automating-your-workflow-with-github-actions/workflow-syntax-for-github-actions#jobsjob_idsteps)."

| Property name | Type | Description |
| :--- | :--- | :--- |
| `env` | `object` | This context changes for each job. You can access this context from any  job. |
| `env.<env name>` | `string` | The value of a specific environment variable. |

### `flow` context

The `flow`context contains information about the workflow: it's id, title, etc.

| Property name | Type | Description |
| :--- | :--- | :--- |
| flow\_id | str | The workflow id. It is auto-calculated from the workflow's YAML filename with a dropped suffix. You can override the `flow_id` by providing &lt;link&gt; attribute in YAML file. |
| project\_id | str |  |
| workspace | LocalPath |  |
| title | str |  |

