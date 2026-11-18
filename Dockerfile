# FiniexCorpusEngine's servers in a container. The image holds Python and the packages only; the repository, its data
# folders and its .env are mounted at /app (docker-compose.yml), so a change to the code takes effect when the container
# restarts, and the data never enters the image.
FROM python:3.13-slim

ENV PYTHONPATH=/app/src \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8

# git: the reading store asks git, before it opens, that its folder is one git ignores. The mounted tree belongs to
# another user than the container's, which git refuses unless it is named safe. This layer comes first: it changes
# never, and the Debian mirror is slow, so a change to the requirements rebuilds only the layer below.
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/* \
    && git config --global --add safe.directory /app

WORKDIR /app
COPY requirements.txt /tmp/requirements.txt
# "-e ." installs the code from the tree; here the mounted tree is on PYTHONPATH instead.
RUN grep -v '^-e ' /tmp/requirements.txt > /tmp/packages.txt \
    && pip install --no-cache-dir -r /tmp/packages.txt \
    && rm /tmp/requirements.txt /tmp/packages.txt
