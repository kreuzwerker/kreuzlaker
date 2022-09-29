# based on https://stackoverflow.com/a/57886655/1380673 and https://github.com/dbt-labs/dbt-core/tree/main/docker
# General idea:
# Built in stages, with the builder installing into a venv so the whole venv can be copied with just what you need

# Top level build args
ARG build_for=linux/amd64

FROM --platform=$build_for python:3.10.7-alpine as base

ENV PYTHONFAULTHANDLER=1 \
    PYTHONHASHSEED=random \
    PYTHONUNBUFFERED=1

# needed in both the builder (potentially) and the final one
RUN apk add --no-cache git

WORKDIR /app

FROM base as builder

ARG poetry_version=1.2.1

ENV PIP_DEFAULT_TIMEOUT=100 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apk add --no-cache gcc libffi-dev musl-dev
# first install poetry, then the venv -> we do not want poetry in the final image
RUN pip install "poetry==$poetry_version"
RUN python -m venv /venv

# Install first the requirements, so this is cached in the builds
COPY pyproject.toml poetry.lock ./
RUN poetry export -f requirements.txt | /venv/bin/pip install -r /dev/stdin


# We have nothing to install as we just have config for dbt!
# This would install our code as a whl via the venv
#COPY . .
#RUN poetry build && /venv/bin/pip install dist/*.whl


FROM base as final

ARG dbt_project=xw_batch

RUN apk add --no-cache libffi
COPY $dbt_project/ .
COPY --from=builder /venv /venv
COPY docker-entrypoint.sh ./
COPY profiles-prod.yml /root/.dbt/profiles.yml
# install the dbt deps already here
RUN /venv/bin/dbt deps

CMD ["./docker-entrypoint.sh"]
