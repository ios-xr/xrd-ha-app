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

import subprocess

import pytest
from python_on_whales import DockerClient as CtrClient
from python_on_whales import Image as CtrImage

import ha_app


@pytest.fixture(scope="module")
def git_commit_hash() -> str:
    return subprocess.check_output(
        ["git", "log", "-1", "--format=%H"], timeout=5, text=True
    ).strip()


def test_not_run_as_root(ctr_client: CtrClient, ha_image: CtrImage):
    output = ctr_client.run(
        ha_image,
        entrypoint="",
        command=["whoami"],
        remove=True,
    )
    assert output == "appuser"


def test_labels(ha_image: CtrImage, git_commit_hash: str):
    assert (
        ha_image.config.labels["com.cisco.ios-xr.xrd-ha-app.git-commit"]
        == git_commit_hash
    )
    assert ha_image.config.labels[
        "com.cisco.ios-xr.xrd-ha-app.version-label"
    ].startswith(ha_app.__version__)
