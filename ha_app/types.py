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
XRd HA app common types.
"""

__all__ = (
    "Action",
    "ActionType",
    "VRRPEvent",
    "VRRPSession",
    "VRRPState",
)

import enum
import typing
from dataclasses import dataclass
from typing import Any, Callable, Mapping


class VRRPSession(typing.NamedTuple):
    """
    A VRRP session key, consisting of XR interface name and VRID.

    Used for registered actions and received telemetry notifications.
    """

    interface_name: str
    vrid: int

    def __repr__(self) -> str:
        return f"<xr_interface={self.interface_name},vrid={self.vrid}>"


class VRRPState(enum.Enum):
    """Enum of VRRP session states, as tracked within this application."""

    INACTIVE = enum.auto()
    ACTIVE = enum.auto()


@dataclass
class VRRPEvent:
    """
    Encapsulation of VRRP state corresponding to a VRRP session.

    Reflects the information received within a telemetry message that's
    relevant to this application.
    """

    session: VRRPSession
    state: VRRPState


class ActionType(enum.StrEnum):
    """Enum of supported action types."""

    AWS_ACTIVATE_VIP = "aws_activate_vip"
    AWS_UPDATE_ROUTE_TABLE = "aws_update_route_table"

    def __repr__(self) -> str:
        return self.value


@dataclass
class Action:
    """Representation of an action to perform on a go-active event."""

    type: ActionType
    func: Callable[..., None]
    kwargs: Mapping[str, Any]

    def __init__(self, type_: ActionType, func: Callable[..., None], **kwargs: Any):
        """
        :param type_:
            The action type.
        :param func:
            The function representing the action.
        :param kwargs:
            Keyword arguments to be passed to the action function.
        """
        self.type = type_
        self.func = func
        self.kwargs = kwargs
