# Copyright (c) 2023 Canonical Ltd.
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

import json
import logging
import traceback

import openstack
from rich.status import Status

from sunbeam.clusterd.client import Client
from sunbeam.clusterd.service import (
    ConfigItemNotFoundException,
    NodeNotExistInClusterException,
)
from sunbeam.commands.configure import get_external_network_configs
from sunbeam.core.common import BaseStep, Result, ResultType, read_config, update_config
from sunbeam.core.deployment import Deployment, Networks
from sunbeam.core.juju import (
    ActionFailedException,
    ApplicationNotFoundException,
    JujuHelper,
    JujuStepHelper,
    TimeoutException,
    run_sync,
)
from sunbeam.core.manifest import Manifest
from sunbeam.core.openstack import OPENSTACK_MODEL
from sunbeam.core.openstack_api import remove_hypervisor
from sunbeam.core.steps import (
    AddMachineUnitsStep,
    DeployMachineApplicationStep,
    DestroyMachineApplicationStep,
)
from sunbeam.core.terraform import TerraformException, TerraformHelper

LOG = logging.getLogger(__name__)
CONFIG_KEY = "TerraformVarsHypervisor"
APPLICATION = "openstack-hypervisor"
HYPERVISOR_APP_TIMEOUT = 180  # 3 minutes, managing the application should be fast
HYPERVISOR_DESTROY_TIMEOUT = 600
HYPERVISOR_UNIT_TIMEOUT = (
    1800  # 30 minutes, adding / removing units can take a long time
)


class DeployHypervisorApplicationStep(DeployMachineApplicationStep):
    """Deploy openstack-hyervisor application using Terraform cloud."""

    _CONFIG = CONFIG_KEY

    def __init__(
        self,
        deployment: Deployment,
        client: Client,
        tfhelper: TerraformHelper,
        openstack_tfhelper: TerraformHelper,
        jhelper: JujuHelper,
        manifest: Manifest,
        model: str,
    ):
        super().__init__(
            deployment,
            client,
            tfhelper,
            jhelper,
            manifest,
            CONFIG_KEY,
            APPLICATION,
            model,
            "Deploy OpenStack Hypervisor",
            "Deploying OpenStack Hypervisor",
        )
        self.openstack_tfhelper = openstack_tfhelper
        self.openstack_model = OPENSTACK_MODEL

    def extra_tfvars(self) -> dict:
        """Extra terraform vars to pass to terraform apply."""
        openstack_tf_output = self.openstack_tfhelper.output()

        # Always pass Offer URLs as extravars instead of terraform backend
        # so that sunbeam has control to remove the CMR integrations by passing
        # null value.
        # If offer URL is retrieved directly by terraform plan itself from
        # openstack backend, removing CMR integration results in errros.
        # see https://bugs.launchpad.net/juju/+bug/2085310

        juju_offers = {
            "rabbitmq-offer-url",
            "keystone-offer-url",
            "cert-distributor-offer-url",
            "ca-offer-url",
            "ovn-relay-offer-url",
            "cinder-ceph-offer-url",
            "nova-offer-url",
        }
        extra_tfvars = {offer: openstack_tf_output.get(offer) for offer in juju_offers}

        extra_tfvars.update(
            {
                "openstack_model": self.openstack_model,
                "endpoint_bindings": [
                    {"space": self.deployment.get_space(Networks.MANAGEMENT)},
                    {
                        "endpoint": "ceph-access",
                        "space": self.deployment.get_space(Networks.STORAGE),
                    },
                    {
                        "endpoint": "migration",
                        "space": self.deployment.get_space(Networks.DATA),
                    },
                    {
                        "endpoint": "data",
                        "space": self.deployment.get_space(Networks.DATA),
                    },
                    {
                        "endpoint": "amqp",
                        "space": self.deployment.get_space(Networks.INTERNAL),
                    },
                    {
                        "endpoint": "ceilometer-service",
                        "space": self.deployment.get_space(Networks.INTERNAL),
                    },
                    {
                        "endpoint": "certificates",
                        "space": self.deployment.get_space(Networks.INTERNAL),
                    },
                    {
                        "endpoint": "cos-agent",
                        "space": self.deployment.get_space(Networks.INTERNAL),
                    },
                    {
                        "endpoint": "identity-credentials",
                        "space": self.deployment.get_space(Networks.INTERNAL),
                    },
                    {
                        "endpoint": "nova-service",
                        "space": self.deployment.get_space(Networks.INTERNAL),
                    },
                    {
                        "endpoint": "ovsdb-cms",
                        "space": self.deployment.get_space(Networks.INTERNAL),
                    },
                    {
                        "endpoint": "receive-ca-cert",
                        "space": self.deployment.get_space(Networks.INTERNAL),
                    },
                ],
            }
        )

        return extra_tfvars

    def get_application_timeout(self) -> int:
        """Return application timeout in seconds."""
        return HYPERVISOR_APP_TIMEOUT


