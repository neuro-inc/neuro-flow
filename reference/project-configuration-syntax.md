# Project configuration syntax

By default, the project name is auto-calculated from the name of the project folder \(a folder with `.neuro` subfolder for configuration YAML files inside\).

It works in 99% cases but sometimes the folder name contains characters that are not allowed: the name started with a digit, contains non-ASCII leters, a dash \(`-`\) symbol etc.

In this case, you can put `project.yml` file into `.neuro` configuration folder to override the name \(`project.yaml` is also supported\).

The file contains the only `id` attribute but the format can be expanded later.

### id

Project `id` that is available as `${{ flow.project_id }}` context.

See also [live contexts: `flow`](live-contexts.md#flow-context)and batch contexts: `flow`.

