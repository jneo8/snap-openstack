# Copyright (c) 2024 Canonical Ltd.
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

from unittest.mock import Mock, patch

import pytest
import tenacity
from watcherclient import v1 as watcher

from sunbeam.core.common import ResultType, SunbeamException
from sunbeam.core.juju import ActionFailedException, UnitNotFoundException
from sunbeam.steps.maintenance import (
    CreateWatcherAuditStepABC,
    CreateWatcherHostMaintenanceAuditStep,
    CreateWatcherWorkloadBalancingAuditStep,
    MicroCephActionStep,
    RunWatcherAuditStep,
)
from sunbeam.steps.microceph import APPLICATION as _MICROCEPH_APPLICATION


@pytest.fixture(autouse=True)
def mock_watcher_helper():
    with patch("sunbeam.steps.maintenance.watcher_helper") as mock:
        yield mock


@pytest.fixture
def mock_watcher_client(mock_watcher_helper):
    mock_client = Mock()
    mock_watcher_helper.get_watcher_client.return_value = mock_client
    yield mock_client


class DummyCreateWatcherAuditStepABC(CreateWatcherAuditStepABC):
    name = "fake-name"
    description = "fake-desc"

    def __init__(self, mock_deployment, node):
        self.mock_audit = Mock()
        super().__init__(mock_deployment, node)

    def _create_audit(self) -> watcher.Audit:
        return self.mock_audit


class TestCreateWatcherAuditStepABC:
    def test_init(self, mock_watcher_helper):
        mock_deployment = Mock()
        DummyCreateWatcherAuditStepABC(mock_deployment, "fake-node")
        mock_watcher_helper.get_watcher_client.assert_called_once_with(
            deployment=mock_deployment
        )

    def test_get_actions(self, mock_watcher_helper, mock_watcher_client):
        step = DummyCreateWatcherAuditStepABC(Mock(), "fake-node")
        step._get_actions("fake-audit")
        mock_watcher_helper.get_actions.assert_called_once_with(
            client=mock_watcher_client, audit="fake-audit"
        )

    def test_run(self, mock_watcher_helper):
        step = DummyCreateWatcherAuditStepABC(Mock(), "fake-node")
        step._get_actions = Mock()
        result = step.run(Mock())
        assert result.result_type == ResultType.COMPLETED
        assert result.message == {
            "audit": step.mock_audit,
            "actions": step._get_actions.return_value,
        }

    def test_run_failed(self, mock_watcher_helper):
        step = DummyCreateWatcherAuditStepABC(Mock(), "fake-node")
        step._get_actions = Mock()
        step._get_actions.side_effect = tenacity.RetryError(Mock())
        result = step.run(Mock())

        assert result.result_type == ResultType.FAILED


class TestMicroCephActionStep:
    @patch("sunbeam.steps.maintenance.run_sync")
    def test_get_unit(self, mock_run_sync):
        mock_client = Mock()
        mock_jhelper = Mock()

        step = MicroCephActionStep(
            mock_client,
            mock_jhelper,
            "fake-node",
            "fake-model",
            "fake-action-name",
            {"param1": "val1", "param2": "val2"},
        )
        mock_client.cluster.get_node_info.return_value = {"machineid": 1001}
        step._get_unit()
        mock_client.cluster.get_node_info.assert_called_once_with("fake-node")
        mock_jhelper.get_unit_from_machine.assert_called_once_with(
            _MICROCEPH_APPLICATION, "1001", "fake-model"
        )

    @patch("sunbeam.steps.maintenance.run_sync")
    def test_run(self, mock_run_sync):
        mock_client = Mock()
        mock_jhelper = Mock()
        mock_unit = Mock()

        step = MicroCephActionStep(
            mock_client,
            mock_jhelper,
            "fake-node",
            "fake-model",
            "fake-action-name",
            {"param1": "val1", "param2": "val2"},
        )
        step._get_unit = Mock()
        step._get_unit.return_value = mock_unit

        result = step.run(Mock())
        mock_jhelper.run_action.assert_called_once_with(
            mock_unit.entity_id,
            "fake-model",
            "fake-action-name",
            action_params={"param1": "val1", "param2": "val2"},
        )
        mock_run_sync.assert_called_once_with(mock_jhelper.run_action.return_value)
        assert result.result_type == ResultType.COMPLETED
        assert result.message == mock_run_sync.return_value

    def test_run_unit_not_found_exception(self):
        mock_client = Mock()
        mock_jhelper = Mock()

        step = MicroCephActionStep(
            mock_client,
            mock_jhelper,
            "fake-node",
            "fake-model",
            "fake-action-name",
            {"param1": "val1", "param2": "val2"},
        )
        step._get_unit = Mock()
        step._get_unit.side_effect = UnitNotFoundException

        result = step.run(Mock())
        assert result.result_type == ResultType.FAILED

    def test_run_action_failed_exception(self):
        mock_client = Mock()
        mock_jhelper = Mock()
        mock_action_result = Mock()

        step = MicroCephActionStep(
            mock_client,
            mock_jhelper,
            "fake-node",
            "fake-model",
            "fake-action-name",
            {"param1": "val1", "param2": "val2"},
        )
        step._get_unit = Mock()
        step._get_unit.side_effect = ActionFailedException(mock_action_result)

        result = step.run(Mock())
        assert result.result_type == ResultType.FAILED
        assert result.message == mock_action_result


