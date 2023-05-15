# Copyright 2023 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import asyncio
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from sunbeam.commands.openstack import DeployControlPlaneStep, ResizeControlPlaneStep
from sunbeam.commands.terraform import TerraformException
from sunbeam.jobs.common import ResultType
from sunbeam.jobs.juju import (
    ApplicationNotFoundException,
    JujuWaitException,
    TimeoutException,
)

TOPOLOGY = "single"
DATABASE = "single"


@pytest.fixture(autouse=True)
def mock_run_sync(mocker):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()

    def run_sync(coro):
        return loop.run_until_complete(coro)

    mocker.patch("sunbeam.commands.openstack.run_sync", run_sync)
    yield
    loop.close()


class TestDeployControlPlaneStep(unittest.TestCase):
    def __init__(self, methodName: str = "runTest") -> None:
        super().__init__(methodName)
        self.client = patch("sunbeam.commands.openstack.Client")

    def setUp(self):
        self.client.start()
        self.jhelper = AsyncMock()
        self.tfhelper = Mock(path=Path())

    def tearDown(self):
        self.client.stop()

    def test_run_pristine_installation(self):
        self.jhelper.get_application.side_effect = ApplicationNotFoundException(
            "not found"
        )

        step = DeployControlPlaneStep(self.tfhelper, self.jhelper, TOPOLOGY, DATABASE)
        result = step.run()

        self.tfhelper.write_tfvars.assert_called_once()
        self.tfhelper.apply.assert_called_once()
        assert result.result_type == ResultType.COMPLETED

    def test_run_tf_apply_failed(self):
        self.tfhelper.apply.side_effect = TerraformException("apply failed...")

        step = DeployControlPlaneStep(self.tfhelper, self.jhelper, TOPOLOGY, DATABASE)
        result = step.run()

        self.tfhelper.apply.assert_called_once()
        assert result.result_type == ResultType.FAILED
        assert result.message == "apply failed..."

    def test_run_waiting_timed_out(self):
        self.jhelper.wait_until_active.side_effect = TimeoutException("timed out")

        step = DeployControlPlaneStep(self.tfhelper, self.jhelper, TOPOLOGY, DATABASE)
        result = step.run()

        self.jhelper.wait_until_active.assert_called_once()
        assert result.result_type == ResultType.FAILED
        assert result.message == "timed out"

    def test_run_unit_in_error_state(self):
        self.jhelper.wait_until_active.side_effect = JujuWaitException(
            "Unit in error: placement/0"
        )

        step = DeployControlPlaneStep(self.tfhelper, self.jhelper, TOPOLOGY, DATABASE)
        result = step.run()

        self.jhelper.wait_until_active.assert_called_once()
        assert result.result_type == ResultType.FAILED
        assert result.message == "Unit in error: placement/0"


class TestResizeControlPlaneStep(unittest.TestCase):
    def __init__(self, methodName: str = "runTest") -> None:
        super().__init__(methodName)
        self.client = patch("sunbeam.commands.openstack.Client")
        self.read_config = patch(
            "sunbeam.commands.openstack.read_config",
            Mock(return_value={"topology": "single", "database": "single"}),
        )

    def setUp(self):
        self.client.start()
        self.read_config.start()
        self.jhelper = AsyncMock()
        self.tfhelper = Mock(path=Path())

    def tearDown(self):
        self.client.stop()
        self.read_config.stop()

    def test_run_pristine_installation(self):
        self.jhelper.get_application.side_effect = ApplicationNotFoundException(
            "not found"
        )

        step = ResizeControlPlaneStep(self.tfhelper, self.jhelper, "single", False)
        result = step.run()

        self.tfhelper.write_tfvars.assert_called_once()
        self.tfhelper.apply.assert_called_once()
        assert result.result_type == ResultType.COMPLETED

    def test_run_tf_apply_failed(self):
        self.tfhelper.apply.side_effect = TerraformException("apply failed...")

        step = ResizeControlPlaneStep(self.tfhelper, self.jhelper, TOPOLOGY, False)
        result = step.run()

        self.tfhelper.apply.assert_called_once()
        assert result.result_type == ResultType.FAILED
        assert result.message == "apply failed..."

    def test_run_waiting_timed_out(self):
        self.jhelper.wait_until_active.side_effect = TimeoutException("timed out")

        step = ResizeControlPlaneStep(self.tfhelper, self.jhelper, TOPOLOGY, False)
        result = step.run()

        self.jhelper.wait_until_active.assert_called_once()
        assert result.result_type == ResultType.FAILED
        assert result.message == "timed out"

    def test_run_unit_in_error_state(self):
        self.jhelper.wait_until_active.side_effect = JujuWaitException(
            "Unit in error: placement/0"
        )

        step = ResizeControlPlaneStep(self.tfhelper, self.jhelper, TOPOLOGY, False)
        result = step.run()

        self.jhelper.wait_until_active.assert_called_once()
        assert result.result_type == ResultType.FAILED
        assert result.message == "Unit in error: placement/0"

    def test_run_incompatible_topology(self):
        step = ResizeControlPlaneStep(self.tfhelper, self.jhelper, "large", False)
        result = step.run()

        assert result.result_type == ResultType.FAILED
        assert "Cannot resize control plane to large" in result.message

    def test_run_force_incompatible_topology(self):
        step = ResizeControlPlaneStep(self.tfhelper, self.jhelper, "large", True)
        result = step.run()

        self.jhelper.wait_until_active.assert_called_once()
        assert result.result_type == ResultType.COMPLETED
