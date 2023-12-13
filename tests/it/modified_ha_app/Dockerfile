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

FROM xrd-ha-app:test-base

ARG THIS_DIR=tests/it/modified_ha_app

USER root
ARG DEBIAN_FRONTEND=noninteractive
RUN apt update && apt install -y sudo iproute2
RUN sh -c "echo 'appuser ALL=(ALL:ALL) NOPASSWD: ALL' > /etc/sudoers.d/appuser"
USER appuser

RUN pip install coverage
COPY .coveragerc ./
COPY $THIS_DIR/entrypoint.sh ./

ENTRYPOINT ["./entrypoint.sh"]
