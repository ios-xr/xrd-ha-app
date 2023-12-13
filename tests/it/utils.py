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

__all__ = (
    "IT_TEST_DIR",
    "ROOT_DIR",
    "AWSEndpoint",
    "gRPCClient",
    "HAApp",
    "build_with_dockerfile",
    "mount_volume",
    "wait_for",
)

import contextlib
import json
import logging
import shlex
import tempfile
import textwrap
import time
from pathlib import Path
from typing import Any, Callable, Generator, Iterable, Mapping, Self

from python_on_whales import Container
from python_on_whales import DockerClient as CtrClient
from python_on_whales import DockerException as CtrException
from python_on_whales import Image as CtrImage
from python_on_whales import Volume as CtrVolume

from ..utils import ROOT_DIR, Json


logger = logging.getLogger(__name__)

IT_TEST_DIR = ROOT_DIR / "tests" / "it"


class gRPCClient:
    """
    A gRPC client for sending gRPC messages.

    This wraps the API provided by the container defined in the 'grpc_client/'
    directory.
    """

    def __init__(self, ctr_client: CtrClient):
        """
        Build the grpc_client container image if required.

        :param ctr_client:
            A python_on_whales container client.
        """
        self._ctr_client = ctr_client
        logger.info(f"Building gRPC client container image...")
        self._ctr_img: CtrImage = ctr_client.legacy_build(
            ROOT_DIR,
            file=IT_TEST_DIR / "grpc_client" / "Dockerfile",
            tags="grpc_client",
        )

    def run(
        self,
        target: str,
        *,
        vrrp_msgs: list[Iterable[Mapping[str, Any]]] | None = None,
        json_msgs: list[Json] | None = None,
        raw_json_msgs: list[Json] | None = None,
        pause: float = 0.1,
        unclean_connection_close: bool = False,
        expect_error: bool = False,
    ) -> str:
        """
        Run the gRPC client, sending specified messages.

        :param target:
            The destination to connect to, e.g. '172.17.0.2:50051'.
        :param vrrp_msgs:
            VRRP telemetry messages to send, e.g.
            {"interface-name": "HundredGigE0/0/0/1",
             "virtual-router-id": 1,
             "vrrp-state": "state-master"}
        :param json_msgs:
            JSON representation of telemetry messages to send, e.g.
            {"encoding_path": "Cisco-IOS-XR-ipv4-vrrp-oper:vrrp/ipv4/virtual-routers/virtual-router",
             "data_gpbkv": [{"fields": []}]}
        :param raw_json_msgs:
            JSON representation of raw MdtDialout messages, e.g.
            {"ReqId": 1, "data": "foo"}
        :param pause:
            How long the client should pause after sending each message.
        :param unclean_connection_close:
            Whether the client should close the connection by raising an error.
        :param expect_error:
            Whether to expect the client container to exit with an error.
        :return:
            The container logs.
        """
        args = ["--target", target, "--pause", str(pause)]
        if unclean_connection_close:
            args.append("--unclean-connection-close")
            expect_error = True
        if vrrp_msgs:
            args.extend(
                [
                    "--vrrp-msgs",
                    *self._vrrp_msgs_to_cli_args(vrrp_msgs),
                ]
            )
        if json_msgs:
            args.extend(
                [
                    "--json-msgs",
                    *[json.dumps(msg) for msg in json_msgs],
                ]
            )
        if raw_json_msgs:
            args.extend(
                [
                    "--raw-json-msgs",
                    *[json.dumps(msg) for msg in raw_json_msgs],
                ]
            )
        logger.debug("Running gRPC client with args: %s", args)
        ctr_name = f"grpc_client__{time.time()}"
        ctr = self._ctr_client.run(
            self._ctr_img,
            command=args,
            name=ctr_name,
            detach=True,
            init=True,
            networks=["bridge"],
        )

        def ready_condition() -> bool:
            ctr.reload()
            return ctr.state.running is False

        try:
            wait_for("gRPC client to exit", ready_condition, 10, exc_type=None)
            if ctr.state.exit_code != 0 and not expect_error:
                logs = ctr.logs()
                raise Exception(
                    f"gRPC client container {ctr_name} exited with {ctr.state.exit_code}"
                )
            elif ctr.state.exit_code == 0 and expect_error:
                logs = ctr.logs()
                raise Exception(
                    f"gRPC client container {ctr_name} unexpectedly exited with success"
                )
            return ctr.logs()
        finally:
            logger.debug("gRPC client logs:\n%s", ctr.logs(timestamps=True))
            logger.debug("Removing gRPC client container %r", ctr_name)
            ctr.remove()

    @contextlib.contextmanager
    def run_indefinite(
        self,
        target: str,
        *,
        vrrp_msgs: list[Iterable[Mapping[str, Any]]] | None = None,
        json_msgs: list[Json] | None = None,
        raw_json_msgs: list[Json] | None = None,
        pause: float = 0.1,
    ) -> Container:
        """
        Context manager to run the gRPC client, sending specified messages and
        keeping the connection open until context manager exits.

        :param target:
            The destination to connect to, e.g. '172.17.0.2:50051'.
        :param vrrp_msgs:
            VRRP telemetry messages to send, e.g.
            {"interface-name": "HundredGigE0/0/0/1",
             "virtual-router-id": 1,
             "vrrp-state": "state-master"}
        :param json_msgs:
            JSON representation of telemetry messages to send, e.g.
            {"encoding_path": "Cisco-IOS-XR-ipv4-vrrp-oper:vrrp/ipv4/virtual-routers/virtual-router",
             "data_gpbkv": [{"fields": []}]}
        :param raw_json_msgs:
            JSON representation of raw MdtDialout messages, e.g.
            {"ReqId": 1, "data": "foo"}
        :param pause:
            How long the client should pause after sending each message.
        :return:
            The running container.
        """
        args = ["--target", target, "--pause", str(pause), "--keep-connection-open"]
        if vrrp_msgs:
            args.extend(
                [
                    "--vrrp-msgs",
                    *self._vrrp_msgs_to_cli_args(vrrp_msgs),
                ]
            )
        if json_msgs:
            args.extend(
                [
                    "--json-msgs",
                    *[json.dumps(msg) for msg in json_msgs],
                ]
            )
        if raw_json_msgs:
            args.extend(
                [
                    "--raw-json-msgs",
                    *[json.dumps(msg) for msg in raw_json_msgs],
                ]
            )
        logger.debug("Running gRPC client with args: %s", args)
        ctr_name = f"grpc_client__{time.time()}"
        ctr = self._ctr_client.run(
            self._ctr_img,
            command=args,
            name=ctr_name,
            detach=True,
            init=True,
            networks=["bridge"],
        )

        def ready_condition() -> bool:
            return "Messages sent, keeping connection open" in ctr.logs()

        try:
            wait_for("gRPC client to send messages", ready_condition, 20, exc_type=None)
            ctr.reload()
            if not ctr.state.running:
                raise Exception(
                    f"gRPC client container {ctr_name} exited unexpectedly with {ctr.state.exit_code}"
                )
            yield ctr
        finally:
            logger.debug("gRPC client logs:\n%s", ctr.logs(timestamps=True))
            logger.debug("Removing gRPC client container %r", ctr_name)
            # Note: It seems to be unpredictable whether the gRPC server will
            #       receive a clean connection close or an RpcError.
            with contextlib.suppress(CtrException):
                ctr.kill()
            with contextlib.suppress(CtrException):
                ctr.remove(force=True)

    def _vrrp_msgs_to_cli_args(
        self, vrrp_msgs: Iterable[Iterable[Mapping[str, Any]]]
    ) -> Iterable[str]:
        """Convert passed VRRP messages to grpc_client CLI form."""
        return (
            ";".join(
                ",".join(f"{k}={v}" for k, v in session.items()) for session in msg
            )
            for msg in vrrp_msgs
        )


