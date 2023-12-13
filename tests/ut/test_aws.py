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
from ipaddress import IPv4Address, IPv4Network
from unittest import mock

import botocore.exceptions
import pytest
import requests

from ha_app import aws


@pytest.fixture(autouse=True)
def boto3_client_create() -> mock.Mock:
    with mock.patch("boto3.client") as m:
        yield m


@pytest.fixture
def boto3_client(boto3_client_create: mock.Mock) -> mock.Mock:
    return boto3_client_create.return_value


@pytest.fixture(autouse=True)
def boto3_resource_create() -> mock.Mock:
    with mock.patch("boto3.resource") as m:
        yield m


@pytest.fixture
def boto3_resource(boto3_resource_create: mock.Mock) -> mock.Mock:
    return boto3_resource_create.return_value


@pytest.fixture
def boto3_ec2_instance(boto3_resource_create: mock.Mock) -> mock.Mock:
    return boto3_resource_create.return_value.Instance.return_value


@pytest.fixture(autouse=True)
def requests_put() -> mock.Mock:
    with mock.patch("requests.put") as m:
        yield m


@pytest.fixture(autouse=True)
def requests_get() -> mock.Mock:
    with mock.patch("requests.get") as m:
        yield m


def test_create_client(
    requests_get: mock.Mock,
    requests_put: mock.Mock,
    boto3_client_create: mock.Mock,
    boto3_resource_create: mock.Mock,
):
    """Test the initialisation of an AWSClient instance."""
    requests_put.return_value = mock.Mock(text="test-token")
    requests_get.side_effect = [
        mock.Mock(text="test-instance-id"),
        mock.Mock(text="test-region"),
    ]

    client = aws.AWSClient(endpoint_url="https://aws-vpc.com")

    requests_put.assert_called_once_with(
        "http://169.254.169.254/latest/api/token",
        headers=mock.ANY,
        timeout=mock.ANY,
    )
    requests_get.assert_has_calls(
        [
            mock.call(
                "http://169.254.169.254/latest/meta-data/instance-id",
                headers={"X-aws-ec2-metadata-token": "test-token"},
                timeout=mock.ANY,
            ),
            mock.call(
                "http://169.254.169.254/latest/meta-data/placement/region",
                headers={"X-aws-ec2-metadata-token": "test-token"},
                timeout=mock.ANY,
            ),
        ],
        any_order=True,
    )
    boto3_client_create.assert_called_once_with(
        service_name="ec2",
        region_name="test-region",
        endpoint_url="https://aws-vpc.com",
        config=mock.ANY,
    )
    boto3_resource_create.assert_called_once_with(
        service_name="ec2",
        region_name="test-region",
        endpoint_url="https://aws-vpc.com",
        config=mock.ANY,
    )
    boto3_resource_create.return_value.Instance.assert_called_once_with(
        "test-instance-id"
    )


def test_create_client_token_error(
    requests_get: mock.Mock,
    requests_put: mock.Mock,
    boto3_client_create: mock.Mock,
    boto3_resource_create: mock.Mock,
    caplog: pytest.LogCaptureFixture,
):
    """Test failure to get a token during initialisation of AWSClient."""
    requests_put.side_effect = requests.RequestException

    with caplog.at_level(logging.WARNING, "ha_app.aws"):
        with pytest.raises(requests.RequestException):
            aws.AWSClient(endpoint_url="https://aws-vpc.com")

    assert len(caplog.records) >= 1
    requests_put.assert_called_once_with(
        "http://169.254.169.254/latest/api/token",
        headers=mock.ANY,
        timeout=mock.ANY,
    )
    requests_get.assert_not_called()
    boto3_client_create.assert_not_called()
    boto3_resource_create.assert_not_called()


