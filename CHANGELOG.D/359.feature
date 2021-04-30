Added support of default volumes similar to default env: both in live and batch modes, you can
specify them under `defaults` section:
```
defaults:
  volumes:
    - storage:some/dir:/mnt/some/dir
    - storage:some/another/dir:/mnt/some/another/dir
```
- In live mode such volumes will be added to all jobs.
- In batch mode such volumes will be added to all tasks.

Default volumes are not passed to actions (same as default env).