class AWSEndpoint:
    """
    Context manager for starting the mock AWS endpoint container.

    This exposes the files exported by the container defined in the
    'aws_endpoint/' directory, and also provides APIs to fetch EC2 state.
    """

    def __init__(self, ctr_client: CtrClient, image: CtrImage):
        """
        :param ctr_client:
            A python_on_whales container client.
        :param image:
            The container image to run.
        """
        self._ctr_client = ctr_client
        self._img = image
        self.ctr: Container | None = None
        self._ec2_instance_id: str | None = None
        self._eni_id: str | None = None
        self._route_table_id: str | None = None
        self._rtb_orig_eni_id: str | None = None
        self._rtb_target_eni_id: str | None = None

    def __enter__(self) -> Self:
        self.ctr = self._run_ctr()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        logger.debug("Removing AWS endpoint container %r", self.ctr.name)
        with contextlib.suppress(CtrException):
            self.ctr.kill()
        with contextlib.suppress(CtrException):
            self.ctr.remove(force=True)
        self._ec2_instance_id = None
        self._eni_id = None
        self._route_table_id = None
        self._rtb_orig_eni_id = None
        self._rtb_target_eni_id = None

    @property
    def ip_address(self) -> str:
        """IP address of the container."""
        return self.ctr.network_settings.ip_address

    @property
    def ec2_instance_id(self) -> str:
        """EC2 instance ID created in the mock endpoint startup script."""
        if not self._ec2_instance_id:
            self._ec2_instance_id = self.ctr.execute(["cat", "/instance-id"])
            logger.debug("Got EC2 instance ID %r", self._ec2_instance_id)
        return self._ec2_instance_id

    @property
    def eni_id(self) -> str:
        """
        ENI ID used for testing the aws_assign_vip action.

        Set up in the mock endpoint startup script.
        """
        if not self._eni_id:
            self._eni_id = self.ctr.execute(["cat", "/eni-id"])
            logger.debug("Got instance's attached ENI ID %r", self._eni_id)
        return self._eni_id

    @property
    def route_table_id(self) -> str:
        """
        Route table ID used for testing the aws_update_route_table action, set
        up in the mock endpoint startup script.
        """
        if not self._route_table_id:
            self._route_table_id = self.ctr.execute(["cat", "/route-table-id"])
            logger.debug("Got route table ID %r", self._route_table_id)
        return self._route_table_id

    @property
    def rtb_orig_eni_id(self) -> str:
        """
        ENI ID used for testing the aws_update_route_table action, which
        the route is initially associated with.

        Set up in the mock endpoint startup script.
        """
        if not self._rtb_orig_eni_id:
            self._rtb_orig_eni_id = self.ctr.execute(["cat", "/rtb-orig-eni-id"])
            logger.debug("Got original route table ENI ID %r", self._rtb_orig_eni_id)
        return self._rtb_orig_eni_id

    @property
    def rtb_target_eni_id(self) -> str:
        """
        ENI ID used for testing the aws_update_route_table action, which
        the route is moved to be associated with.

        Set up in the mock endpoint startup script.
        """
        if not self._rtb_target_eni_id:
            self._rtb_target_eni_id = self.ctr.execute(["cat", "/rtb-target-eni-id"])
            logger.debug("Got target route table ENI ID %r", self._rtb_target_eni_id)
        return self._rtb_target_eni_id

    def run_boto3(self, statement: str) -> Json:
        """
        Run a boto3 client command, connecting to the moto server.

        This may use 'client', 'resource', or 'instance' (see inline script).
        Examples:
        - 'client.describe_network_interfaces()["NetworkInterfaces"]'
        - 'client.replace_route(RouteTableId="rtb-123", ...)'
        - 'resource.NetworkInterface(eni).unassign_private_ip_addresses(
               PrivateIpAddresses=["10.0.2.100"])'

        :param statement:
            The boto3 statement to execute, see examples above.
        :return:
            JSON output from the command.
        """
        logger.debug("Running boto3 command: %s", statement)
        script = textwrap.dedent(
            f"""
            import json
            from pathlib import Path

            import boto3

            client = boto3.client(
                "ec2",
                region_name="us-east-1",
                endpoint_url="http://localhost",
                aws_access_key_id="key",
                aws_secret_access_key="secret-key",
            )
            resource = boto3.resource(
                "ec2",
                region_name="us-east-1",
                endpoint_url="http://localhost",
                aws_access_key_id="key",
                aws_secret_access_key="secret-key",
            )
            instance = resource.Instance(Path("/instance-id").read_text())

            output = {statement}
            print(json.dumps(output, default=str))
            """
        )
        output = self.ctr.execute(command=["python3", "-c", script])
        return json.loads(output)

    def get_eni_private_ip_addrs(
        self, *, device_index: int
    ) -> list[Mapping[str, Json]]:
        """Get the IPv4 addresses associated with the specified device."""
        network_intfs = self.run_boto3(
            "client.describe_network_interfaces()['NetworkInterfaces']"
        )
        for intf in network_intfs:
            if (
                "Attachment" in intf
                and intf["Attachment"]["DeviceIndex"] == device_index
                and intf["Attachment"]["InstanceId"] == self.ec2_instance_id
            ):
                return intf["PrivateIpAddresses"]
        raise ValueError("Network interface not found")

    def get_route_table_routes(self) -> list[Mapping[str, Json]]:
        """Get the IPv4 routes associated with the default route table."""
        route_tables = self.run_boto3(
            f"client.describe_route_tables(RouteTableIds=['{self.route_table_id}'])['RouteTables']"
        )
        assert len(route_tables) == 1
        return route_tables[0]["Routes"]

    def _run_ctr(self) -> Container:
        """Run the mock endpoint container."""

        def ready_condition() -> bool:
            if "Initialisation complete" in ctr.logs():
                return True
            ctr.reload()
            if not ctr.state.running:
                raise Exception(
                    f"AWS endpoint container exited unexpectedly:\n{ctr.logs()}"
                )

        logger.info(f"Running mock AWS endpoint container...")
        name = f"aws_endpoint__{time.time()}"
        ctr = self._ctr_client.run(
            self._img,
            name=name,
            detach=True,
            init=True,
            networks=["bridge"],
        )
        try:
            wait_for(
                "AWS endpoint container startup",
                ready_condition,
                5,
                exc_type=CtrException,
            )
        except Exception:
            with contextlib.suppress(CtrException):
                ctr.kill()
            with contextlib.suppress(CtrException):
                ctr.remove(force=True)
            raise
        return ctr


