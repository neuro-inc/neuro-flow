# Project configuration syntax

By default, the project name is generated automatically based on the name of the project folder \(a folder that contains a `.neuro` subfolder for configuration YAML files\).

Name autogeneration will only work if the folder's name starts with a letter or an underscore symbol \(`_`\) and contains only letters, digits, or underscores. `ALL_CAPS` names are not supported.

To override this, you can put the `project.yml`\(or `project.yaml`\) file into the `.neuro` configuration folder.

This file only contains the `id` attribute by default, but the format can be expanded later.

## id

Project `id` available as a `${{ flow.project_id }}` context.

See also:

* [live contexts: `flow`](live-contexts.md#flow-context)
* [batch contexts: `flow`](batch-contexts.md#flow-context)

