FROM python:3.10.2-buster as requirements

ARG NEURO_FLOW_DIST

ENV PATH=/root/.local/bin:$PATH

RUN pip install --user --upgrade pip

ADD ./dist /dist

RUN pip install --user "/${NEURO_FLOW_DIST}"


FROM python:3.10.2-buster

LABEL org.opencontainers.image.source = "https://github.com/neuro-inc/neuro-flow"

COPY --from=requirements /root/.local /root/.local
COPY docker.entrypoint.sh /var/lib/neuro/entrypoint.sh
RUN chmod u+x /var/lib/neuro/entrypoint.sh

WORKDIR /root
ENV PATH=/root/.local/bin:$PATH

ENTRYPOINT ["/var/lib/neuro/entrypoint.sh"]
