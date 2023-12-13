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

import contextlib
import logging
import textwrap
import time

import pytest
from python_on_whales import Container
from python_on_whales import DockerClient as CtrClient
from python_on_whales import DockerException as CtrException
from python_on_whales import Image as CtrImage
from python_on_whales import Volume as CtrVolume

from . import utils
from .utils import IT_TEST_DIR, ROOT_DIR, AWSEndpoint, HAApp, gRPCClient


logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Package scope fixtures
# -----------------------------------------------------------------------------


@pytest.fixture(scope="package")
def data_volume(ctr_client: CtrClient) -> CtrVolume:
    """A volume for storing data across containers."""
    name = f"test_data__{time.time()}"
    logger.debug("Creating test data volume with name %s", name)
    volume = ctr_client.volume.create(name)
    try:
        with utils.mount_volume(ctr_client, volume, "/data/") as ctr:
            ctr.execute(["chmod", "777", "/data/"])
        yield volume
    finally:
        logger.debug("Removing test data volume %r", name)
        volume.remove()


@pytest.fixture(scope="package", autouse=True)
def copy_coverage_data(
    pytestconfig: pytest.Config, ctr_client: CtrClient, data_volume: CtrVolume
) -> None:
    """
    Retrieve the accumulated coverage data file from the data volume at the end
    of the test run.
    """
    yield

    if pytestconfig.option.cov_it:
        try:
            logger.info("Copying coverage data out of container volume")
            with utils.mount_volume(
                ctr_client, data_volume, "/data/", read_only=True
            ) as ctr:
                ctr.copy_from("/data/.coverage", IT_TEST_DIR / ".coverage")
        except Exception:
            logger.warning("Failed to copy coverage data out of volume", exc_info=True)


@pytest.fixture(scope="package")
def ha_image(ctr_client: CtrClient) -> CtrImage:
    """HA container image fixture - builds the image if required."""
    logger.info(f"Building HA app container image...")
    return ctr_client.legacy_build(ROOT_DIR, tags="xrd-ha-app:test-base")


@pytest.fixture(scope="package")
def test_ha_image(ctr_client: CtrClient, ha_image: CtrImage) -> CtrImage:
    """HA container image modified for use in the IT tests."""
    logger.info(f"Building test HA app container image...")
    return ctr_client.legacy_build(
        ROOT_DIR,
        file=IT_TEST_DIR / "modified_ha_app" / "Dockerfile",
        tags="xrd-ha-app:test-mod",
    )


@pytest.fixture(scope="package")
def minimal_config() -> str:
    """Minimal config for the HA app, to pass config validation."""
    return "groups: []"


@pytest.fixture(scope="package")
def config_volume(ctr_client: CtrClient) -> CtrVolume:
    """Container volume for mounting in HA app config."""
    name = f"ha_app_config__{time.time()}"
    logger.debug("Creating HA app config volume with name %s", name)
    volume = ctr_client.volume.create(name)
    yield volume
    logger.debug("Removing HA config volume %r", name)
    try:
        volume.remove()
    except CtrException:
        logger.warning("Failed to remove volume %r", name, exc_info=True)


@pytest.fixture(scope="package")
def config_volume_ctr(ctr_client: CtrClient, config_volume: CtrVolume) -> Container:
    """
    A simple container with the config volume mounted writable at /etc/ha_app/.
    """
    with utils.mount_volume(ctr_client, config_volume, "/etc/ha_app/") as vol_ctr:
        yield vol_ctr


@pytest.fixture(scope="package")
def app(
    pytestconfig: pytest.Config,
    ctr_client: CtrClient,
    test_ha_image: CtrImage,
    config_volume: CtrVolume,
    config_volume_ctr: Container,
    data_volume: CtrVolume,
) -> HAApp:
    """An HA app object, providing a clean API for running the container."""
    return HAApp(
        ctr_client,
        test_ha_image,
        config_volume,
        config_volume_ctr,
        data_volume if pytestconfig.option.cov_it else None,
    )


@pytest.fixture(scope="package")
def aws_endpoint_image(ctr_client: CtrClient) -> CtrImage:
    """Container image for the mock AWS endpoint, built if required."""
    logger.info(f"Building mock AWS endpoint container image...")
    return ctr_client.legacy_build(
        ROOT_DIR,
        file=IT_TEST_DIR / "aws_endpoint" / "Dockerfile",
        tags="aws_endpoint",
    )


@pytest.fixture(scope="package")
def aws_metadata_service_image(ctr_client: CtrClient) -> CtrImage:
    """Container image for the mock AWS metadata service, built if required."""
    logger.info(f"Building mock AWS metadata service container image...")
    return ctr_client.legacy_build(
        ROOT_DIR,
        file=IT_TEST_DIR / "aws_metadata_service" / "Dockerfile",
        tags="aws_metadata",
    )


@pytest.fixture(scope="package")
def grpc_client(ctr_client: CtrClient) -> gRPCClient:
    """A gRPC client object, providing APIs for sending gRPC messages."""
    return gRPCClient(ctr_client)


# -----------------------------------------------------------------------------
# Function scope fixtures
# -----------------------------------------------------------------------------


@pytest.fixture(scope="function")
def default_config(aws_endpoint: AWSEndpoint) -> str:
    """
    Some default HA app config, for convenience in tests that just want an
    action configured.
    """
    return textwrap.dedent(
        f"""\
        global:
            port: 50051
            aws:
                ec2_private_endpoint_url: "http://{aws_endpoint.ip_address}"
        groups:
          - xr_interface: HundredGigE0/0/0/1
            vrid: 1
            action:
                type: aws_activate_vip
                device_index: 0
                vip: 10.0.2.100
        """
    )


@pytest.fixture(scope="function")
def aws_endpoint(
    ctr_client: CtrClient,
    aws_endpoint_image: CtrImage,
) -> AWSEndpoint:
    """An AWS endpoint object, providing APIs for getting EC2 state."""
    with AWSEndpoint(ctr_client, aws_endpoint_image) as aws_obj:
        yield aws_obj


@pytest.fixture(scope="function")
def aws_metadata_service(
    ctr_client: CtrClient,
    aws_metadata_service_image: CtrImage,
    aws_endpoint: AWSEndpoint,
) -> Container:
    """The mock AWS metadata service container."""
    logger.info(f"Running mock AWS metadata service container...")
    name = f"aws_metadata__{time.time()}"
    ctr = ctr_client.run(
        aws_metadata_service_image,
        command=["--instance-id", aws_endpoint.ec2_instance_id],
        name=name,
        detach=True,
        init=True,
        networks=["bridge"],
        cap_add=["NET_ADMIN"],
    )

    def ready_condition() -> bool:
        if "Running on http://169.254.169.254:80" in ctr.logs():
            return True
        ctr.reload()
        if not ctr.state.running:
            raise Exception(
                f"AWS metadata service container exited unexpectedly:\n" f"{ctr.logs()}"
            )

    utils.wait_for(
        "AWS metadata service container startup",
        ready_condition,
        10,
        exc_type=CtrException,
    )

    yield ctr

    logger.debug("Removing AWS metadata service container %r", name)
    with contextlib.suppress(CtrException):
        ctr.kill()
    with contextlib.suppress(CtrException):
        ctr.remove(force=True)
