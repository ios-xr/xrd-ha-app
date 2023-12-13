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
XRd HA app AWS plugin module, providing APIs for available AWS actions.
"""

from __future__ import annotations


__all__ = ("AWSClient",)

import logging
import os
import typing
from ipaddress import IPv4Address, IPv4Network
from typing import Any, Mapping

import boto3
import botocore.config
import botocore.exceptions
import requests


if typing.TYPE_CHECKING:
    from mypy_boto3_ec2.client import EC2Client
    from mypy_boto3_ec2.service_resource import (
        EC2ServiceResource,
        Instance,
        NetworkInterface,
        Route,
        RouteTable,
    )


logger = logging.getLogger(__name__)

# This is the link-local IP address to fetch EC2 instance metadata.
# https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/instancedata-data-retrieval.html
AWS_METADATA_URL_LATEST = "http://169.254.169.254/latest"

# Respect standard env vars.
# https://boto3.amazonaws.com/v1/documentation/api/latest/guide/configuration.html#using-environment-variables
AWS_METADATA_SERVICE_TIMEOUT = int(os.environ.get("AWS_METADATA_SERVICE_TIMEOUT", 2))
AWS_CONNECTION_TIMEOUT = 1  # seconds
AWS_CONNECTION_ATTEMPTS = int(os.environ.get("AWS_MAX_ATTEMPTS", 1))
AWS_CONNECTION_RETRY_MODE = os.environ.get("AWS_RETRY_MODE", "standard")


class AWSClient:
    """Represents an AWS client, providing APIs for supported actions."""

    def __init__(self, **kwargs: Any):
        """
        :param kwargs:
            Keyword arguments to pass through when creating boto3 client.
        """
        # This token is only used during initialisation, so just make it valid
        # for 1 minute (allowing for possible slow connections etc.).
        token = _get_ec2_token(ttl_seconds=60)
        ec2_id = _get_metadata("instance-id", token)
        region = _get_metadata("placement/region", token)
        logger.debug(
            "Creating AWS EC2 client - instance ID: %s, region: %s", ec2_id, region
        )

        client_kwargs = dict(
            service_name="ec2",
            region_name=region,
            config=botocore.config.Config(
                connect_timeout=AWS_CONNECTION_TIMEOUT,
                read_timeout=AWS_CONNECTION_TIMEOUT,
                retries=dict(
                    total_max_attempts=AWS_CONNECTION_ATTEMPTS,
                    mode=AWS_CONNECTION_RETRY_MODE,  # type: ignore
                ),
            ),
            **kwargs,
        )
        self._ec2_resource: EC2ServiceResource = boto3.resource(**client_kwargs)
        self._ec2_client: EC2Client = boto3.client(**client_kwargs)
        self._ec2_instance: Instance = self._ec2_resource.Instance(ec2_id)
        self._ec2_instance.load()  # Fetch state to ensure connection
        # Fetch the mapping of device ID to ENI object, assumed to be static.
        self._ec2_instance_enis: Mapping[int, NetworkInterface] = {
            eni.attachment["DeviceIndex"]: eni
            for eni in self._ec2_instance.network_interfaces
        }

    def get_indexed_eni(self, device_index: int) -> NetworkInterface:
        """
        Get an ENI attached to the local EC2 instance using its device index.

        :param device_index:
            The device index of the ENI on the EC2 instance.
        :raise ValueError:
            If there is no attached ENI for the given device index.
        :return:
            The ENI object.
        """
        try:
            return self._ec2_instance_enis[device_index]
        except KeyError:
            raise ValueError(
                f"EC2 instance {self._ec2_instance.id} device index '{device_index}' "
                "not found"
            ) from None

    def get_eni(self, eni_id: str) -> NetworkInterface:
        """
        Get an ENI object.

        :param eni_id:
            The ID of the ENI.
        :raise ValueError:
            If the specified ENI does not exist.
        :return:
            The ENI object.
        """
        try:
            eni = self._ec2_resource.NetworkInterface(eni_id)
            eni.load()
            return eni
        except botocore.exceptions.ClientError as exc:
            if exc.response["Error"]["Code"] == "InvalidNetworkInterfaceID.NotFound":
                raise ValueError(f"Network interface {eni_id!r} not found") from None
            else:
                raise

    def get_route_table(self, route_table_id: str) -> RouteTable:
        """
        Get a route table object from its ID.

        :param route_table_id:
            The ID of the route table.
        :raise ValueError:
            If there is no route table with the given ID.
        :return:
            The route table object.
        """
        try:
            rtb = self._ec2_resource.RouteTable(route_table_id)
            rtb.load()
            return rtb
        except botocore.exceptions.ClientError as exc:
            if exc.response["Error"]["Code"] == "InvalidRouteTableID.NotFound":
                raise ValueError(f"Route table {route_table_id!r} not found") from None
            else:
                raise

    def assign_vip(
        self,
        device_index: int,
        ip_addr: IPv4Address,
        *,
        precheck: bool,
    ) -> None:
        """
        Assign a private IP address to the given ENI of the local EC2 instance.

        :param device_index:
            The device index of the ENI to assign to.
        :param ip_addr:
            The IPv4 address to assign.
        :param precheck:
            Whether to first check whether the IP address is already assigned.
        """
        eni = self.get_indexed_eni(device_index)
        if precheck:
            eni.reload()  # Must reload the NetworkInterface state here.
            if any(
                IPv4Address(ec2_ip["PrivateIpAddress"]) == ip_addr
                for ec2_ip in eni.private_ip_addresses
            ):
                logger.debug("IPv4 address %s already assigned", ip_addr)
                return
            else:
                logger.debug("IPv4 address %s not assigned at precheck", ip_addr)

        logger.info(
            "Assigning private IPv4 address %s to device ID %d (%s)",
            ip_addr,
            device_index,
            eni.id,
        )
        eni.assign_private_ip_addresses(
            PrivateIpAddresses=[str(ip_addr)],
            AllowReassignment=True,
        )

    def update_route_table(
        self,
        route_table_id: str,
        destination: IPv4Network,
        target_network_interface: str,
        *,
        precheck: bool,
    ) -> None:
        """
        Update a given route table to associate a network with an ENI.

        :param route_table_id:
            The ID of the route table to update. Must exist and contain a route
            corresponding to the specified destination.
        :param destination:
            The route to update in the route table. This destination must exist
            in the route table.
        :param target_network_interface:
            The ENI ID to associate the route with.
        :param precheck:
            Whether to first check whether the route is already associated with
            the given ENI.
        """
        if precheck:
            if any(
                IPv4Network(route.destination_cidr_block) == destination
                and route.network_interface_id == target_network_interface
                for route in self._ec2_resource.RouteTable(route_table_id).routes
            ):
                logger.debug(
                    "Route destination %s via %s already present in route table %s",
                    destination,
                    target_network_interface,
                    route_table_id,
                )
                return
            else:
                logger.debug(
                    "Route destination %s via %s not present in route table %s at precheck",
                    destination,
                    target_network_interface,
                    route_table_id,
                )

        logger.info(
            "Updating route table %s with destination %s, target %s",
            route_table_id,
            destination,
            target_network_interface,
        )
        try:
            route = self._ec2_resource.Route(route_table_id, str(destination))
            route.replace(NetworkInterfaceId=target_network_interface)
        except botocore.exceptions.ClientError as exc:
            if exc.response["Error"]["Code"] in [
                "InvalidParameterValue",
                "InvalidRoute.NotFound",
            ]:
                logger.info(
                    "Creating route in route table %s with destination %s, target %s",
                    route_table_id,
                    destination,
                    target_network_interface,
                )
                rtb = self._ec2_resource.RouteTable(route_table_id)
                try:
                    rtb.create_route(
                        DestinationCidrBlock=str(destination),
                        NetworkInterfaceId=target_network_interface,
                    )
                except botocore.exceptions.ClientError as exc_inner:
                    if exc_inner.response["Error"]["Code"] == "RouteAlreadyExists":
                        # This is only expected to be hit if multiple threads
                        # end up trying to create the route in parallel, but
                        # this isn't actually an error case - just try replacing
                        # again.
                        logger.info(
                            "Route already created in route table %s with destination "
                            "%s, trying again to update with target %s",
                            route_table_id,
                            destination,
                            target_network_interface,
                        )
                        route.replace(NetworkInterfaceId=target_network_interface)
                    else:
                        raise
            else:
                raise


def _get_ec2_token(ttl_seconds: int) -> str:
    """
    Get an EC2 token for use with IMDSv2.

    :param ttl_seconds:
        The expiry time for the token. Maximum is 6 hours.
    :return:
        The fetched token.
    """
    try:
        logger.debug("Getting session token for IMDSv2")
        response = requests.put(
            AWS_METADATA_URL_LATEST + "/api/token",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": str(ttl_seconds)},
            timeout=AWS_METADATA_SERVICE_TIMEOUT,
        )
        response.raise_for_status()
        return response.text
    except requests.RequestException:
        logger.warning("Unable to get EC2 token for use with IMDSv2")
        logger.warning(
            "This may be due to the hop limit being too low (1) for pods to connect "
            "(see https://aws.amazon.com/about-aws/whats-new/2020/08/amazon-eks-supports-ec2-instance-metadata-service-v2/)"
        )
        logger.warning(
            "Please run the following to fix: "
            "aws ec2 modify-instance-metadata-options --instance-id <instance_id> --http-put-response-hop-limit 2 --http-endpoint enabled"
        )
        raise


def _get_metadata(path: str, token: str, *, json: bool = False) -> Any:
    """
    Get metadata from the AWS metadata service.

    :param path:
        URL path under http://169.254.169.254/latest/meta-data/ to fetch.
    :param token:
        IMDSv2 token to use for fetching the metadata.
    :param json:
        Whether to expect a JSON response, otherwise text.
    """
    response = requests.get(
        AWS_METADATA_URL_LATEST + "/meta-data/" + path,
        headers={"X-aws-ec2-metadata-token": token},
        timeout=AWS_METADATA_SERVICE_TIMEOUT,
    )
    return response.json() if json else response.text
