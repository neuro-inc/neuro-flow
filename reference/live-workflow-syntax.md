# Live workflow syntax

## _Live_ workflow

The live workflow is always located at `.neuro/live.yml` file under the project root;`.neuro/live.yaml` is also supported if you prefer a longer suffix for some reason. The following YAML attributes are supported:

## `kind`

**Required** The workflow _kind_, must be _`live`_ for _live_ workflows.

**Expression contexts:** This attribute cannot contain expressions.

## `id`

Identifier of the workflow. By default, the `id` is `live`.

**Expression contexts:** This attribute only allows expressions that do not access contexts. 

## `title`

Workflow title

**Expression contexts:** This attribute only allows expressions that do not access contexts.

## `defaults`

A map of default settings that will apply to all jobs in the workflow. You can override these global default settings for a particular job.

### `defaults.env`

A mapping of environment variables that are available to all jobs in the workflow. You can also set environment variables that are only available to a job. For more information, see [`jobs.<job-id>.env`](live-workflow-syntax.md#jobs-job-id-env-1).

When more than one environment variable is defined with the same name, `neuro-flow` uses the most specific environment variable. For example, an environment variable defined in a job will override the workflow default.

**Example**:

```yaml
env:
  SERVER: production
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context).

### `defaults.life_span`

The default life span for jo runs by the workflow. It can be overridden by [`jobs.<job-id>.life_span`](live-workflow-syntax.md#jobs-less-than-job-id-greater-than-life_span). If not set, the default job's life span is 1 day. The value is a float number of seconds \(`3600` for an hour\) or expression in the following format: `1d6h15m` \(1 day 6 hours, 15 minutes\). Use an arbitrary huge value \(e.g. `365d`\) for the life-span disabling emulation \(it can be dangerous, a forgotten job consumes the cluster resources\).

{% hint style="warning" %}
life span shorter than _1 minute_ is forbidden.
{% endhint %}

**Example:**

```yaml
defaults:
  life_span: 14d
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context).

### `defaults.preset`

The default preset name used by all jobs if not overridden by [`jobs.<job-id>.preset`](live-workflow-syntax.md#jobs-less-than-job-id-greater-than-preset). The system-wide default preset is used if both `defaults.preset` and `jobs.<job-id>.preset` are omitted.

**Example:**

```yaml
defaults:
  preset: gpu-small
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context).

### `defaults.schedule_timeout`

The default timeout for a job scheduling. See [`jobs.<job-id>.schedule_timeout`](live-workflow-syntax.md#jobs-less-than-job-id-greater-than-schedule_timeout) for more information.

The attribute accepts either a `float` number of seconds or a string in`1d6h15m45s` \(1 day 6 hours, 15 minutes, 45 seconds\).

The cluster-wide timeout is used if both `default.schedule_timeout` and `jobs.<job-id>.schedule_timeout` are omitted.

**Example:**

```yaml
defaults:
  schedule_timeout: 1d  # don't fail until tomorrow
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context).

### `defaults.tags`

A list of tags that are added to every job created by the workflow. A particular job definition can extend this global list by [`jobs.<job-id>.tags`](live-workflow-syntax.md#jobs-less-than-job-id-greater-than-tags).

**Example:**

```yaml
defaults:
  tags: [tag-a, tag-b]
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context).

### `defaults.workdir`

The default working directory for jobs spawned by this workflow.  See [`jobs.<job-id>.workdir`](live-workflow-syntax.md#jobs-less-than-job-id-greater-than-workdir) for more information.

The default working directory for jobs spawn by this workflow. See [`jobs.<job-id>.workdir`](live-workflow-syntax.md#jobs-less-than-job-id-greater-than-workdir) for more information.

**Example:**

```yaml
defaults:
  workdir: /users/my_user
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context).

## `images`

A mapping of image definitions used by _live_ workflow.

