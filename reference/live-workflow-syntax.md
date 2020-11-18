# Live workflow syntax

## _Live_ workflow

The live workflow is always located at `.neuro/live.yml` file under the project root;`.neuro/live.yaml` is also supported if you prefer a longer suffix for some reason. The following YAML attributes are supported:

## `kind`

**Required** The workflow _kind_, __must be `live` for _live_ workflows.

## `id`

Identifier of the workflow. By default, the `id` is `live`.

## `title`

Workflow title

## `defaults`

A map of default settings that will apply to all jobs in the workflow. You can override these global default settings for a particular job.

### `defaults.env`

A mapping of environment variables that are available to all jobs in the workflow. You can also set environment variables that are only available to a job or step. For more information, see [`jobs.<job-id>.env`](live-workflow-syntax.md#jobs-job-id-env).

When more than one environment variable is defined with the same name, `neuro-flow` uses the most specific environment variable. For example, an environment variable defined in a step will override job and workflow variables with the same name, while the step executes. A variable defined for a job will override a workflow variable with the same name, while the job executes.

**Example**:

```yaml
env:
  SERVER: production
```

### `defaults.life_span`

The default life span for jobs run by the workflow.  It can be overridden  by [`jobs.<job-id>.life_span`](live-workflow-syntax.md#jobs-less-than-job-id-greater-than-life_span).  In not set, the default job's life span is 1 day.  The value is a float number of seconds \(`3600` for an hour\) or expression in the following format: `1d6h15m`  \(1 day 6 hours, 15 minutes\). Use an arbitrary huge value \(e.g. `365d`\) for the life-span disabling emulation \(it can be dangerous, a forgotten job consumes the cluster resources\).

{% hint style="warning" %}
life span shorter than _1 minute_ is forbidden.
{% endhint %}

**Example:**

```yaml
defaults:
  life_span: 14d
```

### `defaults.preset`

The default preset name used by all jobs if not overridden by [`jobs.<job-id>.preset`](live-workflow-syntax.md#jobs-less-than-job-id-greater-than-preset).

**Example:**

```yaml
defaults:
  preset: gpu-small
```

### `defaults.tags`

A list of tags that add added to every job created by the workflow. A particular job definition can extend this global list by [`jobs.<job-id>.tags`](live-workflow-syntax.md#jobs-less-than-job-id-greater-than-tags).

**Example with a tag per line:**

```yaml
defaults:
  tags:
  - tag-a
  - tag-b
```

**Example with the compact one-line list:**

```yaml
defaults:
  tags: [tag-a, tag-b]
```

## `images`

A mapping of image definitions used by _live_ workflow.

`neuro-flow build <image-id>` creates an image from passed `Dockerfile` and uploads it to the Neu.ro Registry.  `${{ images.img_id.ref }}` expression can be used for pointing the image from a [`jobs.<job-id>.image`](live-workflow-syntax.md#jobs-less-than-job-id-greater-than-image).

{% hint style="info" %}
The `images` section is not required, a job can specify the image name as a plain string without referring to `${{ images.my_image.ref }}` context.

The section exists for convenience: there is no need to repeat yourself if you can just point the image ref everywhere in the YAML.
{% endhint %}

### `images.<image-id>.ref`

**Required** Image _reference_ that can be used in [`jobs.<job-id>.image`](live-workflow-syntax.md#jobs-less-than-job-id-greater-than-image) expression.

**Example of self-hosted image:**

```yaml
images:
  my_image:
    ref: image:my_image:latest
```

You cannot use `neuro-flow` to make images in DockerHub or another public registry, but you can use the image definition to _address_ it.

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

### `images.<image-id>.dockerfile`

An optional docker file name used for building images, `Dockerfile` by default.

**Example:**

```yaml
images:
  my_image:
    dockerfile: MyDockerfile
```

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

## `volumes`

A mapping of volume definitions available in the _live_ workflow.
A volume defines a link between the Neu.ro storage folder, a remote folder that can be mounted to a _live_ job, and a local folder.

Volumes can be synchronized between local and storage versions by `neuro-flow upload` and `neuro-flow download` commands and they can be mounted to a job by using [`jobs.<job-id>.volumes`](live-workflow-syntax.md#jobs-less-than-job-id-greater-than-volumes) attribute.

{% hint style="info" %}


The `volumes` section is optional, a job can mount a volume by a direct reference string.

The section is very handy to use in a bundle with `run`, `upload`, `download` commands: define a volume once and refer everywhere by name without copy-pasting all the definition details.
{% endhint %}

### `volumes.<volume-id>.remote`

**Required** The volume URI on the Neu.ro Storage.

**Example:**

```yaml
volumes:
  folder:
    remote: storage:path/to/folder
```

### `volumes.<volume-id>.mount`

**Required** The mount path inside a job.

**Example:**

```yaml
volumes:
  folder:
    mount: /mnt/folder
```

### `volumes.<volume-id>.local`

A _local_ path relative to the project root. Used for uploading/downloading the content on the storage.

Volumes without `local` attribute set cannot be used by `neuro-flow upload` and `neuro-flow download` commands.

**Example:**

```yaml
volumes:
  folder:
    local: path/to/folder
```

### `volumes.<volume-id>.read_only`

The volume is mounted as _read-only_ by default if the attribute is set, _read-write_ mode is used otherwise.

**Example:**

```yaml
volumes:
  folder:
    read_only: true
```

## `jobs`

A _live_ workflow can run jobs by their identifiers using `neuro-flow run <job-id>` command. Each job runs remotely on the Neu.ro platform.

### `jobs.<job-id>.env` <a id="jobs-job-id-env"></a>

### `jobs.<job-id>.image`

### `jobs.<job-id>.life_span`

### `jobs.<job-id>.preset`

### `jobs.<job-id>.tags`

### `jobs.<job-id>.volumes`
