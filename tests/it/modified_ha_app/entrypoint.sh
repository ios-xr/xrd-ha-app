#!/bin/bash

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

# These env vars will normally be set by AWS IRSA.
export AWS_ACCESS_KEY_ID="key"
export AWS_SECRET_ACCESS_KEY="secret-key"

if [[ $ADD_AWS_METADATA_ROUTE ==  1 ]]; then
    sudo ip route add 169.254.169.254/32 dev eth0
fi

if [[ $COLLECT_COVERAGE == 1 ]]; then
    exec tini -- \
        python3 -m coverage run \
            --append \
            --data-file /data/.coverage \
            -m ha_app "$@"
else
    exec tini -- python3 -m ha_app "$@"
fi
