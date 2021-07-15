# Project configuration syntax

By default, the project name is generated automatically based on the name of the project folder \(a folder that contains a `.neuro` subfolder for configuration YAML files\).

Name autogeneration will only work if the folder's name starts with a letter or an underscore symbol \(`_`\) and contains only letters, digits, or underscores. `ALL_CAPS` names are not supported.

To override this, you can put the `project.yml`\(or `project.yaml`\) file into the `.neuro` configuration folder.

## id

Project `id` available as a `${{ project.id }}` or `${{ flow.project_id }}` context.

## owner

Optional owner name available as a `${{ project.owner }}` context. Shared projects require `owner` or `role`.

## role

Optional project role name available as a `${{ project.role }}` context. By default the `role` is `{owner}/projects/{id}` if `owner` is defined. Shared projects require `owner` or `role`.

See also:

* [live contexts: `flow`](live-contexts.md#project-context)
* [batch contexts: `flow`](batch-contexts.md#project-context)

