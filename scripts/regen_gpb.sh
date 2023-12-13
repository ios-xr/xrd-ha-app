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

# Requires 'grpcio-tools' python package.

set -e


usage () {
    echo -n "\
Usage: $(basename "$0") [-h|--help]
Regenerate the GPB Python code in ha_app/gpb/ from the proto files in protos/.
"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h | --help )
            usage
            exit 0
            ;;
        *)
            echo "Unexpected argument(s)" >&2
            usage >&2
            exit 1
            ;;
    esac
done


OUT_DIR="./ha_app/gpb/"

for proto_file in cisco_grpc_dialout.proto telemetry.proto; do
    echo "Regenerating for $proto_file"
    python3 -m grpc_tools.protoc \
        --python_out="$OUT_DIR" \
        --grpc_python_out="$OUT_DIR" \
        --pyi_out="$OUT_DIR" \
        -I ./protos/ \
        "$proto_file"
done
echo "Done"
