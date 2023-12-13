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

import logging
import subprocess

import pytest
from python_on_whales import DockerClient as CtrClient
from python_on_whales import Image as CtrImage

from ..utils import ROOT_DIR


logger = logging.getLogger(__name__)


@pytest.fixture(scope="package")
def ha_image(pytestconfig: pytest.Config, ctr_client: CtrClient) -> CtrImage:
    """Build the HA container image using the build_image.sh script."""
    logger.info(f"Building HA app container image using build_image.sh")
    proc = subprocess.run(
        [
            # fmt: off
            ROOT_DIR / "scripts" / "build_image.sh",
            "--container-exe", pytestconfig.getoption("--container-exe"),
            # fmt: on
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=True,
        timeout=30,
    )
    logger.debug("Got build_image.sh output:\n%s", proc.stdout)
    return ctr_client.image.inspect("xrd-ha-app")
