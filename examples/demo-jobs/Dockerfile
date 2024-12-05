FROM ghcr.io/neuro-inc/base:v24.12.0-runtime

ENV DEBIAN_FRONTEND noninteractive

COPY . /cfg

RUN apt-get -qq update && cat /cfg/apt.txt | tr -d \"\\r\" | xargs -I % apt-get -qq install --no-install-recommends % && apt-get -qq clean && apt-get autoremove && rm -rf /var/lib/apt/lists/*

RUN pip install --progress-bar=off -U --no-cache-dir -r /cfg/requirements.txt
