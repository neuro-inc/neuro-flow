`${{ project.project_name }}` now also configures `volume`'s remote path and `image` reference if the project name was not set.

If you do not have `project_name` set in `project.yaml`, the volume paths are assumed within your current project configured in CLI.
However, if you set `project_name`, this project will be assumed while managing jobs, bakes, volumes, building images etc. within this flow.