def test_get_indexed_eni(boto3_ec2_instance: mock.Mock):
    """Test the AWSClient.get_indexed_eni() method."""
    enis = {idx: mock.Mock(attachment={"DeviceIndex": idx}) for idx in (2, 3, 8)}
    boto3_ec2_instance.network_interfaces = enis.values()

    assert aws.AWSClient().get_indexed_eni(2) is enis[2]
    with pytest.raises(ValueError, match=r"device index '999' not found"):
        aws.AWSClient().get_indexed_eni(999)


def test_get_eni(boto3_resource: mock.Mock, boto3_ec2_instance: mock.Mock):
    """Test the AWSClient.get_eni() method."""
    mock_eni = boto3_resource.NetworkInterface.return_value
    aws_client = aws.AWSClient()

    # Success case
    assert aws_client.get_eni("eni-123") is mock_eni
    boto3_resource.NetworkInterface.assert_called_once_with("eni-123")
    mock_eni.load.assert_called_once()
    boto3_resource.reset_mock()

    # Expected failure case
    mock_eni.load.side_effect = botocore.exceptions.ClientError(
        error_response={"Error": {"Code": "InvalidNetworkInterfaceID.NotFound"}},
        operation_name="DescribeNetworkInterfaces",
    )
    with pytest.raises(ValueError, match=r"Network interface 'eni-999' not found"):
        aws_client.get_eni("eni-999")

    # Unexpected failure case
    mock_eni.load.side_effect = botocore.exceptions.ClientError(
        error_response={"Error": {"Code": "Unexpected"}},
        operation_name="DescribeNetworkInterfaces",
    )
    with pytest.raises(botocore.exceptions.ClientError):
        aws_client.get_eni("eni-999")


def test_get_route_table(boto3_resource: mock.Mock):
    """Test the AWSClient.get_route_table() method."""
    mock_rtb = boto3_resource.RouteTable.return_value
    aws_client = aws.AWSClient()

    # Success case
    assert aws_client.get_route_table("rtb-123") is mock_rtb
    boto3_resource.RouteTable.assert_called_once_with("rtb-123")
    mock_rtb.load.assert_called_once()
    boto3_resource.reset_mock()

    # Expected failure case
    mock_rtb.load.side_effect = botocore.exceptions.ClientError(
        error_response={"Error": {"Code": "InvalidRouteTableID.NotFound"}},
        operation_name="DescribeRouteTables",
    )
    with pytest.raises(ValueError, match=r"Route table 'rtb-999' not found"):
        aws_client.get_route_table("rtb-999")

    # Unexpected failure case
    mock_rtb.load.side_effect = botocore.exceptions.ClientError(
        error_response={"Error": {"Code": "Unexpected"}},
        operation_name="DescribeRouteTables",
    )
    with pytest.raises(botocore.exceptions.ClientError):
        aws_client.get_route_table("rtb-999")


class TestAssignVIP:
    """Test the AWSClient.assign_vip() API."""

    def test_no_precheck_success(self, boto3_ec2_instance: mock.Mock):
        """Test with IPv4 address and precheck=False."""
        enis = {idx: mock.Mock(attachment={"DeviceIndex": idx}) for idx in (2, 3, 8)}
        boto3_ec2_instance.network_interfaces = enis.values()

        aws.AWSClient().assign_vip(2, IPv4Address("1.2.3.4"), precheck=False)
        aws.AWSClient().assign_vip(8, IPv4Address("8.0.0.254"), precheck=False)

        enis[2].assign_private_ip_addresses.assert_called_once_with(
            PrivateIpAddresses=["1.2.3.4"], AllowReassignment=True
        )
        enis[8].assign_private_ip_addresses.assert_called_once_with(
            PrivateIpAddresses=["8.0.0.254"], AllowReassignment=True
        )
        enis[3].assign_private_ip_addresses.assert_not_called()
        for eni in enis.values():
            eni.reload.assert_not_called()

    def test_precheck_success(self, boto3_ec2_instance: mock.Mock):
        """Test with IPv4 address and precheck=True."""
        enis = {
            idx: mock.Mock(attachment={"DeviceIndex": idx}, private_ip_addresses=[])
            for idx in (2, 3, 8)
        }
        enis[2].private_ip_addresses = [{"PrivateIpAddress": "1.1.1.1"}]
        enis[8].private_ip_addresses = [
            {"PrivateIpAddress": "8.0.0.200"},
            {"PrivateIpAddress": "8.0.0.254"},
        ]
        boto3_ec2_instance.network_interfaces = enis.values()

        aws.AWSClient().assign_vip(2, IPv4Address("1.2.3.4"), precheck=True)
        aws.AWSClient().assign_vip(8, IPv4Address("8.0.0.254"), precheck=True)

        enis[2].assign_private_ip_addresses.assert_called_once_with(
            PrivateIpAddresses=["1.2.3.4"], AllowReassignment=True
        )
        enis[2].reload.assert_called_once()
        enis[8].assign_private_ip_addresses.assert_not_called()
        enis[8].reload.assert_called_once()
        enis[3].assign_private_ip_addresses.assert_not_called()
        enis[3].reload.assert_not_called()


