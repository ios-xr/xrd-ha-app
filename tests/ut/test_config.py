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
import typing
from ipaddress import IPv4Address, IPv4Network
from pathlib import Path

import pydantic
import pytest
import yaml

from ha_app.config import (
    ActionType,
    AWSActivateVIPActionConfig,
    AWSConfig,
    AWSUpdateRouteTableActionConfig,
    Config,
    GlobalConfig,
    GroupConfig,
)

from ..utils import parametrize_with_namedtuples


logger = logging.getLogger(__name__)


class ParseConfigTestParams(typing.NamedTuple):
    input_config: str
    exp_config: Config


parse_config_testcases = {
    "empty": ParseConfigTestParams(
        input_config=textwrap.dedent(
            """\
            groups: []
            """
        ),
        exp_config=Config(
            **{
                "global": GlobalConfig(
                    port=50051,
                    consistency_check_interval_seconds=10,
                    aws=None,
                ),
                "groups": [],
            }
        ),
    ),
    "single_vip_ipv4": ParseConfigTestParams(
        input_config=textwrap.dedent(
            """\
            groups:
              - xr_interface: HundredGigE0/0/0/1
                vrid: 1
                action:
                    type: aws_activate_vip
                    device_index: 1
                    vip: 10.0.2.100
            """
        ),
        exp_config=Config(
            groups=[
                GroupConfig(
                    xr_interface="HundredGigE0/0/0/1",
                    vrid=1,
                    action=AWSActivateVIPActionConfig(
                        type=ActionType.AWS_ACTIVATE_VIP,
                        device_index=1,
                        vip=IPv4Address("10.0.2.100"),
                    ),
                )
            ],
        ),
    ),
    "single_route_ipv4": ParseConfigTestParams(
        input_config=textwrap.dedent(
            """\
            groups:
              - xr_interface: HundredGigE0/0/0/2
                vrid: 2
                action:
                    type: aws_update_route_table
                    route_table_id: rtb-ec081d94
                    destination: 10.0.2.0/24
                    target_network_interface: eni-7c90349273e5a5db
            """
        ),
        exp_config=Config(
            groups=[
                GroupConfig(
                    xr_interface="HundredGigE0/0/0/2",
                    vrid=2,
                    action=AWSUpdateRouteTableActionConfig(
                        type=ActionType.AWS_UPDATE_ROUTE_TABLE,
                        route_table_id="rtb-ec081d94",
                        destination=IPv4Network("10.0.2.0/24"),
                        target_network_interface="eni-7c90349273e5a5db",
                    ),
                )
            ],
        ),
    ),
    "many_actions": ParseConfigTestParams(
        input_config=textwrap.dedent(
            """\
            groups:
              - xr_interface: HundredGigE0/0/0/1
                vrid: 1
                action:
                    type: aws_activate_vip
                    device_index: 1
                    vip: 10.0.1.100
              - xr_interface: HundredGigE0/0/0/1
                vrid: 2
                action:
                    type: aws_activate_vip
                    device_index: 2
                    vip: 10.0.1.200
              - xr_interface: HundredGigE0/0/0/2
                vrid: 2
                action:
                    type: aws_activate_vip
                    device_index: 2
                    vip: 10.0.2.100
              - xr_interface: HundredGigE0/0/0/11
                vrid: 11
                action:
                    type: aws_update_route_table
                    route_table_id: rtb-123
                    destination: 10.0.2.0/24
                    target_network_interface: eni-7c90349273e5a5db
              - xr_interface: HundredGigE0/0/0/12
                vrid: 12
                action:
                    type: aws_update_route_table
                    route_table_id: rtb-456
                    destination: 22.22.0.0/20
                    target_network_interface: eni-03d03cf989c6b48c
            """
        ),
        exp_config=Config(
            groups=[
                GroupConfig(
                    xr_interface="HundredGigE0/0/0/1",
                    vrid=1,
                    action=AWSActivateVIPActionConfig(
                        type=ActionType.AWS_ACTIVATE_VIP,
                        device_index=1,
                        vip=IPv4Address("10.0.1.100"),
                    ),
                ),
                GroupConfig(
                    xr_interface="HundredGigE0/0/0/1",
                    vrid=2,
                    action=AWSActivateVIPActionConfig(
                        type=ActionType.AWS_ACTIVATE_VIP,
                        device_index=2,
                        vip=IPv4Address("10.0.1.200"),
                    ),
                ),
                GroupConfig(
                    xr_interface="HundredGigE0/0/0/2",
                    vrid=2,
                    action=AWSActivateVIPActionConfig(
                        type=ActionType.AWS_ACTIVATE_VIP,
                        device_index=2,
                        vip=IPv4Address("10.0.2.100"),
                    ),
                ),
                GroupConfig(
                    xr_interface="HundredGigE0/0/0/11",
                    vrid=11,
                    action=AWSUpdateRouteTableActionConfig(
                        type=ActionType.AWS_UPDATE_ROUTE_TABLE,
                        route_table_id="rtb-123",
                        destination=IPv4Network("10.0.2.0/24"),
                        target_network_interface="eni-7c90349273e5a5db",
                    ),
                ),
                GroupConfig(
                    xr_interface="HundredGigE0/0/0/12",
                    vrid=12,
                    action=AWSUpdateRouteTableActionConfig(
                        type=ActionType.AWS_UPDATE_ROUTE_TABLE,
                        route_table_id="rtb-456",
                        destination=IPv4Network("22.22.0.0/20"),
                        target_network_interface="eni-03d03cf989c6b48c",
                    ),
                ),
            ],
        ),
    ),
    "aws_endpoint": ParseConfigTestParams(
        input_config=textwrap.dedent(
            """\
            global:
                aws:
                    ec2_private_endpoint_url: "https://vpce-1234.ec2.us-west-2.vpce.amazonaws.com"
            groups: []
            """
        ),
        exp_config=Config(
            **{
                "global": GlobalConfig(
                    aws=AWSConfig(
                        ec2_private_endpoint_url="https://vpce-1234.ec2.us-west-2.vpce.amazonaws.com"
                    )
                ),
                "groups": [],
            }
        ),
    ),
    "port": ParseConfigTestParams(
        input_config=textwrap.dedent(
            """\
            global:
                port: 1234
            groups: []
            """
        ),
        exp_config=Config(
            **{
                "global": GlobalConfig(port=1234),
                "groups": [],
            }
        ),
    ),
    "consistency_check_interval": ParseConfigTestParams(
        input_config=textwrap.dedent(
            """\
            global:
                consistency_check_interval_seconds: 3
            groups: []
            """
        ),
        exp_config=Config(
            **{
                "global": GlobalConfig(consistency_check_interval_seconds=3),
                "groups": [],
            }
        ),
    ),
}


