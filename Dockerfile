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

FROM python:3.11-slim-bullseye

# Add Tini to serve as the init process.
# https://petermalmgren.com/signal-handling-docker/
ARG TINI_VERSION=v0.19.0
ADD https://github.com/krallin/tini/releases/download/${TINI_VERSION}/tini /usr/bin/tini
RUN chmod +x /usr/bin/tini

# Add non-root user.
RUN useradd --create-home appuser
USER appuser
WORKDIR /home/appuser/

# Install app requirements.
COPY requirements.txt /tmp/
# We don't use scripts installed by pip, ignore the warning.
ARG PIP_NO_WARN_SCRIPT_LOCATION=0
# We're upgrading pip, we don't need to be warned about this.
ARG PIP_DISABLE_PIP_VERSION_CHECK=1
# We don't need the pip cache in the image, we're only installing once.
ARG PIP_NO_CACHE_DIR=1
RUN pip install -U pip wheel && pip install -r /tmp/requirements.txt

# Copy app code in.
COPY ha_app/ ./ha_app/

# Set labels based on args expected to be passed via '--build-arg'.
ARG GIT_COMMIT=unknown
ARG VERSION_LABEL=unknown
LABEL com.cisco.ios-xr.xrd-ha-app.git-commit=${GIT_COMMIT}
LABEL com.cisco.ios-xr.xrd-ha-app.version-label=${VERSION_LABEL}

ENTRYPOINT ["tini", "--", "python3", "-m", "ha_app"]
