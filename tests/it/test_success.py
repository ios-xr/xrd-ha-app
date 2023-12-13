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
import textwrap

from python_on_whales import Container

from . import utils
from .utils import AWSEndpoint, HAApp, gRPCClient


logger = logging.getLogger(__name__)


def test_basic_telem(
    app: HAApp,
    minimal_config: str,
    grpc_client: gRPCClient,
):
    """Test a basic handling of a telemetry message."""
    with app.run(minimal_config) as ha_ctr:
        grpc_client.run(
            f"{ha_ctr.network_settings.ip_address}:50051",
            vrrp_msgs=[
                [
                    {
                        "interface-name": "HundredGigE0/0/0/1",
                        "virtual-router-id": 1,
                        "vrrp-state": "state-master",
                    },
                ],
            ],
        )
        ha_ctr.reload()
        assert ha_ctr.state.running
        ctr_logs = ha_ctr.logs()

    assert "ERROR" not in ctr_logs
    assert ctr_logs.count("WARN") == 1  # No actions configured
    assert "Connection established with gRPC peer" in ctr_logs
    assert "Connection closed by gRPC peer" in ctr_logs


def test_aws_assign_vip(
    app: HAApp,
    aws_metadata_service: Container,
    aws_endpoint: AWSEndpoint,
    grpc_client: gRPCClient,
):
    """Test success of a 'aws_assign_vip' action."""
    config = textwrap.dedent(
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
    with app.run(config) as ha_ctr:
        grpc_client.run(
            f"{ha_ctr.network_settings.ip_address}:50051",
            vrrp_msgs=[
                [
                    {
                        "interface-name": "HundredGigE0/0/0/1",
                        "virtual-router-id": 1,
                        "vrrp-state": "state-master",
                    },
                ],
            ],
        )
        ha_ctr.reload()
        assert ha_ctr.state.running
        ctr_logs = ha_ctr.logs()

    assert "ERROR" not in ctr_logs
    assert "WARN" not in ctr_logs
    assert (
        "Go active on <xr_interface=HundredGigE0/0/0/1,vrid=1> with aws_activate_vip"
    ) in ctr_logs
    assert (
        f"Assigning private IPv4 address 10.0.2.100 to device ID 0 ({aws_endpoint.eni_id})"
        in ctr_logs
    )

    # Check VIP assigned via boto3 client API.
    private_ip_addrs = aws_endpoint.get_eni_private_ip_addrs(device_index=0)
    assert {"Primary": False, "PrivateIpAddress": "10.0.2.100"} in private_ip_addrs


def test_aws_update_route_table(
    app: HAApp,
    aws_metadata_service: Container,
    aws_endpoint: AWSEndpoint,
    grpc_client: gRPCClient,
):
    """Test success of a 'aws_update_route_table' action."""
    config = textwrap.dedent(
        f"""\
        global:
            port: 50051
            aws:
                ec2_private_endpoint_url: "http://{aws_endpoint.ip_address}"
        groups:
          - xr_interface: HundredGigE0/0/0/2
            vrid: 2
            action:
                type: aws_update_route_table
                route_table_id: {aws_endpoint.route_table_id}
                destination: 10.0.10.0/24
                target_network_interface: {aws_endpoint.rtb_target_eni_id}
        """
    )
    with app.run(config) as ha_ctr:
        grpc_client.run(
            f"{ha_ctr.network_settings.ip_address}:50051",
            vrrp_msgs=[
                [
                    {
                        "interface-name": "HundredGigE0/0/0/2",
                        "virtual-router-id": 2,
                        "vrrp-state": "state-master",
                    },
                ],
            ],
        )
        ha_ctr.reload()
        assert ha_ctr.state.running
        ctr_logs = ha_ctr.logs()

    assert "ERROR" not in ctr_logs
    assert "WARN" not in ctr_logs
    assert (
        "Go active on <xr_interface=HundredGigE0/0/0/2,vrid=2> with aws_update_route_table"
    ) in ctr_logs
    assert (
        f"Updating route table {aws_endpoint.route_table_id} with destination "
        f"10.0.10.0/24, target {aws_endpoint.rtb_target_eni_id}"
    ) in ctr_logs
    assert (
        f"Creating route in route table {aws_endpoint.route_table_id} with "
        f"destination 10.0.10.0/24, target {aws_endpoint.rtb_target_eni_id}"
    ) in ctr_logs

    # Check route is updated via boto3 client API.
    routes = aws_endpoint.get_route_table_routes()
    assert {
        "DestinationCidrBlock": "10.0.10.0/24",
        "NetworkInterfaceId": aws_endpoint.rtb_target_eni_id,
        "Origin": "CreateRoute",
        "State": "active",
    } in routes


def test_aws_update_route_table_route_exists(
    app: HAApp,
    aws_metadata_service: Container,
    aws_endpoint: AWSEndpoint,
    grpc_client: gRPCClient,
):
    """
    Test 'aws_update_route_table' action where the route already exists, so
    ReplaceRoute should succeed and CreateRoute not be used.
    """
    config = textwrap.dedent(
        f"""\
        global:
            port: 50051
            aws:
                ec2_private_endpoint_url: "http://{aws_endpoint.ip_address}"
        groups:
          - xr_interface: HundredGigE0/0/0/2
            vrid: 2
            action:
                type: aws_update_route_table
                route_table_id: {aws_endpoint.route_table_id}
                destination: 10.0.10.0/24
                target_network_interface: {aws_endpoint.rtb_target_eni_id}
        """
    )
    aws_endpoint.run_boto3(
        # fmt: off
        "client.create_route("
            f"RouteTableId='{aws_endpoint.route_table_id}',"
            "DestinationCidrBlock='10.0.10.0/24',"
            f"NetworkInterfaceId='{aws_endpoint.rtb_orig_eni_id}',"
        ")"
        # fmt: on
    )
    with app.run(config) as ha_ctr:
        grpc_client.run(
            f"{ha_ctr.network_settings.ip_address}:50051",
            vrrp_msgs=[
                [
                    {
                        "interface-name": "HundredGigE0/0/0/2",
                        "virtual-router-id": 2,
                        "vrrp-state": "state-master",
                    },
                ],
            ],
        )
        ha_ctr.reload()
        assert ha_ctr.state.running
        ctr_logs = ha_ctr.logs()

    assert "ERROR" not in ctr_logs
    assert "WARN" not in ctr_logs
    assert (
        "Go active on <xr_interface=HundredGigE0/0/0/2,vrid=2> with aws_update_route_table"
    ) in ctr_logs
    assert (
        f"Updating route table {aws_endpoint.route_table_id} with destination "
        f"10.0.10.0/24, target {aws_endpoint.rtb_target_eni_id}"
    ) in ctr_logs
    assert "Creating route table" not in ctr_logs

    # Check route is updated via boto3 client API.
    routes = aws_endpoint.get_route_table_routes()
    assert {
        "DestinationCidrBlock": "10.0.10.0/24",
        "NetworkInterfaceId": aws_endpoint.rtb_target_eni_id,
        "Origin": "CreateRoute",
        "State": "active",
    } in routes


def test_multiple_actions(
    app: HAApp,
    aws_metadata_service: Container,
    aws_endpoint: AWSEndpoint,
    grpc_client: gRPCClient,
):
    """Test success of a multiple actions in parallel."""
    config = textwrap.dedent(
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
          - xr_interface: HundredGigE0/0/0/2
            vrid: 2
            action:
                type: aws_update_route_table
                route_table_id: {aws_endpoint.route_table_id}
                destination: 10.0.10.0/24
                target_network_interface: {aws_endpoint.rtb_target_eni_id}
        """
    )
    with app.run(config) as ha_ctr:
        grpc_client.run(
            f"{ha_ctr.network_settings.ip_address}:50051",
            vrrp_msgs=[
                [
                    {
                        "interface-name": "HundredGigE0/0/0/1",
                        "virtual-router-id": 1,
                        "vrrp-state": "state-init",
                    },
                    {
                        "interface-name": "HundredGigE0/0/0/2",
                        "virtual-router-id": 2,
                        "vrrp-state": "state-init",
                    },
                ],
                [
                    {
                        "interface-name": "HundredGigE0/0/0/1",
                        "virtual-router-id": 1,
                        "vrrp-state": "state-master",
                    },
                    {
                        "interface-name": "HundredGigE0/0/0/2",
                        "virtual-router-id": 2,
                        "vrrp-state": "state-master",
                    },
                ],
                [
                    {
                        "interface-name": "HundredGigE0/0/0/1",
                        "virtual-router-id": 1,
                        "vrrp-state": "state-master",
                    },
                    {
                        "interface-name": "HundredGigE0/0/0/2",
                        "virtual-router-id": 2,
                        "vrrp-state": "state-master",
                    },
                ],
            ],
        )
        ha_ctr.reload()
        assert ha_ctr.state.running
        ctr_logs = ha_ctr.logs()

    assert "ERROR" not in ctr_logs
    assert "WARN" not in ctr_logs
    assert (
        "Go active on <xr_interface=HundredGigE0/0/0/1,vrid=1> with aws_activate_vip"
    ) in ctr_logs
    assert (
        f"Assigning private IPv4 address 10.0.2.100 to device ID 0 ({aws_endpoint.eni_id})"
        in ctr_logs
    )
    assert (
        "Go active on <xr_interface=HundredGigE0/0/0/2,vrid=2> with aws_update_route_table"
    ) in ctr_logs
    assert (
        f"Updating route table {aws_endpoint.route_table_id} with destination "
        f"10.0.10.0/24, target {aws_endpoint.rtb_target_eni_id}"
    ) in ctr_logs

    # Check VIP assigned via boto3 client API.
    private_ip_addrs = aws_endpoint.get_eni_private_ip_addrs(device_index=0)
    assert {"Primary": False, "PrivateIpAddress": "10.0.2.100"} in private_ip_addrs

    # Check route is updated via boto3 client API.
    routes = aws_endpoint.get_route_table_routes()
    assert {
        "DestinationCidrBlock": "10.0.10.0/24",
        "NetworkInterfaceId": aws_endpoint.rtb_target_eni_id,
        "Origin": "CreateRoute",
        "State": "active",
    } in routes


def test_no_actions_configured(app: HAApp):
    """Test handling of no actions being configured - app doesn't exit."""
    config = textwrap.dedent(
        """\
        groups: []
        """
    )
    with app.run(config) as ha_ctr:
        ha_ctr.reload()
        assert ha_ctr.state.running
        ctr_logs = ha_ctr.logs()

    assert "ERROR" not in ctr_logs
    assert ctr_logs.count("WARN") == 1
    assert "No registered actions found" in ctr_logs


def test_ctrl_c_exit(
    app: HAApp,
    minimal_config: str,
    grpc_client: gRPCClient,
):
    """Test handling of Ctrl+C exit, with gRPC connection active."""

    def has_exited() -> bool:
        ha_ctr.reload()
        return not ha_ctr.state.running

    with app.run(minimal_config) as ha_ctr:
        with grpc_client.run_indefinite(f"{ha_ctr.network_settings.ip_address}:50051"):
            ha_ctr.kill("SIGINT")
            utils.wait_for(
                "HA container exit", condition=has_exited, timeout=5, exc_type=None
            )
        assert ha_ctr.state.exit_code == 130
        ctr_logs = ha_ctr.logs()

    assert "ERROR" not in ctr_logs
    assert ctr_logs.count("WARN") == 1
    assert "Exiting on Ctrl+C" in ctr_logs


def test_app_version(app: HAApp, app_version: str):
    """Test handling of exit due to Ctrl+C."""
    with app.run(None, command=["--version"], expect_exit=True) as ha_ctr:
        ctr_logs = ha_ctr.logs()
        assert ha_ctr.state.exit_code == 0

    assert ctr_logs.strip() == app_version


def test_ignore_unregistered_session(
    app: HAApp,
    default_config: str,
    aws_metadata_service: Container,
    grpc_client: gRPCClient,
):
    """Test handling of VRRP notification for unregistered session."""
    with app.run(default_config) as ha_ctr:
        grpc_client.run(
            f"{ha_ctr.network_settings.ip_address}:50051",
            vrrp_msgs=[
                [
                    {
                        "interface-name": "HundredGigE0/0/0/5",
                        "virtual-router-id": 20,
                        "vrrp-state": "state-master",
                    }
                ],
            ],
        )
        ha_ctr.reload()
        assert ha_ctr.state.running
        ctr_logs = ha_ctr.logs()

    assert "ERROR" not in ctr_logs
    assert "WARN" not in ctr_logs
    assert (
        "Ignoring event for unregistered session "
        "<xr_interface=HundredGigE0/0/0/5,vrid=20>"
    ) in ctr_logs


def test_consistency_check_aws_assign_vip(
    app: HAApp,
    aws_metadata_service: Container,
    aws_endpoint: AWSEndpoint,
    grpc_client: gRPCClient,
):
    """
    Test consistency check successfully triggering 'aws_assign_vip' action.
    """
    config = textwrap.dedent(
        f"""\
        global:
            port: 50051
            consistency_check_interval_seconds: 1
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

    def reconverged() -> bool:
        private_ip_addrs = aws_endpoint.get_eni_private_ip_addrs(device_index=0)
        return {"Primary": False, "PrivateIpAddress": "10.0.2.100"} in private_ip_addrs

    with app.run(config) as ha_ctr:
        # First update session state to active, then detach the IP address and
        # wait for the consistency check to reassign it.
        with grpc_client.run_indefinite(
            f"{ha_ctr.network_settings.ip_address}:50051",
            vrrp_msgs=[
                [
                    {
                        "interface-name": "HundredGigE0/0/0/1",
                        "virtual-router-id": 1,
                        "vrrp-state": "state-master",
                    },
                ],
            ],
        ):
            aws_endpoint.run_boto3(
                # fmt: off
                f"resource.NetworkInterface({aws_endpoint.eni_id!r}).unassign_private_ip_addresses("
                    "PrivateIpAddresses=['10.0.2.100']"
                ")"
                # fmt: on
            )
            utils.wait_for(
                "consistency check to trigger 'aws_activate_vip' action",
                reconverged,
                timeout=10,
                exc_type=None,
            )
        ha_ctr.reload()
        assert ha_ctr.state.running
        ctr_logs = ha_ctr.logs()

    assert "ERROR" not in ctr_logs
    assert "WARN" not in ctr_logs
    assert (
        "Performing consistency check on <xr_interface=HundredGigE0/0/0/1,vrid=1>"
    ) in ctr_logs
    assert "IPv4 address 10.0.2.100 not assigned at precheck" in ctr_logs
    assert "Assigning private IPv4 address 10.0.2.100 to device ID 0" in ctr_logs


def test_consistency_check_aws_update_route_table(
    app: HAApp,
    aws_metadata_service: Container,
    aws_endpoint: AWSEndpoint,
    grpc_client: gRPCClient,
):
    """
    Test consistency check successfully triggering 'aws_update_route_table'
    action.
    """
    config = textwrap.dedent(
        f"""\
        global:
            port: 50051
            consistency_check_interval_seconds: 1
            aws:
                ec2_private_endpoint_url: "http://{aws_endpoint.ip_address}"
        groups:
          - xr_interface: HundredGigE0/0/0/2
            vrid: 2
            action:
                type: aws_update_route_table
                route_table_id: {aws_endpoint.route_table_id}
                destination: 10.0.10.0/24
                target_network_interface: {aws_endpoint.rtb_target_eni_id}
        """
    )

    def reconverged() -> bool:
        routes = aws_endpoint.get_route_table_routes()
        return {
            "DestinationCidrBlock": "10.0.10.0/24",
            "NetworkInterfaceId": aws_endpoint.rtb_target_eni_id,
            "Origin": "CreateRoute",
            "State": "active",
        } in routes

    with app.run(config) as ha_ctr:
        # First update session state to active, then remove the route and
        # wait for the consistency check to reassign it.
        with grpc_client.run_indefinite(
            f"{ha_ctr.network_settings.ip_address}:50051",
            vrrp_msgs=[
                [
                    {
                        "interface-name": "HundredGigE0/0/0/2",
                        "virtual-router-id": 2,
                        "vrrp-state": "state-master",
                    },
                ],
            ],
        ):
            aws_endpoint.run_boto3(
                # fmt: off
                "client.replace_route("
                    f"RouteTableId={aws_endpoint.route_table_id!r}, "
                    "DestinationCidrBlock='10.0.10.0/24', "
                    f"NetworkInterfaceId={aws_endpoint.rtb_orig_eni_id!r}"
                ")",
                # fmt: on
            )
            utils.wait_for(
                "consistency check to trigger 'aws_update_route_table' action",
                reconverged,
                timeout=10,
                exc_type=None,
            )
        ha_ctr.reload()
        assert ha_ctr.state.running
        ctr_logs = ha_ctr.logs()

    assert "ERROR" not in ctr_logs
    assert "WARN" not in ctr_logs
    assert (
        "Performing consistency check on <xr_interface=HundredGigE0/0/0/2,vrid=2>"
    ) in ctr_logs
    assert (
        f"Route destination 10.0.10.0/24 via {aws_endpoint.rtb_target_eni_id} "
        f"not present in route table {aws_endpoint.route_table_id} at precheck"
    ) in ctr_logs
    assert (
        f"Updating route table {aws_endpoint.route_table_id} with destination "
        f"10.0.10.0/24, target {aws_endpoint.rtb_target_eni_id}"
    ) in ctr_logs
