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

import pytest
from python_on_whales import DockerClient as CtrClient

from .utils import ROOT_DIR


logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Pytest hooks
# -----------------------------------------------------------------------------


def pytest_addoption(parser: pytest.Parser) -> None:
    """Pytest hook for adding CLI options."""
    group = parser.getgroup("cov")
    group.addoption(
        "--cov-it",
        action="store_true",
        help="Collect code coverage for the HA app IT tests",
    )
    group = parser.getgroup("ha_app", "HA app")
    group.addoption(
        "--container-exe",
        metavar="EXE",
        default="docker",
        help="The executable used to manage containers, defaults to 'docker'",
    )


# -----------------------------------------------------------------------------
# Session fixtures
# -----------------------------------------------------------------------------


@pytest.fixture(scope="session")
def ctr_client(pytestconfig: pytest.Config) -> CtrClient:
    """A container client for performing container operations."""
    ctr_exe = pytestconfig.getoption("--container-exe")
    logger.debug(f"Creating client, using %r", ctr_exe)
    return CtrClient(client_call=[ctr_exe])


@pytest.fixture(scope="session")
def app_version() -> str:
    """The current HA app version string."""
    return (ROOT_DIR / "ha_app" / "version.txt").read_text()