class AddHypervisorUnitsStep(AddMachineUnitsStep):
    def __init__(
        self,
        client: Client,
        names: list[str] | str,
        jhelper: JujuHelper,
        model: str,
    ):
        super().__init__(
            client,
            names,
            jhelper,
            CONFIG_KEY,
            APPLICATION,
            model,
            "Add Openstack-Hypervisor unit(s)",
            "Adding Openstack Hypervisor unit to machine(s)",
        )

    def get_accepted_unit_status(self) -> dict[str, list[str]]:
        """Accepted status to pass wait_units_ready function."""
        workload_statuses = ["active"]
        if len(self.client.cluster.list_nodes_by_role("storage")) < 1:
            LOG.debug("No storage nodes found, allowing hypervisor waiting status")
            workload_statuses.append("waiting")
        return {"agent": ["idle"], "workload": workload_statuses}

    def get_unit_timeout(self) -> int:
        """Return unit timeout in seconds."""
        return HYPERVISOR_UNIT_TIMEOUT


class RemoveHypervisorUnitStep(BaseStep, JujuStepHelper):
    def __init__(
        self,
        client: Client,
        name: str,
        jhelper: JujuHelper,
        model: str,
        force: bool = False,
    ):
        super().__init__(
            "Remove openstack-hypervisor unit",
            "Remove openstack-hypervisor unit from machine",
        )
        self.client = client
        self.name = name
        self.jhelper = jhelper
        self.model = model
        self.force = force
        self.unit = None
        self.machine_id = ""

    def is_skip(self, status: Status | None = None) -> Result:
        """Determines if the step should be skipped or not.

        :return: ResultType.SKIPPED if the Step should be skipped,
                ResultType.COMPLETED or ResultType.FAILED otherwise
        """
        try:
            node = self.client.cluster.get_node_info(self.name)
            self.machine_id = str(node.get("machineid"))
        except NodeNotExistInClusterException:
            LOG.debug(f"Machine {self.name} does not exist, skipping.")
            return Result(ResultType.SKIPPED)

        try:
            application = run_sync(
                self.jhelper.get_application(APPLICATION, self.model)
            )
        except ApplicationNotFoundException as e:
            LOG.debug(str(e))
            return Result(
                ResultType.SKIPPED, "Hypervisor application has not been deployed yet"
            )

        for unit in application.units:
            if unit.machine.id == self.machine_id:
                LOG.debug(f"Unit {unit.name} is deployed on machine: {self.machine_id}")
                self.unit = unit.name
                break
        if not self.unit:
            LOG.debug(f"Unit is not deployed on machine: {self.machine_id}, skipping.")
            return Result(ResultType.SKIPPED)
        try:
            results = run_sync(
                self.jhelper.run_action(self.unit, self.model, "running-guests")
            )
        except ActionFailedException:
            LOG.debug("Failed to run action on hypervisor unit", exc_info=True)
            return Result(ResultType.FAILED, "Failed to run action on hypervisor unit")

        if results.get("return-code", 0) > 1:
            _message = "Failed to run action on hypervisor unit"
            return Result(ResultType.FAILED, _message)

        if result := results.get("result"):
            guests = json.loads(result)
            LOG.debug(f"Found guests on hypervisor: {guests}")
            if guests and not self.force:
                return Result(
                    ResultType.FAILED,
                    "Guests are running on hypervisor, aborting",
                )
        return Result(ResultType.COMPLETED)

    def remove_machine_id_from_tfvar(self) -> None:
        """Remove machine if from terraform vars saved in cluster db."""
        try:
            tfvars = read_config(self.client, CONFIG_KEY)
        except ConfigItemNotFoundException:
            tfvars = {}

        machine_ids = tfvars.get("machine_ids", [])
        if self.machine_id in machine_ids:
            machine_ids.remove(self.machine_id)
            tfvars.update({"machine_ids": machine_ids})
            update_config(self.client, CONFIG_KEY, tfvars)

    def run(self, status: Status | None = None) -> Result:
        """Remove unit from openstack-hypervisor application on Juju model."""
        if not self.unit:
            return Result(ResultType.FAILED, "Unit not found on machine")
        try:
            run_sync(self.jhelper.run_action(self.unit, self.model, "disable"))
        except ActionFailedException as e:
            LOG.debug(str(e))
            return Result(ResultType.FAILED, "Failed to disable hypervisor unit")
        try:
            run_sync(self.jhelper.remove_unit(APPLICATION, self.unit, self.model))
            self.remove_machine_id_from_tfvar()
            run_sync(
                self.jhelper.wait_units_gone(
                    [self.unit],
                    self.model,
                    timeout=HYPERVISOR_UNIT_TIMEOUT,
                )
            )
            run_sync(
                self.jhelper.wait_application_ready(
                    APPLICATION,
                    self.model,
                    accepted_status=["active", "unknown"],
                    timeout=HYPERVISOR_UNIT_TIMEOUT,
                )
            )
        except (ApplicationNotFoundException, TimeoutException) as e:
            LOG.warning(str(e))
            return Result(ResultType.FAILED, str(e))
        try:
            remove_hypervisor(self.name, self.jhelper)
        except openstack.exceptions.SDKException as e:
            LOG.error(
                "Encountered error removing hypervisor references from control plane."
            )
            if self.force:
                LOG.warning("Force mode set, ignoring exception:")
                traceback.print_exception(e)
            else:
                return Result(ResultType.FAILED, str(e))

        return Result(ResultType.COMPLETED)


