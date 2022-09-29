#!/bin/sh

set -e

# This is the target from the ~/.dbt/profile.yml (copied from profile-prod.yml), showing which glue databases to use
# default is docker to have a sane fallback to use user paths instead of prod
# prod needs to set `DBT_TARGET=prod`
DBT_TARGET=${DBT_TARGET:-'docker'}

echo "Activating python environment"
. /venv/bin/activate

echo "Showing aws debug info"
aws sts get-caller-identity

echo "Showing python debug info (python = $(command -v python)"
python --version

#echo "Setting up any needed dependencies"
#dbt deps --target ${DBT_TARGET}

echo "Showing debug output ..."
echo "Using dbt target: DBT_TARGET=${DBT_TARGET} "
dbt --version
dbt debug --target ${DBT_TARGET}
dbt list --target ${DBT_TARGET}

echo "Running dbt run..."
dbt run --target ${DBT_TARGET}

echo "Run dbt test..."
dbt test --target ${DBT_TARGET}
