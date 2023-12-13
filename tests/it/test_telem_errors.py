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

import json
import logging

from .utils import HAApp, gRPCClient


logger = logging.getLogger(__name__)


def test_unexpected_telem_msg_encoding_paths(
    app: HAApp,
    minimal_config: str,
    grpc_client: gRPCClient,
):
    """Test handling of telemetry messages with unexpected oper paths."""
    with app.run(minimal_config) as ha_ctr:
        grpc_client.run(
            f"{ha_ctr.network_settings.ip_address}:50051",
            json_msgs=[
                # Only the first of a given encoding path results in a warning.
                dict(
                    encoding_path="Cisco-IOS-XR-infra-syslog-oper:syslog/messages",
                ),
                dict(
                    encoding_path="Cisco-IOS-XR-infra-syslog-oper:syslog/messages",
                ),
                dict(
                    encoding_path="Cisco-IOS-XR-infra-syslog-oper:syslog/messages",
                ),
                # The encoding path is assumed to terminate at 'virtual-router'.
                dict(
                    encoding_path="Cisco-IOS-XR-ipv4-vrrp-oper:vrrp/ipv4/virtual-routers/virtual-router/vrrp-state",
                ),
                # The encoding path is assumed not to include filters.
                dict(
                    encoding_path="Cisco-IOS-XR-ipv4-vrrp-oper:vrrp/ipv4/virtual-routers/virtual-router[virtual-router-id=1]",
                ),
            ],
        )
        ha_ctr.reload()
        assert ha_ctr.state.running
        ctr_logs = ha_ctr.logs()

    assert ctr_logs.count("ERROR") == 0
    assert (
        ctr_logs.count(
            "Received unexpected telemetry message with path "
            "'Cisco-IOS-XR-infra-syslog-oper:syslog/messages'"
        )
        == 1
    )
    assert (
        ctr_logs.count(
            "Received unexpected telemetry message with path "
            "'Cisco-IOS-XR-ipv4-vrrp-oper:vrrp/ipv4/virtual-routers/virtual-router/vrrp-state'"
        )
        == 1
    )
    assert (
        ctr_logs.count(
            "Received unexpected telemetry message with path "
            "'Cisco-IOS-XR-ipv4-vrrp-oper:vrrp/ipv4/virtual-routers/virtual-router[virtual-router-id=1]'"
        )
        == 1
    )


def test_unexpected_vrrp_telem_msg_no_gpbkv(
    app: HAApp,
    minimal_config: str,
    grpc_client: gRPCClient,
):
    """Test handling of a VRRP telemetry message with no GPB key-value data."""
    with app.run(minimal_config) as ha_ctr:
        grpc_client.run(
            f"{ha_ctr.network_settings.ip_address}:50051",
            json_msgs=[
                dict(
                    encoding_path="Cisco-IOS-XR-ipv4-vrrp-oper:vrrp/ipv4/virtual-routers/virtual-router",
                )
            ],
        )
        ha_ctr.reload()
        assert ha_ctr.state.running
        ctr_logs = ha_ctr.logs()

    assert ctr_logs.count("ERROR") == 0
    assert (
        ctr_logs.count(
            "Ignoring telemetry message on path "
            "'Cisco-IOS-XR-ipv4-vrrp-oper:vrrp/ipv4/virtual-routers/virtual-router' "
            "without gpbkv data, only self-describing-gpb encoding is supported"
        )
        == 1
    )


