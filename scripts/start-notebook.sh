#!/bin/sh
set -eu
exec jupyter lab --ip=0.0.0.0 --no-browser "$@"
