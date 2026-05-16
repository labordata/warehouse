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
