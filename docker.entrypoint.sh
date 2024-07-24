#!/usr/bin/env bash

set -e

# Run some command to make cli parse and setup config passed by --pass-config
apolo help > /dev/null

if [ -n "$APOLO_CLUSTER" ]
then
    apolo config switch-cluster "$APOLO_CLUSTER" 1>/dev/null
fi

exec "$@"
