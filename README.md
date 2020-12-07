# Getting started

`neuro-flow` is a tool that simplifies daily jobs with the Neu.ro platform.

The main idea is: a user creates YAML files that configure routine things, e.g. starting a Jupiter Notebook in the platform, starting a Training Pipeline, opening a file browser for Remote Storage, etc., etc.

The tool builds required Docker images and starts Neu.ro job under the hood but avoids a user from typing all required `neuro` options and managing the pipeline scenarios manually.

## Installation

The tool is hosted on PyPI and can be installed by `pip` as a regular Python project:

```bash
$ pip install neuro-flow
```

Use `--upgrade` option for upgrading to the latest version:

```bash
$ pip install --upgrade neuro-flow
```

