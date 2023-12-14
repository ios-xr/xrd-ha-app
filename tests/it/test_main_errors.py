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

import datetime as dt
import logging
import textwrap

from python_on_whales import Container

from . import utils
from .utils import AWSEndpoint, HAApp, gRPCClient


logger = logging.getLogger(__name__)


def test_general_invalid_config(app: HAApp):
    """Test for general invalid config - app exits."""
    config = "foo: bar"
    with app.run(config, expect_exit=True) as ha_ctr:
        assert ha_ctr.state.exit_code == 2
        ctr_logs = ha_ctr.logs()

    assert ctr_logs.count("ERROR") == 1
    assert "Initialisation error" in ctr_logs
    assert (
        textwrap.dedent(
            """
            pydantic.error_wrappers.ValidationError: 2 validation errors for Config
            groups
              field required (type=value_error.missing)
            foo
              extra fields not permitted (type=value_error.extra)
            """
        )
        in ctr_logs
    )


def test_session_with_multiple_actions_invalid_config(app: HAApp):
    """Test multiple actions configured for a VRRP session - app exits."""
    config = textwrap.dedent(
        f"""\
        groups:
          - xr_interface: HundredGigE0/0/0/1
            vrid: 1
            action:
                type: aws_activate_vip
                device_index: 1
                vip: 10.0.2.101
          - xr_interface: HundredGigE0/0/0/1
            vrid: 1
            action:
                type: aws_activate_vip
                device_index: 2
                vip: 10.0.2.102
        """
    )
    with app.run(config, expect_exit=True) as ha_ctr:
        assert ha_ctr.state.exit_code == 2
        ctr_logs = ha_ctr.logs()

    assert ctr_logs.count("ERROR") == 1
    assert "Initialisation error" in ctr_logs
    assert (
        textwrap.dedent(
            """
            pydantic.error_wrappers.ValidationError: 1 validation error for Config
            groups
              Only one action allowed per VRRP group, got multiple for <xr_interface=HundredGigE0/0/0/1,vrid=1> (type=value_error)
            """
        )
        in ctr_logs
    )


def test_go_active_action_fail(
    app: HAApp,
    default_config: str,
    aws_metadata_service: Container,
    aws_endpoint: AWSEndpoint,
    grpc_client: gRPCClient,
):
    """Test a go-active action failing - error logged, app keeps running."""
    with app.run(default_config) as ha_ctr:
        aws_endpoint.ctr.stop()  # Cause action to fail
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

    assert ctr_logs.count("ERROR") == 1
    assert (
        "Hit exception when performing aws_activate_vip action on "
        "<xr_interface=HundredGigE0/0/0/1,vrid=1>"
    ) in ctr_logs
    assert (
        "ConnectTimeoutError: Connect timeout on endpoint URL" in ctr_logs
        or "EndpointConnectionError: Could not connect to the endpoint URL" in ctr_logs
    )


def test_consistency_check_action_fail(
    app: HAApp,
    aws_metadata_service: Container,
    aws_endpoint: AWSEndpoint,
    grpc_client: gRPCClient,
):
    """
    Test a consistency check action failing - error logged, app keeps running.
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

    def consistency_check_error() -> bool:
        exp_log_msg = "Hit an error trying to perform consistency check"
        return exp_log_msg in ha_ctr.logs(since=log_start_time)

    aws_endpoint_ip_addr = aws_endpoint.ip_address

    with app.run(config) as ha_ctr:
        # First update session state to active, then kill the AWS endpoint
        # container and wait for the consistency check to fire.
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
            aws_endpoint.ctr.stop()
            log_start_time = dt.datetime.now()
            utils.wait_for(
                "consistency check action to fail",
                consistency_check_error,
                timeout=20,
                exc_type=None,
            )
        ha_ctr.reload()
        assert ha_ctr.state.running
        ctr_logs = ha_ctr.logs()

    assert ctr_logs.count("ERROR") > 0
    assert (
        "Hit an error trying to perform consistency check action "
        "'aws_activate_vip' on <xr_interface=HundredGigE0/0/0/1,vrid=1>"
    ) in ctr_logs

    assert (
        "botocore.exceptions.ConnectTimeoutError: Connect timeout on endpoint URL: "
        f'"http://{aws_endpoint_ip_addr}/"'
    ) in ctr_logs