`neuro-flow build <image-id>` creates an image from passed `Dockerfile` and uploads it to the Neu.ro Registry. `${{ images.img_id.ref }}` expression can be used for pointing the image from a [`jobs.<job-id>.image`](live-workflow-syntax.md#jobs-less-than-job-id-greater-than-image).

{% hint style="info" %}
The `images` section is not required, a job can specify the image name as a plain string without referring to `${{ images.my_image.ref }}` context.

The section exists for convenience: there is no need to repeat yourself if you can just point the image ref everywhere in the YAML.
{% endhint %}

### `images.<image-id>`

The key image`-id` is a string and its value is a map of the job's configuration data. You must replace `<image-id>` with a string that is unique to the `images` object. The `<image-id>` must start with a letter and contain only alphanumeric characters or `_`. Dash `-` is not allowed.

### `images.<image-id>.ref`

**Required** Image _reference_ that can be used in [`jobs.<job-id>.image`](live-workflow-syntax.md#jobs-less-than-job-id-greater-than-image) expression.

**Example of self-hosted image:**

```yaml
images:
  my_image:
    ref: image:my_image:latest
```

You can use the image definition to _address_ images hosted on [_Docker Hub_](https://hub.docker.com/search?q=&type=image) as an _external_ source \(while you cannot use `neuro-flow` to build this image\). All other attributes except `ref` make no sense for _external_ images.

**Example of external image:**

```yaml
images:
  python:
    ref: python:3.9.0
```

{% hint style="info" %}
Use [`hash_files()`](expression-functions.md#hash_files-pattern) embedded function to calculate the built image tag based on the image's content.
{% endhint %}

**Example of auto-calculated stable hash:**

```yaml
images:
  my_image:
    ref: image:my_image:${{ hash_files('Dockerfile', 'requirements/*.txt', 'modules/**/*.py') }}
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context).

### `images.<image-id>.context`

The Docker _context_ used to build an image, a local path relative to the project root folder. The context should contain the `Dockerfile` and any additional files and folders that should be copied to the image.

**Example:**

```yaml
images:
  my_image:
    context: path/to/context
```

{% hint style="info" %}
`neuro-flow` cannot build images without the context set but can address _pre-built_ images using [`images.<image-id>.ref`](live-workflow-syntax.md#images-less-than-image-id-greater-than-ref)\`\`
{% endhint %}

**Expression contexts:** [`flow` context](live-contexts.md#flow-context).

### `images.<image-id>.dockerfile`

An optional docker file name used for building images, `Dockerfile` by default.

**Example:**

```yaml
images:
  my_image:
    dockerfile: MyDockerfile
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context).

### `images.<image-id>.build_args`

A list of optional build arguments passed to the image builder. See docker [help](https://docs.docker.com/engine/reference/commandline/build/#set-build-time-variables---build-arg) for details.

**Example:**

```yaml
images:
  my_image:
    build_args:
    - ARG1=val1
    - ARG2=val2
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context).

### `images.<image-id>.env`

A mapping of _environment variables_ passed to the image builder.

**Example:**

```yaml
images:
  my_image:
    env:
      ENV1: val1
      ENV2: val2
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context).

### `images.<image-id>.volumes`

A list of volume references mounter to the image build process.

**Example:**

```yaml
images:
  my_image:
    volumes:
    - storage:folder1:/mnt/folder1:ro
    - storage:folder2:/mnt/folder2
    - volumes.volume_id.ref
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context).

## `volumes`

A mapping of volume definitions available in the _live_ workflow. A volume defines a link between the Neu.ro storage folder, a remote folder that can be mounted to a _live_ job, and a local folder.

Volumes can be synchronized between local and storage versions by `neuro-flow upload` and `neuro-flow download` commands and they can be mounted to a job by using [`jobs.<job-id>.volumes`](live-workflow-syntax.md#jobs-less-than-job-id-greater-than-volumes) attribute.

{% hint style="info" %}
The `volumes` section is optional, a job can mount a volume by a direct reference string.

The section is very handy to use in a bundle with `run`, `upload`, `download` commands: define a volume once and refer everywhere by name without copy-pasting all the definition details.
{% endhint %}

### `volumes.<volume-id>`

The key `volume-id` is a string and its value is a map of the volume's configuration data. You must replace `<volume-id>` with a string that is unique to the `volumes` object. The `<volume-id>` must start with a letter and contain only alphanumeric characters or `_`. Dash `-` is not allowed.

### `volumes.<volume-id>.remote`

**Required** The volume URI on the Neu.ro Storage.

**Example:**

```yaml
volumes:
  folder:
    remote: storage:path/to/folder
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context).

### `volumes.<volume-id>.mount`

**Required** The mount path inside a job.

**Example:**

```yaml
volumes:
  folder:
    mount: /mnt/folder
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context).

### `volumes.<volume-id>.local`

A _local_ path relative to the project root. Used for uploading/downloading the content on the storage.

Volumes without `local` attribute set cannot be used by `neuro-flow upload` and `neuro-flow download` commands.

**Example:**

```yaml
volumes:
  folder:
    local: path/to/folder
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context).

### `volumes.<volume-id>.read_only`

The volume is mounted as _read-only_ by default if the attribute is set, _read-write_ mode is used otherwise.

**Example:**

```yaml
volumes:
  folder:
    read_only: true
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context).

## `jobs`

A _live_ workflow can run jobs by their identifiers using `neuro-flow run <job-id>` command. Each job runs remotely on the Neu.ro Platform.

### `jobs.<job-id>` <a id="jobs-job-id-env"></a>

Each job must have an id to associate with the job. The key `job-id` is a string and its value is a map of the job's configuration data or action call. You must replace `<job-id>` with a string that is unique to the `jobs` object. The `<job-id>` must start with a letter and contain only alphanumeric characters or `_`. Dash `-` is not allowed.

## Attributes for both jobs and action calls

The attributes in this section can be applied both to plain jobs and action calls. To simplify reading, this section uses the term "job" instead of "job or action call".

### `jobs.<job-id>.params`

Params is a mapping of key-value pairs that have default value and could be overridden from a command line by using `neuro-flow run <job-id> --param name1 val1 --param name2 val2`

This attribute describes a set of param names accepted by a job and their default values.

The parameter can be specified in a _short_ and _long_ form.

The short form is compact but allows to specify the parameter name and default value only:

```yaml
jobs:
  my_job:
    params:
      name1: default1
      name2: ~   # None by default
      name3: ""  # Empty string by default
```

The long form allows to point the parameter description also \(can be useful for `neuro-flow run` command introspection, the shell autocompletion, and generation a more verbose error message if needed:

```yaml
jobs:
  my_job:
    params:
      name1:
        default: default1
        descr: The name1 description
      name2:
        default: ~
        descr: The name2 description
      name3:
        default: ""
        descr: The name3 description
```

Both examples above are equal but the last has parameter descriptions.

The params can be used in expressions for calculating other job attributes, e.g. [`jobs.<job-id>.cmd`](live-workflow-syntax.md#jobs-less-than-job-id-greater-than-cmd) .

**Example:**

```yaml
jobs:
  my_job:
    params:
      folder: "."  # search in current folder by default
      pattern: "*"  # all files by default
    cmd:
      find ${{ params.folder }} -name ${{ params.pattern }}
```

**Expression contexts:** This attribute only allows expressions that do not access contexts.

## Attributes for jobs

The attributes in this section are only applicable to the plain jobs, that are executed by running docker images on the Neu.ro platform.

### `jobs.<job-id>.image`

**Required** Each job is executed remotely on the Neu.ro cluster using a _Docker image_. The image can be hosted on [_Docker Hub_](https://hub.docker.com/search?q=&type=image) \(`python:3.9` or `ubuntu:20.04`\) or on the Neu.ro Registry \(`image:my_image:v2.3`\).

**Example with a constant image string:**

```yaml
jobs:
  my_job:
    image: image:my_image:v2.3
```

Often you want to use the reference to [`images.<image-id>`](live-workflow-syntax.md#images-less-than-image-id-greater-than).

**Example with a reference to `images` section:**

```yaml
jobs:
  my_job:
    image: ${{ images.my_image.ref }}
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context), [`env` context](live-contexts.md#env-context), [`tags` context](live-contexts.md#tags-context), [`volumes` context](live-contexts.md#volumes-context), [`images` context](live-contexts.md#images-context), [`params` context](live-contexts.md#params-context), [`multi` context](live-contexts.md#multi-context) \(if [`jobs.<job-id>.multi`](live-workflow-syntax.md#jobs-less-than-job-id-greater-than-multi) is set\).

### `jobs.<job-id>.cmd`

A job executes either a _command_, or _bash_ script, or _python_ script. The `cmd`, `bash,` and `python` are **mutually exclusive**: only one of three is allowed. If none of these three attributes are specified the [`CMD`](https://docs.docker.com/engine/reference/builder/#cmd) from the [`jobs.<job-id>.image`](live-workflow-syntax.md#jobs-less-than-job-id-greater-than-image) is used.

`cmd` attribute points on the command with optional arguments which is available in the executed [`jobs.<job-id>.image`](live-workflow-syntax.md#jobs-less-than-job-id-greater-than-image) .

**Example:**

```yaml
jobs:
  my_job:
    cmd: tensorboard --host=0.0.0.0
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context), [`env` context](live-contexts.md#env-context), [`tags` context](live-contexts.md#tags-context), [`volumes` context](live-contexts.md#volumes-context), [`images` context](live-contexts.md#images-context), [`params` context](live-contexts.md#params-context), [`multi` context](live-contexts.md#multi-context) \(if [`jobs.<job-id>.multi`](live-workflow-syntax.md#jobs-less-than-job-id-greater-than-multi) is set\).

### `jobs.<job-id>.bash`

The attribute contains a `bash` script to run.

Using `cmd` to run bash script is tedious: you need to apply quotas to the executed script and setup the proper bash flags to fail on error.

The `bash` attribute is essentially a shortcut for `cmd: bash -euo pipefail -c <shell_quoted_attr>` .

This form is especially handy for executing multi-line complex bash scripts.

The `cmd`, `bash,` and `python` are **mutually exclusive**.

The `bash` should be pre-installed in the image to make this attribute work.

**Example:**

```yaml
jobs:
  my_job:
    bash: |
      for arg in {1..5}
      do
        echo "Step ${arg}"
        sleep 1
      done
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context), [`env` context](live-contexts.md#env-context), [`tags` context](live-contexts.md#tags-context), [`volumes` context](live-contexts.md#volumes-context), [`images` context](live-contexts.md#images-context), [`params` context](live-contexts.md#params-context), [`multi` context](live-contexts.md#multi-context) \(if [`jobs.<job-id>.multi`](live-workflow-syntax.md#jobs-less-than-job-id-greater-than-multi) is set\).

### `jobs.<job-id>.python`

The attribute contains a `python` script to run.

Python is the language number one for modern scientific calculations. If you prefer writing simple inlined commands in `python` instead of `bash` this notation is developed for you.

The `python` attribute is essentially a shortcut for `cmd: python3 -uc <shell_quoted_attr>` .

The `cmd`, `bash,` and `python` are **mutually exclusive**.

The `python3` should be pre-installed in the image to make this attribute work.

**Example:**

```yaml
jobs:
  my_job:
    python: |
      import sys
      print("The Python version is", sys.version)
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context), [`env` context](live-contexts.md#env-context), [`tags` context](live-contexts.md#tags-context), [`volumes` context](live-contexts.md#volumes-context), [`images` context](live-contexts.md#images-context), [`params` context](live-contexts.md#params-context), [`multi` context](live-contexts.md#multi-context) \(if [`jobs.<job-id>.multi`](live-workflow-syntax.md#jobs-less-than-job-id-greater-than-multi) is set\).

### `jobs.<job-id>.browse`

Open job's _Http URL_ in a browser. Off by default.

Use this attribute in scenarios like starting a Jupyter Notebook job and opening a browser with the notebook session.

**Example:**

```yaml
jobs:
  my_job:
    browse: true
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context), [`env` context](live-contexts.md#env-context), [`tags` context](live-contexts.md#tags-context), [`volumes` context](live-contexts.md#volumes-context), [`images` context](live-contexts.md#images-context), [`params` context](live-contexts.md#params-context), [`multi` context](live-contexts.md#multi-context) \(if [`jobs.<job-id>.multi`](live-workflow-syntax.md#jobs-less-than-job-id-greater-than-multi) is set\).

### `jobs.<job-id>.detach`

By default, `neuro-flow run <job-id>` keeps the terminal attached to the spawn job. You can see job logs or type a command in an embedded bash session if any.

Set `detach` attribute to disable this behavior.

**Example:**

```yaml
jobs:
  my_job:
    detach: true
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context), [`env` context](live-contexts.md#env-context), [`tags` context](live-contexts.md#tags-context), [`volumes` context](live-contexts.md#volumes-context), [`images` context](live-contexts.md#images-context), [`params` context](live-contexts.md#params-context), [`multi` context](live-contexts.md#multi-context) \(if [`jobs.<job-id>.multi`](live-workflow-syntax.md#jobs-less-than-job-id-greater-than-multi) is set\).

### `jobs.<job-id>.entrypoint`

You can override the Docker image [`ENTRYPOINT`](https://docs.docker.com/engine/reference/builder/#entrypoint) if needed or sets it if one wasn't already specified. Unlike the Docker `ENTRYPOINT` instruction which has a shell and exec form, `entrypoint` attribute accepts only a single string defining the executable to be run.

**Example:**

```yaml
jobs:
  my_job:
    entrypoint: sh -c "Echo $HOME"
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context), [`env` context](live-contexts.md#env-context), [`tags` context](live-contexts.md#tags-context), [`volumes` context](live-contexts.md#volumes-context), [`images` context](live-contexts.md#images-context), [`params` context](live-contexts.md#params-context), [`multi` context](live-contexts.md#multi-context) \(if [`jobs.<job-id>.multi`](live-workflow-syntax.md#jobs-less-than-job-id-greater-than-multi) is set\).

### `jobs.<job-id>.env` <a id="jobs-job-id-env"></a>

Sets environment variables for `<job-id>` to use in the executed job. You can also set environment variables for the entire workflow. For more information, see [`defaults.env`](live-workflow-syntax.md#defaults-env).

When more than one environment variable is defined with the same name, `neuro-flow` uses the most specific environment variable. For example, an environment variable defined in a task will override the [workflow default](live-workflow-syntax.md#defaults-env).

**Example:**

```yaml
jobs:
  my_job:
    env:
      ENV1: val1
      ENV2: val2
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context), [`env` context](live-contexts.md#env-context), [`tags` context](live-contexts.md#tags-context), [`volumes` context](live-contexts.md#volumes-context), [`images` context](live-contexts.md#images-context), [`params` context](live-contexts.md#params-context), [`multi` context](live-contexts.md#multi-context) \(if [`jobs.<job-id>.multi`](live-workflow-syntax.md#jobs-less-than-job-id-greater-than-multi) is set\).

### `jobs.<job-id>.http_auth`

Control whether the HTTP port exposed by the job requires the Neu.ro Platform authentication for access.

You can want to disable the authentication to allow everybody to access your job's exposed web resource.

The job has HTTP protection by default.

**Example:**

```yaml
jobs:
  my_job:
    http_auth: false
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context), [`env` context](live-contexts.md#env-context), [`tags` context](live-contexts.md#tags-context), [`volumes` context](live-contexts.md#volumes-context), [`images` context](live-contexts.md#images-context), [`params` context](live-contexts.md#params-context), [`multi` context](live-contexts.md#multi-context) \(if [`jobs.<job-id>.multi`](live-workflow-syntax.md#jobs-less-than-job-id-greater-than-multi) is set\).

### `jobs.<job-id>.http_port`

The jobs HTTP port number to expose globally.

By default, the Neu.ro Platform exposes the job's internal `80` port as HTTPS protected resource enumerated by `neuro-flow status <job-id>` command as _Http URL_.

You may want to expose a different local port. Use `0` to disable the feature entirely.

**Example:**

```yaml
jobs:
  my_job:
    http_port: 8080
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context), [`env` context](live-contexts.md#env-context), [`tags` context](live-contexts.md#tags-context), [`volumes` context](live-contexts.md#volumes-context), [`images` context](live-contexts.md#images-context), [`params` context](live-contexts.md#params-context), [`multi` context](live-contexts.md#multi-context) \(if [`jobs.<job-id>.multi`](live-workflow-syntax.md#jobs-less-than-job-id-greater-than-multi) is set\).

### `jobs.<job-id>.life_span`

The time period at the end of that the job will be automatically killed.

By default, the job lives 1 day.

You may want to increase this period by customizing the attribute.

The value is a float number of seconds \(`3600` for an hour\) or expression in the following format: `1d6h15m` \(1 day 6 hours, 15 minutes\). Use an arbitrary huge value \(e.g. `365d`\) for the life-span disabling emulation \(it can be dangerous, a forgotten job consumes the cluster resources\).

The [`defaults.life_span`](live-workflow-syntax.md#defaults-life_span)value is used if the attribute is not set.

**Example:**

```yaml
jobs:
  my_job:
    life_span: 14d12h
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context), [`env` context](live-contexts.md#env-context), [`tags` context](live-contexts.md#tags-context), [`volumes` context](live-contexts.md#volumes-context), [`images` context](live-contexts.md#images-context), [`params` context](live-contexts.md#params-context), [`multi` context](live-contexts.md#multi-context) \(if [`jobs.<job-id>.multi`](live-workflow-syntax.md#jobs-less-than-job-id-greater-than-multi) is set\).

### `jobs.<job-id>.name`

You can specify the project name if needed. The name becomes a part of job's internal hostname and exposed HTTP URL, the job can be controlled by it's name when low-level `neuro` tool is used.

The name is _optional_, `neuro-flow` tool doesn't need it.

**Example:**

```yaml
jobs:
  my_job:
    name: my-name
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context), [`env` context](live-contexts.md#env-context), [`tags` context](live-contexts.md#tags-context), [`volumes` context](live-contexts.md#volumes-context), [`images` context](live-contexts.md#images-context), [`params` context](live-contexts.md#params-context), [`multi` context](live-contexts.md#multi-context) \(if [`jobs.<job-id>.multi`](live-workflow-syntax.md#jobs-less-than-job-id-greater-than-multi) is set\).

### `jobs.<job-id>.multi`

By default, the job can have the only running instance at the time. The next `neuro-flow run <job-id>` call for the same job attaches to the running job instead of recreating a new one. This can be overridden by setting `multi` attribute.

**Example:**

```yaml
jobs:
  my_job:
    multi: true
```

**Expression contexts:** This attribute only allows expressions that do not access contexts. 

### `jobs.<job-id>.pass_config`

Set the attribute to `true` if you want to pass the Neuro current config used to execute `neuro-flow run ...` command into the spawn job. It can be useful if you use a job image with Neuro CLI installed and want to execute `neuro ...` commands _inside_ the running job.

By default the config is not passed.

**Example:**

```yaml
jobs:
  my_job:
    pass_config: true
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context), [`env` context](live-contexts.md#env-context), [`tags` context](live-contexts.md#tags-context), [`volumes` context](live-contexts.md#volumes-context), [`images` context](live-contexts.md#images-context), [`params` context](live-contexts.md#params-context), [`multi` context](live-contexts.md#multi-context) \(if [`jobs.<job-id>.multi`](live-workflow-syntax.md#jobs-less-than-job-id-greater-than-multi) is set\).

### `jobs.<job-id>.port-forward`

You can define a list of TCP tunnels for the job.

Each port forward entry is a string with `<LOCAL_PORT>:<REMOTE_PORT>` format.

When the job starts all enumerated _remote ports_ on the job side are bound with the developer's box and available under the corresponding _local port_ numbers.

You can use the feature, for example, for remote debugging or accessing a database running in the job.

**Example:**

```yaml
jobs:
  my_job:
    port_forward:
    - 6379:6379  # Default Redis port
    - 9200:9200  # Default Zipkin port
```

### `jobs.<job-id>.preset`

The preset name to execute the job with. [`defaults.preset`](live-workflow-syntax.md#defaults-preset) is used if the preset is not specified for the job.

**Expression contexts:** [`flow` context](live-contexts.md#flow-context), [`env` context](live-contexts.md#env-context), [`tags` context](live-contexts.md#tags-context), [`volumes` context](live-contexts.md#volumes-context), [`images` context](live-contexts.md#images-context), [`params` context](live-contexts.md#params-context), [`multi` context](live-contexts.md#multi-context) \(if [`jobs.<job-id>.multi`](live-workflow-syntax.md#jobs-less-than-job-id-greater-than-multi) is set\).

### `jobs.<job-id>.schedule_timeout`

Use this attribute if you want to increase the _schedule timeout_ to prevent the job from fail if the Neu.ro cluster is under high load and requested resources a not available at the moment highly likely.

If the Neu.ro cluster has no resources to launch a job immediately the job is pushed into the wait queue. If the job is not started yet at the moment of _schedule timeout_ expiration the job is failed.

The default system-wide _schedule timeout_ is controlled by the cluster administrator and usually is about 5-10 minutes. 

The attribute accepts either a `float` number of seconds or a string in`1d6h15m45s` \(1 day 6 hours, 15 minutes, 45 seconds\).

See also [`defaults.schedule_timeout`](live-workflow-syntax.md#defaults-schedule_timeout) if you want to set the workflow-wide schedule timeout for all jobs.

**Example:**

```yaml
jobs:
  my_job:
    schedule_timeout: 1d  # don't fail until tomorrow
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context), [`env` context](live-contexts.md#env-context), [`tags` context](live-contexts.md#tags-context), [`volumes` context](live-contexts.md#volumes-context), [`images` context](live-contexts.md#images-context), [`params` context](live-contexts.md#params-context), [`multi` context](live-contexts.md#multi-context) \(if [`jobs.<job-id>.multi`](live-workflow-syntax.md#jobs-less-than-job-id-greater-than-multi) is set\).

### `jobs.<job-id>.tags`

A list of additional job tags.

Each _live_ job is tagged. The job tags are from tags enumerated by this attribute, [`defaults.tags`](live-workflow-syntax.md#defaults-tags) and system tags \(`project:<project-id>` and `job:<job-id>`\).

**Example:**

```yaml
jobs:
  my_job:
    tags:
    - tag-a
    - tag-b
```

### `jobs.<job-id>.title`

The job title. The title is equal to `<job-id>` if not overridden.

**Expression contexts:** [`flow` context](live-contexts.md#flow-context), [`env` context](live-contexts.md#env-context), [`tags` context](live-contexts.md#tags-context), [`volumes` context](live-contexts.md#volumes-context), [`images` context](live-contexts.md#images-context), [`params` context](live-contexts.md#params-context), [`multi` context](live-contexts.md#multi-context) \(if [`jobs.<job-id>.multi`](live-workflow-syntax.md#jobs-less-than-job-id-greater-than-multi) is set\).

### `jobs.<job-id>.volumes`

A list of job volumes. You can specify a bare string for the volume reference or use `${{ volumes.<volume-id>.ref }}` expression.

**Example:**

```yaml
jobs:
  my_job:
    volumes:
    - storage:path/to:/mnt/path/to
    - ${{ volumes.my_volume.ref }}
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context), [`env` context](live-contexts.md#env-context), [`tags` context](live-contexts.md#tags-context), [`volumes` context](live-contexts.md#volumes-context), [`images` context](live-contexts.md#images-context), [`params` context](live-contexts.md#params-context), [`multi` context](live-contexts.md#multi-context) \(if [`jobs.<job-id>.multi`](live-workflow-syntax.md#jobs-less-than-job-id-greater-than-multi) is set\).

### `jobs.<job-id>.workdir`

The current working dir to use inside the job.

This attribute takes precedence if set. Otherwise, [`defaults.workdir`](live-workflow-syntax.md#defaults-workdir) is used if present. Otherwise, a [`WORKDIR`](https://docs.docker.com/engine/reference/builder/#workdir) definition from the image is used.

**Example:**

```yaml
jobs:
  my_job:
    workdir: /users/my_user
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context), [`env` context](live-contexts.md#env-context), [`tags` context](live-contexts.md#tags-context), [`volumes` context](live-contexts.md#volumes-context), [`images` context](live-contexts.md#images-context), [`params` context](live-contexts.md#params-context), [`multi` context](live-contexts.md#multi-context) \(if [`jobs.<job-id>.multi`](live-workflow-syntax.md#jobs-less-than-job-id-greater-than-multi) is set\).

## Attributes for actions calls

The attributes in this section are only applicable to the action calls. An action is a reusable part that can be integrated into the workflow. Refer to [actions reference](actions-syntax.md) to learn more about actions.

### `jobs.<job-id>.action`

The URL that selects the action to run. It supports two schemes: `workspace:` for actions files that are stored locally and `github:` for actions that are bound to the Github repository. Same support short forms: `ws:` and `gh:` , respectively.

The `ws:` scheme expects a valid filesystem path to the action file.

The `gh:` scheme expects the next format `{owner}/{repo}@{tag}`. Here `{owner}` is the owner of the Github repository, `{repo}` is the repository name and `{tag}` is the commit tag. Commit tags are used to allow a versioning of the actions.

**Example of `ws:` scheme**

```yaml
jobs:
  my_job:
    action: ws:path/to/file/some-action.yml
```

**Example of `gh:` scheme**

```yaml
jobs:
  my_job:
    action: gh:username/repository@v1
```

**Expression contexts:** This attribute only allows expressions that do not access contexts.

### `jobs.<job-id>.args`

Mapping of values that will be passed to the actions as arguments. This should correspond to [`inputs`](actions-syntax.md#inputs) defined in the action file.

**Example:**

```yaml
jobs:
  my_job:
    args:
      param1: value1          # You can pass constant
      param2: ${{ flow.id }}  # Or some expresion value
```

**Expression contexts:** [`flow` context](live-contexts.md#flow-context), [`env` context](live-contexts.md#env-context), [`tags` context](live-contexts.md#tags-context), [`volumes` context](live-contexts.md#volumes-context), [`images` context](live-contexts.md#images-context), [`params` context](live-contexts.md#params-context), [`multi` context](live-contexts.md#multi-context) \(if [`jobs.<job-id>.multi`](live-workflow-syntax.md#jobs-less-than-job-id-greater-than-multi) is set\).