@parametrize_with_namedtuples(parse_config_testcases)
def test_parse_config(input_config: str, exp_config: Config):
    parsed_config = Config(**yaml.safe_load(input_config))
    assert parsed_config == exp_config


class InvalidConfigTestParams(typing.NamedTuple):
    input_config: str
    exp_regex: str


invalid_config_testcases = {
    "groups_not_a_list": InvalidConfigTestParams(
        input_config=textwrap.dedent(
            """\
            groups: {}
            """
        ),
        exp_regex=r"\ngroups\n.*not a valid list",
    ),
    "missing_groups": InvalidConfigTestParams(
        input_config=textwrap.dedent(
            """\
            global: {}
            """
        ),
        exp_regex=r"\ngroups\n.*field required",
    ),
    "port_type": InvalidConfigTestParams(
        input_config=textwrap.dedent(
            """\
            global:
                port: 1.2
            groups: []
            """
        ),
        exp_regex=r"\nglobal -> port\n.*not a valid integer",
    ),
    "port_value": InvalidConfigTestParams(
        input_config=textwrap.dedent(
            """\
            global:
                port: 123456789
            groups: []
            """
        ),
        exp_regex=r"\nglobal -> port\n.*less than or equal to 65535",
    ),
    "consistency_check_interval_type": InvalidConfigTestParams(
        input_config=textwrap.dedent(
            """\
            global:
                consistency_check_interval_seconds: None
            groups: []
            """
        ),
        exp_regex=(
            r"\nglobal -> consistency_check_interval_seconds\n.*not a valid integer"
        ),
    ),
    "consistency_check_interval_value": InvalidConfigTestParams(
        input_config=textwrap.dedent(
            """\
            global:
                consistency_check_interval_seconds: 0
            groups: []
            """
        ),
        exp_regex=(
            r"\nglobal -> consistency_check_interval_seconds\n"
            r".*greater than or equal to 1"
        ),
    ),
    "aws_endpoint_url_regex": InvalidConfigTestParams(
        input_config=textwrap.dedent(
            """\
            global:
                aws:
                    ec2_private_endpoint_url: 127.0.0.1
            groups: []
            """
        ),
        exp_regex=(
            r"\nglobal -> aws -> ec2_private_endpoint_url\n"
            r"\s+invalid or missing URL scheme"
        ),
    ),
    "group_vrid_type": InvalidConfigTestParams(
        input_config=textwrap.dedent(
            """\
            groups:
              - xr_interface: HundredGigE0/0/0/2
                vrid: False
                action:
                    type: aws_update_route_table
                    route_table_id: rtb-ec081d94
                    destination: 10.0.2.0/24
                    target_network_interface: eni-7c90349273e5a5db
            """
        ),
        exp_regex=r"\ngroups -> 0 -> vrid\n.*not a valid integer",
    ),
    "group_vrid_value": InvalidConfigTestParams(
        input_config=textwrap.dedent(
            """\
            groups:
              - xr_interface: HundredGigE0/0/0/2
                vrid: -2
                action:
                    type: aws_update_route_table
                    route_table_id: rtb-ec081d94
                    destination: 10.0.2.0/24
                    target_network_interface: eni-7c90349273e5a5db
            """
        ),
        exp_regex=r"\ngroups -> 0 -> vrid\n.*greater than or equal to 1",
    ),
    "group_action_type": InvalidConfigTestParams(
        input_config=textwrap.dedent(
            """\
            groups:
              - xr_interface: HundredGigE0/0/0/2
                vrid: 2
                action:
                    type: foo
                    ignored_field: 1
            """
        ),
        exp_regex=(
            r"\ngroups -> 0 -> action -> type\n"
            r".*value is not a valid enumeration member"
        ),
    ),
    "activate_vip_device_index_value": InvalidConfigTestParams(
        input_config=textwrap.dedent(
            """\
            groups:
              - xr_interface: HundredGigE0/0/0/2
                vrid: 2
                action:
                    type: aws_activate_vip
                    device_index: -4
                    vip: 1.2.3.4
            """
        ),
        exp_regex=(
            r"\ngroups -> 0 -> action -> device_index\n.*greater than or equal to 0"
        ),
    ),
    "activate_vip_ip_addr": InvalidConfigTestParams(
        input_config=textwrap.dedent(
            """\
            groups:
              - xr_interface: HundredGigE0/0/0/2
                vrid: 2
                action:
                    type: aws_activate_vip
                    device_index: 4
                    vip: 1.2.3
            """
        ),
        exp_regex=(r"\ngroups -> 0 -> action -> vip\n.*not a valid IPv4 address"),
    ),
    "activate_vip_ip_addr_ipv6": InvalidConfigTestParams(
        input_config=textwrap.dedent(
            """\
            groups:
              - xr_interface: HundredGigE0/0/0/2
                vrid: 2
                action:
                    type: aws_activate_vip
                    device_index: 4
                    vip: 10::1
            """
        ),
        exp_regex=(r"\ngroups -> 0 -> action -> vip\n.*not a valid IPv4 address"),
    ),
    "update_route_table_destination_ipv6": InvalidConfigTestParams(
        input_config=textwrap.dedent(
            """\
            groups:
              - xr_interface: HundredGigE0/0/0/2
                vrid: 2
                action:
                    type: aws_update_route_table
                    route_table_id: rtb-ec081d94
                    destination: 2001:DB8::/32
                    target_network_interface: eni-7c90349273e5a5db
            """
        ),
        exp_regex=(
            r"\ngroups -> 0 -> action -> destination\n.*not a valid IPv4 network"
        ),
    ),
    "update_route_table_missing_eni": InvalidConfigTestParams(
        input_config=textwrap.dedent(
            """\
            groups:
              - xr_interface: HundredGigE0/0/0/2
                vrid: 2
                action:
                    type: aws_update_route_table
                    route_table_id: rtb-ec081d94
                    destination: 10.0.2.0/24
            """
        ),
        exp_regex=(
            r"\ngroups -> 0 -> action -> target_network_interface\n.*field required"
        ),
    ),
    "unrecognised_field": InvalidConfigTestParams(
        input_config=textwrap.dedent(
            """\
            foo: 1
            groups: []
            """
        ),
        exp_regex=r"\nfoo\n.*extra fields not permitted",
    ),
    "unrecognised_global_field": InvalidConfigTestParams(
        input_config=textwrap.dedent(
            """\
            global:
                foo: 1
            groups: []
            """
        ),
        exp_regex=r"\nglobal -> foo\n.*extra fields not permitted",
    ),
    "unrecognised_group_field": InvalidConfigTestParams(
        input_config=textwrap.dedent(
            """\
            groups:
              - xr_interface: HundredGigE0/0/0/2
                vrid: 2
                action:
                    type: aws_update_route_table
                    route_table_id: rtb-ec081d94
                    destination: 10.0.2.0/24
                    target_network_interface: eni-7c90349273e5a5db
                foo: 1
            """
        ),
        exp_regex=r"\ngroups -> 0 -> foo\n.*extra fields not permitted",
    ),
    "unrecognised_action_field": InvalidConfigTestParams(
        input_config=textwrap.dedent(
            """\
            groups:
              - xr_interface: HundredGigE0/0/0/2
                vrid: 2
                action:
                    type: aws_update_route_table
                    route_table_id: rtb-ec081d94
                    destination: 10.0.2.0/24
                    target_network_interface: eni-7c90349273e5a5db
                    foo: 1
            """
        ),
        exp_regex=r"\ngroups -> 0 -> action -> foo\n.*extra fields not permitted",
    ),
    "multiple_actions_on_single_group": InvalidConfigTestParams(
        input_config=textwrap.dedent(
            """\
            groups:
              - xr_interface: HundredGigE0/0/0/1
                vrid: 1
                action:
                    type: aws_activate_vip
                    device_index: 0
                    vip: 1.2.3.4
              - xr_interface: HundredGigE0/0/0/1
                vrid: 1
                action:
                    type: aws_update_route_table
                    route_table_id: rtb-ec081d94
                    destination: 10.0.2.0/24
                    target_network_interface: eni-7c90349273e5a5db
            """
        ),
        exp_regex=r"\ngroups\n\s+Only one action allowed per VRRP group, got multiple for <xr_interface=HundredGigE0/0/0/1,vrid=1>",
    ),
}


@parametrize_with_namedtuples(invalid_config_testcases)
def test_invalid_config(input_config: str, exp_regex: str):
    with pytest.raises(pydantic.ValidationError, match=exp_regex) as exc_info:
        Config(**yaml.safe_load(input_config))
    logger.debug("Validation exception:\n%s", exc_info.value)


def test_from_file(tmp_path: Path):
    tmp_file = tmp_path / "config.yaml"
    tmp_file.write_text(
        textwrap.dedent(
            """\
            global:
                port: 1234
            groups: []
            """
        )
    )
    actual = Config.from_file(tmp_file)
    expected = Config(**{"global": GlobalConfig(port=1234), "groups": []})
    assert actual == expected