class ReapplyHypervisorTerraformPlanStep(BaseStep):
    """Reapply openstack-hyervisor terraform plan."""

    _CONFIG = CONFIG_KEY

    def __init__(
        self,
        client: Client,
        tfhelper: TerraformHelper,
        jhelper: JujuHelper,
        manifest: Manifest,
        model: str,
        extra_tfvars: dict = {},
    ):
        super().__init__(
            "Reapply OpenStack Hypervisor Terraform plan",
            "Reapply OpenStack Hypervisor Terraform plan",
        )
        self.client = client
        self.tfhelper = tfhelper
        self.jhelper = jhelper
        self.manifest = manifest
        self.model = model
        self.extra_tfvars = extra_tfvars

    def is_skip(self, status: Status | None = None) -> Result:
        """Determines if the step should be skipped or not.

        :return: ResultType.SKIPPED if the Step should be skipped,
                ResultType.COMPLETED or ResultType.FAILED otherwise
        """
        if self.client.cluster.list_nodes_by_role("compute"):
            return Result(ResultType.COMPLETED)

        return Result(ResultType.SKIPPED)

    def run(self, status: Status | None = None) -> Result:
        """Apply terraform configuration to deploy hypervisor."""
        # Apply Network configs everytime reapply is called
        network_configs = get_external_network_configs(self.client)
        if network_configs:
            LOG.debug(
                "Add external network configs from DemoSetup to extra tfvars: "
                f"{network_configs}"
            )
            self.extra_tfvars.update({"charm_config": network_configs})

        statuses = ["active", "unknown"]
        if len(self.client.cluster.list_nodes_by_role("storage")) < 1:
            LOG.debug("No storage nodes found, allowing hypervisor waiting status")
            statuses.append("waiting")
        try:
            self.tfhelper.update_tfvars_and_apply_tf(
                self.client,
                self.manifest,
                tfvar_config=self._CONFIG,
                override_tfvars=self.extra_tfvars,
            )
        except TerraformException as e:
            return Result(ResultType.FAILED, str(e))

        try:
            run_sync(
                self.jhelper.wait_application_ready(
                    APPLICATION,
                    self.model,
                    accepted_status=statuses,
                    timeout=HYPERVISOR_APP_TIMEOUT,
                )
            )
        except TimeoutException as e:
            LOG.warning(str(e))
            return Result(ResultType.FAILED, str(e))

        return Result(ResultType.COMPLETED)


