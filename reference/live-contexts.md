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