class TestCreateWatcherHostMaintenanceAuditStep:
    def test_create_audit(self, mock_watcher_helper, mock_watcher_client):
        step = CreateWatcherHostMaintenanceAuditStep(Mock(), "fake-node")
        result = step._create_audit()
        assert result == mock_watcher_helper.create_audit.return_value
        mock_watcher_helper.get_enable_maintenance_audit_template.assert_called_once_with(
            client=mock_watcher_client
        )
        mock_watcher_helper.create_audit.assert_called_once_with(
            client=mock_watcher_client,
            template=mock_watcher_helper.get_enable_maintenance_audit_template.return_value,
            parameters={"maintenance_node": "fake-node"},
        )


class TestCreateWatcherWorkloadBalancingAuditStep:
    def test_create_audit(self, mock_watcher_helper, mock_watcher_client):
        step = CreateWatcherWorkloadBalancingAuditStep(Mock(), "fake-node")
        result = step._create_audit()
        assert result == mock_watcher_helper.create_audit.return_value
        mock_watcher_helper.get_workload_balancing_audit_template.assert_called_once_with(
            client=mock_watcher_client
        )
        mock_watcher_helper.create_audit.assert_called_once_with(
            client=mock_watcher_client,
            template=mock_watcher_helper.get_workload_balancing_audit_template.return_value,
        )


class TestRunWatcherAuditStep:
    def test_run(self, mock_watcher_helper, mock_watcher_client):
        mock_audit = Mock()
        mock_status = Mock()
        step = RunWatcherAuditStep(Mock(), "fake-node", mock_audit)

        result = step.run(mock_status)
        assert result.result_type == ResultType.COMPLETED
        assert result.message == mock_watcher_helper.get_actions.return_value

        mock_watcher_helper.exec_audit.assert_called_once_with(
            mock_watcher_client, mock_audit
        )
        mock_watcher_helper.wait_until_action_state.assert_called_once_with(
            step=step,
            audit=mock_audit,
            client=mock_watcher_client,
            status=mock_status,
        )
        mock_watcher_helper.get_actions.assert_called_once_with(
            client=mock_watcher_client, audit=mock_audit
        )

    def test_run_failed(self, mock_watcher_helper, mock_watcher_client):
        mock_audit = Mock()
        mock_status = Mock()
        mock_deployment = Mock()

        # Mock helper methods
        mock_watcher_helper.exec_audit.side_effect = SunbeamException(
            "Execution failed"
        )
        mock_watcher_helper.get_actions.return_value = "mock-actions"

        step = RunWatcherAuditStep(mock_deployment, "fake-node", mock_audit)

        # Call the method under test
        result = step.run(mock_status)

        # Assertions
        assert result.result_type == ResultType.FAILED
        assert result.message == "mock-actions"

        mock_watcher_helper.exec_audit.assert_called_once_with(
            mock_watcher_client, mock_audit
        )
        mock_watcher_helper.wait_until_action_state.assert_not_called()
        mock_watcher_helper.get_actions.assert_called_once_with(
            client=mock_watcher_client, audit=mock_audit
        )
