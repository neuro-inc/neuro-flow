# Project configuration syntax

By default, the project name is generated automatically based on the name of the project folder \(a folder that contains a `.neuro` subfolder for configuration YAML files\).

However, if the folder's name contains unsupported characters, this will not work. The following character's are _not_ supported: 
* A digit in the beginning of the name 
* Non-ASCII symbols 
* The dash \(`-`\) symbol

To override this, you can put the `project.yml`\(or `project.yaml`\) file into the `.neuro` configuration folder.

This file only contains the `id` attribute by default, but the format can be expanded later.

### id

Project `id` available as a `${{ flow.project_id }}` context.

See also: 
* [live contexts: `flow`](live-contexts.md#flow-context)
* [batch contexts: `flow`](batch-contexts.md#flow-context)
