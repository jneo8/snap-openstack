# Copyright (c) 2023 Canonical Ltd.
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
from unittest.mock import AsyncMock, Mock, patch

import pytest

from sunbeam.clusterd.service import NodeNotExistInClusterException
from sunbeam.core.common import ResultType
from sunbeam.core.juju import ApplicationNotFoundException, TimeoutException
from sunbeam.core.terraform import TerraformException
from sunbeam.steps.hypervisor import (
    ReapplyHypervisorTerraformPlanStep,
    RemoveHypervisorUnitStep,
)


@pytest.fixture(autouse=True)
def mock_run_sync(mocker):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()

    def run_sync(coro):
        return loop.run_until_complete(coro)

    mocker.patch("sunbeam.steps.hypervisor.run_sync", run_sync)
    yield
    loop.close()


class TestRemoveHypervisorUnitStep(unittest.TestCase):
    def __init__(self, methodName: str = "runTest") -> None:
        super().__init__(methodName)
        self.read_config = patch(
            "sunbeam.steps.hypervisor.read_config",
            Mock(
                return_value={
                    "openstack_model": "openstack",
                }
            ),
        )
        guest = Mock()
        type(guest).name = "my-guest"
        self.guests = [guest]

    def setUp(self):
        self.client = Mock()
        self.read_config.start()
        self.jhelper = AsyncMock()
        self.name = "test-0"

    def tearDown(self):
        self.read_config.stop()

    def test_is_skip(self):
        id = "1"
        self.client.cluster.get_node_info.return_value = {"machineid": id}
        self.jhelper.get_application.return_value = Mock(
            units=[Mock(machine=Mock(id=id))]
        )

        step = RemoveHypervisorUnitStep(
            self.client, self.name, self.jhelper, "test-model"
        )
        result = step.is_skip()

        self.client.cluster.get_node_info.assert_called_once()
        self.jhelper.get_application.assert_called_once()
        assert result.result_type == ResultType.COMPLETED

    def test_is_skip_node_missing(self):
        self.client.cluster.get_node_info.side_effect = NodeNotExistInClusterException(
            "Node missing..."
        )

        step = RemoveHypervisorUnitStep(
            self.client, self.name, self.jhelper, "test-model"
        )
        result = step.is_skip()

        self.client.cluster.get_node_info.assert_called_once()
        assert result.result_type == ResultType.SKIPPED

    def test_is_skip_application_missing(self):
        self.jhelper.get_application.side_effect = ApplicationNotFoundException(
            "Application missing..."
        )

        step = RemoveHypervisorUnitStep(
            self.client, self.name, self.jhelper, "test-model"
        )
        result = step.is_skip()

        self.jhelper.get_application.assert_called_once()
        assert result.result_type == ResultType.SKIPPED

    def test_is_skip_unit_missing(self):
        self.client.cluster.get_node_info.return_value = {}
        self.jhelper.get_application.return_value = Mock(units=[])

        step = RemoveHypervisorUnitStep(
            self.client, self.name, self.jhelper, "test-model"
        )
        result = step.is_skip()

        self.client.cluster.get_node_info.assert_called_once()
        self.jhelper.get_application.assert_called_once()
        assert result.result_type == ResultType.SKIPPED

    @patch("sunbeam.steps.hypervisor.remove_hypervisor")
    @patch("sunbeam.steps.hypervisor.guests_on_hypervisor")
    def test_run(self, guests_on_hypervisor, remove_hypervisor):
        guests_on_hypervisor.return_value = []
        step = RemoveHypervisorUnitStep(
            self.client, self.name, self.jhelper, "test-model"
        )
        result = step.run()
        assert result.result_type == ResultType.COMPLETED
        remove_hypervisor.assert_called_once_with("test-0", self.jhelper)

    @patch("sunbeam.steps.hypervisor.remove_hypervisor")
    @patch("sunbeam.steps.hypervisor.guests_on_hypervisor")
    def test_run_guests(self, guests_on_hypervisor, remove_hypervisor):
        guests_on_hypervisor.return_value = self.guests
        step = RemoveHypervisorUnitStep(
            self.client, self.name, self.jhelper, "test-model"
        )
        result = step.run()
        assert result.result_type == ResultType.FAILED
        assert not remove_hypervisor.called

    @patch("sunbeam.steps.hypervisor.remove_hypervisor")
    @patch("sunbeam.steps.hypervisor.guests_on_hypervisor")
    def test_run_guests_force(self, guests_on_hypervisor, remove_hypervisor):
        guests_on_hypervisor.return_value = self.guests
        step = RemoveHypervisorUnitStep(
            self.client, self.name, self.jhelper, "test-model", True
        )
        result = step.run()
        assert result.result_type == ResultType.COMPLETED
        remove_hypervisor.assert_called_once_with("test-0", self.jhelper)

    @patch("sunbeam.steps.hypervisor.remove_hypervisor")
    @patch("sunbeam.steps.hypervisor.guests_on_hypervisor")
    def test_run_application_not_found(self, guests_on_hypervisor, remove_hypervisor):
        guests_on_hypervisor.return_value = []
        self.jhelper.remove_unit.side_effect = ApplicationNotFoundException(
            "Application missing..."
        )

        step = RemoveHypervisorUnitStep(
            self.client, self.name, self.jhelper, "test-model"
        )
        result = step.run()

        self.jhelper.remove_unit.assert_called_once()
        assert result.result_type == ResultType.FAILED
        assert result.message == "Application missing..."

    @patch("sunbeam.steps.hypervisor.remove_hypervisor")
    @patch("sunbeam.steps.hypervisor.guests_on_hypervisor")
    def test_run_timeout(self, guests_on_hypervisor, remove_hypervisor):
        guests_on_hypervisor.return_value = []
        self.jhelper.wait_application_ready.side_effect = TimeoutException("timed out")

        step = RemoveHypervisorUnitStep(
            self.client, self.name, self.jhelper, "test-model"
        )
        result = step.run()

        self.jhelper.wait_application_ready.assert_called_once()
        assert result.result_type == ResultType.FAILED
        assert result.message == "timed out"