class HAApp:
    """
    Representation of an HA app.

    Use the 'run()' context manager to start the container.
    """

    def __init__(
        self,
        ctr_client: CtrClient,
        image: CtrImage,
        config_vol: CtrVolume,
        config_vol_ctr: Container,
        coverage_vol: CtrVolume | None = None,
    ):
        """
        :param ctr_client:
            A python_on_whales container client.
        :param image:
            The HA container image to run.
        :param config_vol:
            A volume containing HA app config.
        :param config_vol_ctr:
            A container with the config volume mounted.
        :param coverage_vol:
            Optional volume to mount read-write at /data for collecting code
            coverage.
        """
        self._ctr_client = ctr_client
        self._img = image
        self._config_vol = config_vol
        self._config_vol_ctr = config_vol_ctr
        self._coverage_vol = coverage_vol
        self._collect_coverage = bool(self._coverage_vol)

    @contextlib.contextmanager
    def run(
        self,
        config: str | None,
        *,
        command: list[str] | None = None,
        timeout: float = 5,
        expect_exit: bool = False,
        aws_metadata_route: bool = True,
    ) -> Generator[Container, None, None]:
        """
        Context manager to start an instance of the HA app.

        :param config:
            The yaml config to run the HA app with.
        :param timeout:
            How long to wait for the app to be ready.
        :param expect_exit:
            Whether to expect (and wait for) the container to exit.
        :param aws_metadata_route:
            Whether to add a route to the AWS metadata service.
        """

        def is_listening() -> bool:
            if "Listening on port" in ctr.logs():
                return True
            ctr.reload()
            if not ctr.state.running:
                raise Exception(
                    f"HA container exited unexpectedly:\n{ctr.logs(timestamps=True)}"
                )

        def has_exited() -> bool:
            ctr.reload()
            return not ctr.state.running

        volumes = []
        if config is not None:
            self._config_vol_ctr.execute(
                ["sh", "-c", f"echo {shlex.quote(config)} > /etc/ha_app/config.yaml"]
            )
            volumes.append((self._config_vol, "/etc/ha_app/", "ro"))
        if self._coverage_vol:
            volumes.append((self._coverage_vol, "/data/", "rw"))
        name = f"ha_app__{time.time()}"
        logger.info("Starting HA container %s", name)
        ctr = self._ctr_client.run(
            self._img,
            command=command or [],
            name=name,
            detach=True,
            volumes=volumes,
            networks=["bridge"],
            cap_add=["NET_ADMIN"],
            envs={
                "COLLECT_COVERAGE": str(int(self._collect_coverage)),
                "ADD_AWS_METADATA_ROUTE": str(int(aws_metadata_route)),
            },
        )
        try:
            wait_for(
                "HA container exit" if expect_exit else "HA container startup",
                condition=has_exited if expect_exit else is_listening,
                timeout=timeout,
                exc_type=CtrException,
            )
            assert ctr.network_settings.ip_address is not None
            yield ctr
        finally:
            logger.debug("HA container logs:\n%s", ctr.logs(timestamps=True))
            logger.debug("Removing HA container %r", name)
            if not expect_exit:
                with contextlib.suppress(CtrException):
                    ctr.kill("SIGTERM")
            ctr.remove(force=True)


