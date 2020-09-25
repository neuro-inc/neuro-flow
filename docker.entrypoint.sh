#!/usr/bin/env bash

set -e

# Run some command to make cli parse and setup config passed by --pass-config
neuro help > /dev/null

if [ -n "$NEURO_CLUSTER" ]
then
    neuro config switch-cluster "$NEURO_CLUSTER" 1>/dev/null
fi

exec "$@"
