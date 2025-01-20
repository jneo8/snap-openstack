# Copyright (c) 2024 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
from abc import ABC, abstractmethod
from typing import Any

import tenacity
from rich.status import Status
from watcherclient import v1 as watcher
from watcherclient.v1 import client as watcher_client

from sunbeam.clusterd.client import Client
from sunbeam.core import watcher as watcher_helper
from sunbeam.core.common import BaseStep, Result, ResultType, SunbeamException
from sunbeam.core.deployment import Deployment
from sunbeam.core.juju import (
    ActionFailedException,
    JujuHelper,
    UnitNotFoundException,
    run_sync,
)
from sunbeam.core.watcher import WatcherActionFailedException
from sunbeam.steps.microceph import APPLICATION as _MICROCEPH_APPLICATION

LOG = logging.getLogger(__name__)


class MicroCephActionStep(BaseStep):
    def __init__(
        self,
        client: Client,
        jhelper: JujuHelper,
        node: str,
        model: str,
        action_name: str,
        action_params: dict[str, Any],
    ):
        name = f"Run action {action_name} on microceph node {node}"
        description = f"Run action {action_name} on microceph node {node}"
        super().__init__(name, description)

        self.client = client
        self.node = node
        self.jhelper = jhelper
        self.model = model
        self.action_name = action_name
        self.action_params = action_params

    def _get_unit(self):
        node_info = self.client.cluster.get_node_info(self.node)
        machine_id = str(node_info.get("machineid"))
        unit = run_sync(
            self.jhelper.get_unit_from_machine(
                _MICROCEPH_APPLICATION, machine_id, self.model
            )
        )
        return unit

    def run(self, status: Status | None = None) -> Result:
        """Run charm microceph action."""
        failed: bool = False
        message: str = ""
        try:
            unit = self._get_unit()
            LOG.debug(f"Running action {self.action_name} on {unit.entity_id}")

            action_result = run_sync(
                self.jhelper.run_action(
                    unit.entity_id,
                    self.model,
                    self.action_name,
                    action_params=self.action_params,
                )
            )
            LOG.debug(
                f"Result after running action {self.action_name}: {action_result}"
            )
        except UnitNotFoundException as e:
            message = f"Microceph node {self.node} not found: {str(e)}"
            failed = True
        except ActionFailedException as e:
            message = e.action_result
            failed = True

        if failed:
            return Result(ResultType.FAILED, message)
        return Result(ResultType.COMPLETED, action_result)


class CreateWatcherAuditStepABC(ABC, BaseStep):
    def __init__(
        self,
        deployment: Deployment,
        node: str,
    ):
        super().__init__(self.name, self.description)
        self.node = node
        self.client: watcher_client.Client = watcher_helper.get_watcher_client(
            deployment=deployment
        )

    @abstractmethod
    def _create_audit(self) -> watcher.Audit:
        """Create Watcher audit."""
        raise NotImplementedError

    def _get_actions(self, audit: watcher.Audit) -> list[watcher.Action]:
        return watcher_helper.get_actions(client=self.client, audit=audit)

    def run(self, status: Status | None) -> Result:
        """Create Watcher audit."""
        try:
            audit = self._create_audit()
            actions = self._get_actions(audit)
        except tenacity.RetryError as e:
            LOG.warning(e)
            return Result(ResultType.FAILED, "Unable to create Watcher audit")
        return Result(
            ResultType.COMPLETED,
            {
                "audit": audit,
                "actions": actions,
            },
        )


class CreateWatcherHostMaintenanceAuditStep(CreateWatcherAuditStepABC):
    name = "Create Watcher Host maintenance audit"
    description = "Create Watcher Host maintenance audit"

    def _create_audit(self) -> watcher.Audit:
        audit_template = watcher_helper.get_enable_maintenance_audit_template(
            client=self.client
        )
        return watcher_helper.create_audit(
            client=self.client,
            template=audit_template,
            parameters={"maintenance_node": self.node},
        )


class CreateWatcherWorkloadBalancingAuditStep(CreateWatcherAuditStepABC):
    name = "Create Watcher workload balancing audit"
    description = "Create Watcher workload balancing audit"

    def _create_audit(self) -> watcher.Audit:
        audit_template = watcher_helper.get_workload_balancing_audit_template(
            client=self.client
        )
        return watcher_helper.create_audit(
            client=self.client,
            template=audit_template,
        )


class RunWatcherAuditStep(BaseStep):
    name = "Start Watcher Audit's action plan"
    description = "Start Watcher Audit's action plan"

    def __init__(
        self,
        deployment: Deployment,
        node: str,
        audit: watcher.Audit,
    ):
        self.node = node
        super().__init__(self.name, self.description)
        self.client: watcher_client.Client = watcher_helper.get_watcher_client(
            deployment=deployment
        )
        self.audit = audit

    def run(self, status: Status | None) -> Result:
        """Execute Watcher Audit's Action Plan."""
        failed = False
        try:
            watcher_helper.exec_audit(self.client, self.audit)
            watcher_helper.wait_until_action_state(
                step=self,
                audit=self.audit,
                client=self.client,
                status=status,
            )
        except (
            SunbeamException,
            tenacity.RetryError,
            WatcherActionFailedException,
        ) as e:
            LOG.warning(e)
            failed = True

        actions = watcher_helper.get_actions(client=self.client, audit=self.audit)
        return Result(
            ResultType.COMPLETED if not failed else ResultType.FAILED,
            actions,
        )