def build_with_dockerfile(
    ctr_client: CtrClient,
    dockerfile: str,
    *,
    tags: str | Iterable[str] = (),
    build_root: Path | None = None,
) -> CtrImage:
    """Build a container image using a dockerfile in string form."""
    with tempfile.TemporaryDirectory(prefix="ctr-build-root-") as tmpdir:
        dockerfile_path = Path(tmpdir) / "Dockerfile"
        dockerfile_path.write_text(dockerfile)
        if not build_root:
            build_root = tmpdir
        return ctr_client.legacy_build(build_root, file=dockerfile_path, tags=tags)


@contextlib.contextmanager
def mount_volume(
    ctr_client: CtrClient,
    volume: CtrVolume,
    path: str,
    *,
    read_only: bool = False,
    ctr_image: CtrImage | str = "alpine",
) -> Generator[Container, None, None]:
    """
    Context manager for mounting a volume in a container.

    :param ctr_client:
        A python_on_whales container client.
    :param volume:
        The container volume to mount.
    :param path:
        The path to mount the volume at.
    :param read_only:
        Whether to mount the volume read-only.
    :param ctr_image:
        The container image to use.
    """
    ctr = ctr_client.run(
        ctr_image,
        name=f"mount_volume__{time.time()}",
        tty=True,
        detach=True,
        remove=True,
        entrypoint="sh",
        volumes=[(volume, path, "ro" if read_only else "rw")],
    )
    try:
        yield ctr
    finally:
        ctr.remove(force=True)


