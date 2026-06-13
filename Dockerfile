# Data-less Datasette image for Fly.io deployment.
#
# Unlike the Cloud Run image (built ad-hoc by `datasette package *.db`), this
# image bundles ONLY datasette + plugins + config. The SQLite databases live
# on a Fly Volume mounted at /data and are uploaded out-of-band via
# `fly ssh sftp`, decoupling code and data deploys.
#
# Result: image is ~100 MB instead of ~2 GB, deploys take seconds, and
# updating data doesn't require a redeploy.

FROM python:3.12-slim

# pysqlite3-binary wants build tools when no wheel matches; with python:slim
# we usually get the binary wheel, but include build-essential just in case.
# wget is for pull-from-r2-direct.sh: it length-checks and retries
# downloads, unlike the hand-rolled urllib loop it replaced, which wrote
# silently truncated .db files when a connection dropped mid-transfer.
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential wget \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    https://github.com/fgregg/datasette/archive/d9e31738fb1eed8aae1c524f036f002b7c127264.zip \
    datasette-atom==0.10a0 \
    datasette-rure \
    pysqlite3-binary \
    datasette-block-robots \
    datasette-pretty-traces \
    https://github.com/fgregg/datasette-schema-org/archive/611e9b3dffaa7aed32f5a56cc250dd8f840f94d1.zip

# Bake the commit SHA into the rootfs so the deploy workflow can SSH
# into the running machine and verify it matches $GITHUB_SHA. Fly's
# control-plane tag→digest cache occasionally hands a machine a stale
# digest after `flyctl machine update --image …:tag` — the API
# reports success but /proc/1/root is on the wrong rootfs. The Verify
# step in deploy.yml compares this file to the expected SHA and fails
# the run if they don't match. deploy.yml also pins by digest, which
# bypasses the cache; this is the second line of defence.
ARG GIT_SHA=unknown
RUN echo "$GIT_SHA" > /etc/build-sha

WORKDIR /app

# Plugins and config — these change with code, not data.
COPY plugins/ /app/plugins/
COPY static/ /app/static/
COPY templates/ /app/templates/
COPY datasette.yml warehouse_metadata.yml /app/
COPY scripts/ /app/scripts/
RUN chmod +x /app/scripts/*.sh

# Databases live on a Fly Volume mounted here.
VOLUME /data

EXPOSE 8080

CMD ["/app/scripts/serve.sh"]