class TestReapplyHypervisorTerraformPlanStep(unittest.TestCase):
    def __init__(self, methodName: str = "runTest") -> None:
        super().__init__(methodName)
        self.read_config = patch(
            "sunbeam.steps.hypervisor.read_config",
            Mock(
                return_value={
                    "openstack_model": "openstack",
                }
            ),
        )
        self.get_network_config = patch(
            "sunbeam.steps.hypervisor.get_external_network_configs",
            Mock(return_value={}),
        )

    def setUp(self):
        self.client = Mock()
        self.client.cluster.list_nodes_by_role.return_value = []
        self.read_config.start()
        self.get_network_config.start()
        self.tfhelper = Mock()
        self.jhelper = AsyncMock()
        self.manifest = Mock()

    def tearDown(self):
        self.read_config.stop()
        self.get_network_config.stop()

    def test_is_skip(self):
        self.client.cluster.list_nodes_by_role.return_value = ["node-1"]
        step = ReapplyHypervisorTerraformPlanStep(
            self.client, self.tfhelper, self.jhelper, self.manifest, "test-model"
        )
        result = step.is_skip()

        assert result.result_type == ResultType.COMPLETED

    def test_run_pristine_installation(self):
        self.jhelper.get_application.side_effect = ApplicationNotFoundException(
            "not found"
        )

        step = ReapplyHypervisorTerraformPlanStep(
            self.client, self.tfhelper, self.jhelper, self.manifest, "test-model"
        )
        result = step.run()

        self.tfhelper.update_tfvars_and_apply_tf.assert_called_once()
        assert result.result_type == ResultType.COMPLETED

    @patch("sunbeam.steps.hypervisor.get_external_network_configs")
    def test_run_after_configure_step(self, get_external_network_configs):
        # This is a case where external network configs are already added
        # and Reapply terraform plan is called.
        # Check if override_tfvars contain external network configs
        # previously added
        network_config_tfvars = {
            "external-bridge": "br-ex",
            "external-bridge-address": "172.16.2.1/24",
            "physnet-name": "physnet1",
        }
        get_external_network_configs.return_value = network_config_tfvars
        step = ReapplyHypervisorTerraformPlanStep(
            self.client, self.tfhelper, self.jhelper, self.manifest, "test-model"
        )
        result = step.run()

        self.tfhelper.update_tfvars_and_apply_tf.assert_called_once()
        expected_override_tfvars = {"charm_config": network_config_tfvars}
        override_tfvars_from_mock_call = (
            self.tfhelper.update_tfvars_and_apply_tf.call_args.kwargs.get(
                "override_tfvars", {}
            )
        )
        assert override_tfvars_from_mock_call == expected_override_tfvars
        assert result.result_type == ResultType.COMPLETED

    def test_run_tf_apply_failed(self):
        self.tfhelper.update_tfvars_and_apply_tf.side_effect = TerraformException(
            "apply failed..."
        )

        step = ReapplyHypervisorTerraformPlanStep(
            self.client, self.tfhelper, self.jhelper, self.manifest, "test-model"
        )
        result = step.run()

        self.tfhelper.update_tfvars_and_apply_tf.assert_called_once()
        assert result.result_type == ResultType.FAILED
        assert result.message == "apply failed..."

    def test_run_waiting_timed_out(self):
        self.jhelper.wait_application_ready.side_effect = TimeoutException("timed out")

        step = ReapplyHypervisorTerraformPlanStep(
            self.client, self.tfhelper, self.jhelper, self.manifest, "test-model"
        )
        result = step.run()

        self.jhelper.wait_application_ready.assert_called_once()
        assert result.result_type == ResultType.FAILED
        assert result.message == "timed out"