def wait_for(
    description: str,
    condition: Callable[[], bool],
    timeout: float,
    interval: float = 0.2,
    *,
    exc_type: type[Exception] | None = Exception,
) -> None:
    """
    Wait for a condition to complete within the given timeout.

    The given condition function should return True on success, return False or
    raise an exception of the type given in 'exc_type' for retry, or raise
    another exception type on unexpected error.

    :param description:
        Description of what's being waited for.
    :param condition:
        The callable representing the condition being waited for.
    :param timeout:
        The retry timeout in seconds.
    :param interval:
        The retry interval in seconds.
    :param exc_type:
        The exception type to catch from calling the condition function, or
        None to not catch exceptions.
    """
    logger.info("Waiting up to %s seconds for %s", timeout, description)
    exception: exc_type | None = None
    end_time = time.monotonic() + timeout
    ready = False
    while True:
        if exc_type:
            try:
                ready = condition()
            except exc_type as e:
                exception = e
        else:
            ready = condition()
        if ready:
            logger.debug("Ready condition met")
            return
        if time.monotonic() >= end_time:
            break
        logger.debug("Trying again in %s seconds...", interval)
        time.sleep(interval)

    msg = f"Timed out after {timeout} seconds waiting for {description}"
    if exception:
        raise TimeoutError(msg) from exception
    else:
        raise TimeoutError(msg)
