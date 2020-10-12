#!/usr/bin/env bash

for trial in {1..10}; do
    pip download --no-deps neuro-flow==$1
    if [ $? -eq 0 ]; then
        exit 0
    fi
    echo "Cannot fetch, sleep"
    sleep 10
done
echo "Cannot fetch, fail"
exit 1
