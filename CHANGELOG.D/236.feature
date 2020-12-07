Support compound expressions for `volumes`, `tags`, `env`, `port_forward` attributes:

```
jobs:
  job_a:
    volumes: "${{ 'ubuntu', volumes.volume_a.ref }}"
```
