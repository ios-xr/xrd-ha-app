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

"""Common test utils."""

__all__ = (
    "ROOT_DIR",
    "Json",
    "parametrize_with_namedtuples",
)

import typing
from pathlib import Path
from typing import Mapping

import pytest


ROOT_DIR = Path.cwd()

Json = dict[None | bool | int | float | str | list["Json"] | dict[str, "Json"]]


def parametrize_with_namedtuples(
    testcases: Mapping[str, typing.NamedTuple],
) -> pytest.MarkDecorator:
    """
    Shorthand for parametrizing a test with a map: ID -> namedtuple of params.

    All values in the map are assumed to have the same fields.

    :param testcases:
        A map with keys being testcase IDs and values being namedtuple instances
        containing the testcase params.
    :return:
        The wrapped pytest parametrize mark decorator.
    """
    return pytest.mark.parametrize(
        list(testcases.values())[0]._fields,
        [pytest.param(*params, id=tc) for tc, params in testcases.items()],
    )