class DestroyHypervisorApplicationStep(DestroyMachineApplicationStep):
    """Destroy Hypervisor application using Terraform."""

    def __init__(
        self,
        client: Client,
        tfhelper: TerraformHelper,
        jhelper: JujuHelper,
        manifest: Manifest,
        model: str,
    ):
        super().__init__(
            client,
            tfhelper,
            jhelper,
            manifest,
            CONFIG_KEY,
            [APPLICATION],
            model,
            "Destroy Hypervisor",
            "Destroying Hypervisor",
        )

    def get_application_timeout(self) -> int:
        """Return application timeout in seconds."""
        return HYPERVISOR_DESTROY_TIMEOUT


class EnableHypervisorStep(BaseStep, JujuStepHelper):
    """Enable hypervisor service."""

    def __init__(
        self,
        client: Client,
        node: str,
        jhelper: JujuHelper,
        model: str,
    ):
        super().__init__(
            "Enable hypervisor service",
            "Enable hypervisor service for unit",
        )
        self.client = client
        self.node = node
        self.jhelper = jhelper
        self.model = model
        self.unit = None
        self.machine_id = ""

    def is_skip(self, status: Status | None = None) -> Result:
        """Determines if the step should be skipped or not.

        :return: ResultType.SKIPPED if the Step should be skipped,
                ResultType.COMPLETED or ResultType.FAILED otherwise
        """
        try:
            node = self.client.cluster.get_node_info(self.node)
            self.machine_id = str(node.get("machineid"))
        except NodeNotExistInClusterException:
            LOG.debug(f"Machine {self.node} does not exist, skipping.")
            return Result(ResultType.SKIPPED)

        try:
            application = run_sync(
                self.jhelper.get_application(APPLICATION, self.model)
            )
        except ApplicationNotFoundException as e:
            LOG.debug(str(e))
            return Result(
                ResultType.SKIPPED, "Hypervisor application has not been deployed yet"
            )

        for unit in application.units:
            if unit.machine.id == self.machine_id:
                LOG.debug(f"Unit {unit.name} is deployed on machine: {self.machine_id}")
                self.unit = unit.name
                break
        if not self.unit:
            LOG.debug(f"Unit is not deployed on machine: {self.machine_id}, skipping.")
            return Result(ResultType.SKIPPED)
        return Result(ResultType.COMPLETED)

    def run(self, status: Status | None = None) -> Result:
        """Enable hypervisor service on node."""
        if not self.unit:
            return Result(ResultType.FAILED, "Unit not found on machine")
        try:
            run_sync(self.jhelper.run_action(self.unit, self.model, "enable"))
        except ActionFailedException as e:
            LOG.debug(str(e))
            return Result(
                ResultType.FAILED,
                f"Failed to enable hypervisor service for unit {self.unit}",
            )
        return Result(ResultType.COMPLETED)
