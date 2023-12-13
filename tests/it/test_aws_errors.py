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

from .utils import AWSEndpoint, HAApp


logger = logging.getLogger(__name__)


def test_invalid_device_index(
    app: HAApp,
    aws_metadata_service: Container,
    aws_endpoint: AWSEndpoint,
):
    """Test for invalid device ID in action config - app exits."""
    # Config validation will fail due to incorrect device ID.
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
                device_index: 123
                vip: 10.0.2.100
        """
    )
    with app.run(config, expect_exit=True) as ha_ctr:
        assert ha_ctr.state.exit_code == 2
        ctr_logs = ha_ctr.logs()

    assert ctr_logs.count("ERROR") == 1
    assert "Initialisation error" in ctr_logs
    assert ctr_logs.splitlines()[-1] == (
        f"InitError: Error validating config: EC2 instance {aws_endpoint.ec2_instance_id} "
        "device index '123' not found"
    )


def test_invalid_route_table(
    app: HAApp,
    aws_metadata_service: Container,
    aws_endpoint: AWSEndpoint,
):
    """Test for invalid route table ID in action config - app exits."""
    # Config validation will fail due to incorrect route table ID.
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
                type: aws_update_route_table
                route_table_id: foo
                destination: 10.0.10.0/24
                target_network_interface: {aws_endpoint.rtb_target_eni_id}
        """
    )
    with app.run(config, expect_exit=True) as ha_ctr:
        assert ha_ctr.state.exit_code == 2
        ctr_logs = ha_ctr.logs()

    assert ctr_logs.count("ERROR") == 1
    assert "Initialisation error" in ctr_logs
    assert ctr_logs.splitlines()[-1] == (
        f"InitError: Error validating config: Route table 'foo' not found"
    )


def test_invalid_eni_for_route_table(
    app: HAApp,
    aws_metadata_service: Container,
    aws_endpoint: AWSEndpoint,
):
    """Test for invalid route in action config - app exits."""
    # Config validation will fail due to specified ENI not existing.
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
                type: aws_update_route_table
                route_table_id: {aws_endpoint.route_table_id}
                destination: 10.0.10.0/24
                target_network_interface: foo
        """
    )
    with app.run(config, expect_exit=True) as ha_ctr:
        assert ha_ctr.state.exit_code == 2
        ctr_logs = ha_ctr.logs()

    assert ctr_logs.count("ERROR") == 1
    assert "Initialisation error" in ctr_logs
    assert ctr_logs.splitlines()[-1] == (
        f"InitError: Error validating config: Network interface 'foo' not found"
    )


def test_aws_metadata_error(
    app: HAApp,
    default_config: str,
):
    """Test hitting an error when trying to connect to AWS metadata service."""
    # AWS metadata service not in fixture dependencies, so shouldn't be running.
    # However, we should also make sure the HA app has no route to the IP
    # address (via aws_metadata_route=False) since there could be another
    # instance of the metadata service running on the bridge.
    with app.run(
        default_config, expect_exit=True, timeout=20, aws_metadata_route=False
    ) as ha_ctr:
        assert ha_ctr.state.exit_code == 2
        ctr_logs = ha_ctr.logs()

    assert ctr_logs.count("ERROR") > 0
    assert "Unable to get EC2 token for use with IMDSv2" in ctr_logs
    assert "Initialisation error" in ctr_logs


def test_invalid_aws_endpoint_domain(
    app: HAApp,
    aws_metadata_service: Container,
):
    """
    Test hitting an error trying to connect to an invalid EC2 endpoint domain.
    """
    config = textwrap.dedent(
        f"""\
        global:
            aws:
                ec2_private_endpoint_url: "http://invalid"
        groups:
          - xr_interface: HundredGigE0/0/0/1
            vrid: 1
            action:
                type: aws_activate_vip
                device_index: 0
                vip: 10.0.2.100
        """
    )
    with app.run(config, expect_exit=True, timeout=20) as ha_ctr:
        assert ha_ctr.state.exit_code == 2
        ctr_logs = ha_ctr.logs()

    assert ctr_logs.count("ERROR") == 1
    assert "Initialisation error" in ctr_logs
    assert 'Could not connect to the endpoint URL: "http://invalid/"' in ctr_logs


def test_invalid_aws_endpoint_ip_addr(
    app: HAApp,
    aws_metadata_service: Container,
):
    """
    Test hitting an error trying to connect to an invalid EC2 endpoint IP
    address.
    """
    config = textwrap.dedent(
        f"""\
        global:
            aws:
                ec2_private_endpoint_url: "http://192.0.2.1"
        groups:
          - xr_interface: HundredGigE0/0/0/1
            vrid: 1
            action:
                type: aws_activate_vip
                device_index: 0
                vip: 10.0.2.100
        """
    )
    with app.run(config, expect_exit=True, timeout=20) as ha_ctr:
        assert ha_ctr.state.exit_code == 2
        ctr_logs = ha_ctr.logs()

    assert ctr_logs.count("ERROR") == 1
    assert "Initialisation error" in ctr_logs
    assert ctr_logs.splitlines()[-1] == (
        "InitError: Error validating config: Connect timeout on endpoint URL: "
        '"http://192.0.2.1/"'
    )
