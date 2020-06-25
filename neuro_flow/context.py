# Contexts

from dataclasses import dataclass


# neuro -- global settings (cluster, user, api entrypoint)

# env -- Contains environment variables set in a workflow, job, or step

# job -- Information about the currently executing job

# batch -- Information about the currently executing batch

# steps -- Information about the steps that have been run in this job

# secrets -- Enables access to secrets.

# strategy -- Enables access to the configured strategy parameters and information about
# the current job.
# Strategy parameters include batch-index, batch-total,
# (and maybe fail-fast and max-parallel).

# matrix -- Enables access to the matrix parameters you configured for the current job.

# needs -- Enables access to the outputs of all jobs that are defined as a dependency of
# the current job.

# image -- Enables access to image specifications.

# volume -- Enables access to volume specifications.


@dataclass(frozen=True)
class Neuro:
    pass