class TestUpdateRouteTable:
    """Test the AWSClient.update_route_table() API."""

    def test_no_precheck_replace_success(self, boto3_resource: mock.Mock):
        """Test with IPv4 route and no precheck."""
        aws.AWSClient().update_route_table(
            "rtb-123", IPv4Network("1.2.3.0/24"), "eni-123", precheck=False
        )

        boto3_resource.Route.assert_called_once_with("rtb-123", "1.2.3.0/24")
        boto3_route = boto3_resource.Route.return_value
        boto3_route.replace.assert_called_once_with(NetworkInterfaceId="eni-123")

    def test_precheck_replace_success(self, boto3_resource: mock.Mock):
        """Test with IPv4 route and precheck."""
        route_tables = {
            "rtb-1": mock.Mock(
                routes=[
                    mock.Mock(
                        destination_cidr_block="1.2.3.0/24",
                        network_interface_id="eni-123",
                    )
                ]
            ),
            "rtb-2": mock.Mock(
                routes=[
                    mock.Mock(
                        destination_cidr_block="1.2.3.0/24",
                        network_interface_id="eni-123",
                    ),
                    mock.Mock(
                        destination_cidr_block="8.8.8.0/24",
                        network_interface_id="eni-456",
                    ),
                ]
            ),
        }
        boto3_resource.RouteTable.side_effect = lambda id: route_tables.get(
            id, mock.Mock(routes=[])
        )

        aws.AWSClient().update_route_table(
            "rtb-1", IPv4Network("1.2.3.0/24"), "eni-123", precheck=True
        )
        boto3_resource.Route.assert_not_called()
        boto3_resource.reset_mock()

        aws.AWSClient().update_route_table(
            "rtb-2", IPv4Network("8.8.8.0/24"), "eni-456", precheck=True
        )
        boto3_resource.Route.assert_not_called()
        boto3_resource.reset_mock()

        aws.AWSClient().update_route_table(
            "rtb-2", IPv4Network("1.2.3.0/24"), "eni-456", precheck=True
        )
        boto3_resource.Route.assert_called_once_with("rtb-2", "1.2.3.0/24")
        boto3_route = boto3_resource.Route.return_value
        boto3_route.replace.assert_called_once_with(NetworkInterfaceId="eni-456")
        boto3_resource.reset_mock()

    def test_no_precheck_create_route_success(self, boto3_resource: mock.Mock):
        """Test success creating the route."""
        boto3_resource.Route.return_value.replace.side_effect = (
            botocore.exceptions.ClientError(
                error_response={"Error": {"Code": "InvalidParameterValue"}},
                operation_name="ReplaceRoute",
            )
        )
        aws.AWSClient().update_route_table(
            "rtb-123", IPv4Network("1.2.3.0/24"), "eni-123", precheck=False
        )
        boto3_resource.Route.assert_called_once_with("rtb-123", "1.2.3.0/24")
        boto3_resource.Route.return_value.replace.assert_called_once_with(
            NetworkInterfaceId="eni-123"
        )
        boto3_resource.RouteTable.assert_called_once_with("rtb-123")
        boto3_resource.RouteTable.return_value.create_route.assert_called_once_with(
            DestinationCidrBlock="1.2.3.0/24", NetworkInterfaceId="eni-123"
        )

    def test_route_exists_at_create(self, boto3_resource: mock.Mock):
        """
        Test the route already existing at the point it is being created.
        This can be caused by a race between two threads.
        Replacing the route succeeds on the second attempt.
        """
        boto3_resource.Route.return_value.replace.side_effect = [
            (
                botocore.exceptions.ClientError(
                    error_response={"Error": {"Code": "InvalidParameterValue"}},
                    operation_name="ReplaceRoute",
                )
            ),
            None,
        ]
        boto3_resource.RouteTable.return_value.create_route.side_effect = (
            botocore.exceptions.ClientError(
                error_response={"Error": {"Code": "RouteAlreadyExists"}},
                operation_name="CreateRoute",
            )
        )
        aws.AWSClient().update_route_table(
            "rtb-123", IPv4Network("1.2.3.0/24"), "eni-123", precheck=False
        )
        boto3_resource.Route.assert_called_once_with("rtb-123", "1.2.3.0/24")
        boto3_resource.Route.return_value.replace.assert_has_calls(
            [
                mock.call(NetworkInterfaceId="eni-123"),
                mock.call(NetworkInterfaceId="eni-123"),
            ]
        )
        boto3_resource.RouteTable.assert_called_once_with("rtb-123")
        boto3_resource.RouteTable.return_value.create_route.assert_called_once_with(
            DestinationCidrBlock="1.2.3.0/24", NetworkInterfaceId="eni-123"
        )

    def test_unexpected_replace_error(self, boto3_resource: mock.Mock):
        """Test unexpected boto3 client error from ReplaceRoute."""
        boto3_resource.Route.return_value.replace.side_effect = (
            botocore.exceptions.ClientError(
                error_response={"Error": {"Code": "Unexpected"}},
                operation_name="ReplaceRoute",
            )
        )
        with pytest.raises(botocore.exceptions.ClientError):
            aws.AWSClient().update_route_table(
                "rtb-123", IPv4Network("1.2.3.0/24"), "eni-123", precheck=False
            )
        boto3_resource.Route.assert_called_once_with("rtb-123", "1.2.3.0/24")
        boto3_resource.Route.return_value.replace.assert_called_once_with(
            NetworkInterfaceId="eni-123"
        )
        boto3_resource.RouteTable.assert_not_called()
        boto3_resource.RouteTable.return_value.create_route.assert_not_called()

    def test_unexpected_create_error(self, boto3_resource: mock.Mock):
        """Test unexpected boto3 client error from CreateRoute."""
        boto3_resource.Route.return_value.replace.side_effect = (
            botocore.exceptions.ClientError(
                error_response={"Error": {"Code": "InvalidParameterValue"}},
                operation_name="ReplaceRoute",
            )
        )
        boto3_resource.RouteTable.return_value.create_route.side_effect = (
            botocore.exceptions.ClientError(
                error_response={"Error": {"Code": "Unexpected"}},
                operation_name="CreateRoute",
            )
        )
        with pytest.raises(botocore.exceptions.ClientError):
            aws.AWSClient().update_route_table(
                "rtb-123", IPv4Network("1.2.3.0/24"), "eni-123", precheck=False
            )
        boto3_resource.Route.assert_called_once_with("rtb-123", "1.2.3.0/24")
        boto3_resource.Route.return_value.replace.assert_called_once_with(
            NetworkInterfaceId="eni-123"
        )
        boto3_resource.RouteTable.assert_called_once_with("rtb-123")
        boto3_resource.RouteTable.return_value.create_route.assert_called_once_with(
            DestinationCidrBlock="1.2.3.0/24", NetworkInterfaceId="eni-123"
        )
