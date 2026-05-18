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
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    datasette==1.0a29 \
    datasette-atom==0.10a0 \
    datasette-rure \
    pysqlite3-binary \
    datasette-block-robots \
    datasette-pretty-traces \
    https://github.com/fgregg/datasette-schema-org/archive/refs/heads/main.zip

# Cache-busting sentinel. Without this, Fly's remote builder occasionally
# reuses the cached COPY layers below across commits even when the
# source files have changed — we hit this exactly once and shipped a
# build that still had the pre-cutover scripts/ layout and a stale
# datasette.yml. This RUN consumes GIT_SHA, so its cache key changes
# every commit, forcing every COPY beneath it to re-execute with
# current sources. The apt-get + pip install layers above stay
# cached, so this only costs ~5s on the cheap layers.
#
# deploy.yml passes --build-arg GIT_SHA=$GITHUB_SHA.
ARG GIT_SHA=unknown
RUN echo "$GIT_SHA" > /etc/build-sha

WORKDIR /app

# Plugins and config — these change with code, not data.
COPY plugins/ /app/plugins/
COPY datasette.yml warehouse_metadata.yml /app/
COPY scripts/ /app/scripts/
RUN chmod +x /app/scripts/*.sh

# Databases live on a Fly Volume mounted here.
VOLUME /data

EXPOSE 8080

CMD ["/app/scripts/serve.sh"]