def test_unexpected_json_payload(
    app: HAApp,
    minimal_config: str,
    grpc_client: gRPCClient,
):
    """Test handling of a message with a JSON payload."""
    with app.run(minimal_config) as ha_ctr:
        grpc_client_logs = grpc_client.run(
            f"{ha_ctr.network_settings.ip_address}:50051",
            raw_json_msgs=[
                dict(
                    ReqId=1,
                    data=json.dumps(
                        {
                            "encoding_path": "Cisco-IOS-XR-ipv4-vrrp-oper:vrrp/ipv4/virtual-routers/virtual-router",
                            "data_json": [
                                {
                                    "timestamp": "1683282451222",
                                    "keys": [
                                        {"interface-name": "HundredGigE0/0/0/1"},
                                        {"virtual-router-id": 1},
                                    ],
                                    "content": {
                                        "vrrp-state": "state-initial",
                                    },
                                }
                            ],
                        }
                    ),
                )
            ],
        )
        logger.debug("gRPC client logs:\n%s", grpc_client_logs)
        ha_ctr.reload()
        assert ha_ctr.state.running
        ctr_logs = ha_ctr.logs()

    assert ctr_logs.count("ERROR") == 0
    assert (
        ctr_logs.count(
            "Ignoring message with JSON payload, only self-describing-gpb "
            "encoding is supported"
        )
        == 1
    )


def test_unexpected_vrrp_telem_msg_invalid_gpbkv(
    app: HAApp,
    minimal_config: str,
    grpc_client: gRPCClient,
):
    """Test handling of a VRRP telemetry message with unexpected structure."""
    with app.run(minimal_config) as ha_ctr:
        grpc_client.run(
            f"{ha_ctr.network_settings.ip_address}:50051",
            json_msgs=[
                dict(
                    encoding_path="Cisco-IOS-XR-ipv4-vrrp-oper:vrrp/ipv4/virtual-routers/virtual-router",
                    data_gpbkv=[dict(fields=[])],
                ),
            ],
        )
        ha_ctr.reload()
        assert ha_ctr.state.running
        ctr_logs = ha_ctr.logs()

    assert ctr_logs.count("ERROR") == 1
    assert ctr_logs.count("VRRP session data has unexpected structure") == 1


def test_unexpected_mdt_dialout_msg(
    app: HAApp,
    grpc_client: gRPCClient,
    minimal_config: str,
):
    """Test handling of a MdtDialout message with unexpected data field."""
    with app.run(minimal_config) as ha_ctr:
        grpc_client.run(
            f"{ha_ctr.network_settings.ip_address}:50051",
            raw_json_msgs=[dict(ReqId=1, data="foo")],
            expect_error=True,
        )
        ha_ctr.reload()
        assert ha_ctr.state.running
        ctr_logs = ha_ctr.logs()

    assert ctr_logs.count("ERROR") > 0
    assert "google.protobuf.message.DecodeError: Error parsing message" in ctr_logs


def test_unclean_grpc_connection_close(
    app: HAApp,
    minimal_config: str,
    grpc_client: gRPCClient,
):
    """Test handling of an unclean gRPC connection close."""
    with app.run(minimal_config) as ha_ctr:
        grpc_client.run(
            f"{ha_ctr.network_settings.ip_address}:50051",
            unclean_connection_close=True,
        )
        ha_ctr.reload()
        assert ha_ctr.state.running
        ctr_logs = ha_ctr.logs()

    assert ctr_logs.count("ERROR") == 0
    if "Connection lost with gRPC peer" not in ctr_logs:
        assert "Connection closed by gRPC peer" in ctr_logs
        logger.warning("Hitting https://github.com/grpc/grpc/issues/33038")


def test_multiple_grpc_connections_disallowed(
    app: HAApp,
    minimal_config: str,
    grpc_client: gRPCClient,
):
    """Check that only a single gRPC connection is allowed at a time."""
    with app.run(minimal_config) as ha_ctr:
        ha_app_addr = f"{ha_ctr.network_settings.ip_address}:50051"
        with grpc_client.run_indefinite(ha_app_addr):
            # Create a second gRPC client, which should fail to connect.
            grpc_client_logs = grpc_client.run(ha_app_addr, expect_error=True)
        ha_ctr.reload()
        assert ha_ctr.state.running
        ctr_logs = ha_ctr.logs()

    assert "Concurrent RPC limit exceeded" in grpc_client_logs
    assert ctr_logs.count("ERROR") == 0
    assert ctr_logs.count("Connection established with gRPC peer") == 1
