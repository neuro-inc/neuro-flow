# Getting started

`apolo-flow` is a tool that simplifies daily jobs on the Apolo platform.

Apolo Flow provides users the ability to create YAML files that configure routine things, for example, starting a Jupiter Notebook on the platform, starting a training pipeline, opening a file browser for remote storage, etc.

The tool builds required Docker images and starts all necessary Apolo jobs under the hood, while the user doesn't have to type all required `apolo` options and manually manage the pipeline scenarios.

## Installation

The tool is hosted on PyPI and can be installed by `pip` as a regular Python project:

```bash
$ pip install apolo-flow
```

Use the `--upgrade` option to upgrading Apolo Flow to the latest version:

```bash
$ pip install --upgrade apolo-flow
```

