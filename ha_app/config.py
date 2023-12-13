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

"""
XRd HA app config module, providing types for parsing the user config file.
"""

__all__ = (
    "AWSActivateVIPActionConfig",
    "AWSUpdateRouteTableActionConfig",
    "BaseActionConfig",
    "Config",
    "GlobalConfig",
    "GroupConfig",
)

import logging
import typing
from ipaddress import IPv4Address, IPv4Network
from pathlib import Path
from typing import Literal, Self

import pydantic
import yaml
from pydantic import AnyHttpUrl, Field

from .types import ActionType


logger = logging.getLogger(__name__)


class NonNegativeInt(pydantic.StrictInt):
    """A strict non-negative integer."""

    ge = 0


class PositiveInt(pydantic.StrictInt):
    """A strict integer greater than zero."""

    ge = 1


class Port(pydantic.StrictInt):
    """A strict integer representing a valid port number."""

    ge = 1024
    le = 65535


class VRID(pydantic.StrictInt):
    """A strict integer representing a VRID."""

    ge = 1
    le = 255


class AWSConfig(pydantic.BaseModel, extra=pydantic.Extra.forbid):
    """Corresponds to 'global->aws' in the config."""

    ec2_private_endpoint_url: AnyHttpUrl | None = None


class GlobalConfig(pydantic.BaseModel, extra=pydantic.Extra.forbid):
    """Corresponds to 'global' in the config."""

    port: Port = typing.cast(Port, 50051)
    consistency_check_interval_seconds: PositiveInt = typing.cast(PositiveInt, 10)
    aws: AWSConfig | None = None


class BaseActionConfig(pydantic.BaseModel, extra=pydantic.Extra.allow):
    """
    Base class corresponding to action types, 'groups->action' in the config.
    """

    type: ActionType


class AWSActivateVIPActionConfig(BaseActionConfig, extra=pydantic.Extra.forbid):
    """
    Corresponds to 'groups->action' for 'aws_activate_vip' in the config.
    """

    type: Literal[ActionType.AWS_ACTIVATE_VIP]
    device_index: NonNegativeInt
    vip: IPv4Address  # Currently only support IPv4


class AWSUpdateRouteTableActionConfig(BaseActionConfig, extra=pydantic.Extra.forbid):
    """
    Corresponds to 'groups->action' for 'aws_update_route_table' in the config.
    """

    type: Literal[ActionType.AWS_UPDATE_ROUTE_TABLE]
    route_table_id: str
    destination: IPv4Network  # Currently only support IPv4
    target_network_interface: str


class GroupConfig(pydantic.BaseModel, extra=pydantic.Extra.forbid):
    """Corresponds to 'groups' in the config."""

    xr_interface: str
    vrid: VRID
    action: BaseActionConfig

    @pydantic.validator("action")
    def validate_action_type(
        cls, action: BaseActionConfig
    ) -> AWSActivateVIPActionConfig | AWSUpdateRouteTableActionConfig:
        """
        Validate an action type against the associated concrete class.

        :param action:
            The action config being validated.
        :return:
            The parsed action config with associated action type.
        :raise ValueError:
            If there is a parsing error for the action type.
        """
        if action.type is ActionType.AWS_ACTIVATE_VIP:
            return AWSActivateVIPActionConfig(**vars(action))
        elif action.type is ActionType.AWS_UPDATE_ROUTE_TABLE:
            return AWSUpdateRouteTableActionConfig(**vars(action))
        else:
            assert False


class Config(pydantic.BaseModel, extra=pydantic.Extra.forbid):
    """Direct typed representation of the app's config."""

    global_: GlobalConfig = Field(alias="global", default_factory=GlobalConfig)
    groups: list[GroupConfig]

    @classmethod
    def from_file(cls, file: str | Path) -> Self:
        """
        Load a config object from a config file.

        :param file:
            The path to the file to load.
        """
        logger.debug("Reading config from file: %s", file)
        with open(file, "r", encoding="utf-8") as f:
            return cls(**(yaml.safe_load(f) or {}))

    @pydantic.validator("groups")
    def one_action_per_group(cls, groups: list[GroupConfig]) -> list[GroupConfig]:
        """
        Validation method to ensure only one action is provided per group key.

        :param groups:
            The list of groups being validated.
        :return:
            The list of groups (unchanged).
        :raise ValueError:
            If there are multiple actions for a VRRP session.
        """
        group_keys = [(g.xr_interface, g.vrid) for g in groups]
        duplicate_keys = []
        for k in group_keys:
            if group_keys.count(k) > 1 and k not in duplicate_keys:
                duplicate_keys.append(k)
        if duplicate_keys:
            keys_str = ", ".join(
                f"<xr_interface={k[0]},vrid={k[1]}>" for k in duplicate_keys
            )
            raise ValueError(
                f"Only one action allowed per VRRP group, got multiple for {keys_str}"
            )
        return groups
