#!/usr/bin/env bash

# Copyright 2023 Cisco Systems Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

set -e

THIS_DIR=$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")
REPO_ROOT=$(dirname "$THIS_DIR")

DEFAULT_CTR_EXE="docker"

usage () {
    echo -n "\
Usage: $(basename "$0") [-h|--help] [-c|--container-exe] [--] ...

Build the HA app container image.

Optional arguments:
  --container-exe EXE  Container client executable (defaults to '$DEFAULT_CTR_EXE')
  [--] ...             Args passed through to the container build command
"
}

# ---------------------
# Parse args
# ---------------------

CTR_EXE=$DEFAULT_CTR_EXE
CTR_CLIENT_ARGS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h | --help )
            usage
            exit 0
            ;;
        -c | --container-exe )
            CTR_EXE=$2
            shift 2
            ;;
        -- )
            shift
            CTR_CLIENT_ARGS+=("$@")
            break
            ;;
        *)
            CTR_CLIENT_ARGS+=("$1")
            shift
            ;;
    esac
done

# ---------------------
# Main logic
# ---------------------

GIT_COMMIT=$(git log -1 --format=%H)
VERSION_LABEL=$(cat "$REPO_ROOT/ha_app/version.txt")
GIT_TAGS=$(git describe --tags 2>/dev/null || true)
if [[ " $GIT_TAGS " == *" $VERSION_LABEL "* ]]; then
    TAG_VERSION=$VERSION_LABEL
else
    echo "WARNING: Version $VERSION_LABEL from version.txt not found in git tags" >&2
    TAG_VERSION=${GIT_COMMIT:0:8}
    VERSION_LABEL="$VERSION_LABEL+${GIT_COMMIT:0:8}"
fi

"$CTR_EXE" build "$REPO_ROOT" \
    --tag xrd-ha-app:latest \
    --tag xrd-ha-app:"$TAG_VERSION" \
    --build-arg GIT_COMMIT="$GIT_COMMIT" \
    --build-arg VERSION_LABEL="$VERSION_LABEL" \
    "${CTR_CLIENT_ARGS[@]}"
