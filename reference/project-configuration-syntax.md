# Project configuration syntax

By default, the project name is generated automatically based on the name of the project folder \(a folder that contains a `.neuro` subfolder for configuration YAML files\).

Name autogeneration will only work if the folder's name starts with a letter or an underscore symbol \(`_`\) and contains only letters, digits, or underscores. `ALL_CAPS` names are not supported.

To override this, you can put the `project.yml`\(or `project.yaml`\) file into the `.neuro` configuration folder.

## id

Project `id` available as a `${{ project.id }}` or `${{ flow.project_id }}` context.
Default value - folder name, where '.neuro' folder is located.

## owner

Optional owner name available as a `${{ project.owner }}` context. Shared projects require `owner` or `role`.

## role

Optional project role name available as a `${{ project.role }}` context. By default the `role` is `{owner}/projects/{id}` if `owner` is defined. Shared projects require `owner` or `role`.
This role name might be used to share the project with other platform `<user>` via `neuro acl grant <role> <user>`

## Project-wide configuration

You can define jobs and workflows globally by specifying the desired project-wide behavior in the following sections of the `project.yml` file: 

* defaults
* images
* volumes
* mixins

You can find detailed description of how to use the `defaults`, `images`, and `volumes` sections in the corresponding parts of the [live workflows syntax](live-workflow-syntax.md) and [batch workflow syntax](batch-workflow-syntax.md) documentation.

You can [learn more about mixins here](mixins.md). 

All settings specified in `project.yml` will be applied by default to all job and workflows of this project.

## See also

* [live contexts: `flow`](live-contexts.md#project-context) 
* [batch contexts: `flow`](batch-contexts.md#project-context)