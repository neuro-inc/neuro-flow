FROM python:3.7-stretch as requirements

ARG NEURO_FLOW_VERSION

ENV PATH=/root/.local/bin:$PATH

RUN pip install --user \
    neuro-flow==$NEURO_FLOW_VERSION


FROM python:3.7-stretch

COPY --from=requirements /root/.local /root/.local
COPY docker.entrypoint.sh /var/lib/neuro/entrypoint.sh
RUN chmod u+x /var/lib/neuro/entrypoint.sh

WORKDIR /root
ENV PATH=/root/.local/bin:$PATH

ENTRYPOINT ["/var/lib/neuro/entrypoint.sh"]
