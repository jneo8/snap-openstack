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

import abc
import logging
from typing import Optional

from lightkube.config.kubeconfig import KubeConfig
from lightkube.core import exceptions
from lightkube.core.client import Client as KubeClient
from lightkube.core.exceptions import ApiError
from lightkube.resources.core_v1 import Service
from rich.status import Status

from sunbeam.clusterd.client import Client
from sunbeam.clusterd.service import (
    ConfigItemNotFoundException,
    NodeNotExistInClusterException,
)
from sunbeam.commands.terraform import TerraformException, TerraformHelper
from sunbeam.jobs.common import BaseStep, Result, ResultType, read_config, update_config
from sunbeam.jobs.deployment import Deployment
from sunbeam.jobs.juju import (
    ApplicationNotFoundException,
    JujuHelper,
    TimeoutException,
    run_sync,
)
from sunbeam.jobs.k8s import K8SHelper
from sunbeam.jobs.manifest import Manifest

LOG = logging.getLogger(__name__)


class DeployMachineApplicationStep(BaseStep):
    """Base class to deploy machine application using Terraform cloud."""

    def __init__(
        self,
        deployment: Deployment,
        client: Client,
        tfhelper: TerraformHelper,
        jhelper: JujuHelper,
        manifest: Manifest,
        config: str,
        application: str,
        model: str,
        banner: str = "",
        description: str = "",
        refresh: bool = False,
    ):
        super().__init__(banner, description)
        self.deployment = deployment
        self.client = client
        self.tfhelper = tfhelper
        self.jhelper = jhelper
        self.manifest = manifest
        self.config = config
        self.application = application
        self.model = model
        # Set refresh flag to True to redeploy the application
        self.refresh = refresh

    def extra_tfvars(self) -> dict:
        """Extra terraform vars to pass to terraform apply."""
        return {}

    def get_application_timeout(self) -> int:
        """Application timeout in seconds."""
        return 600

    def is_skip(self, status: Optional[Status] = None) -> Result:
        """Determines if the step should be skipped or not.

        :return: ResultType.SKIPPED if the Step should be skipped,
                ResultType.COMPLETED or ResultType.FAILED otherwise
        """
        if self.refresh:
            return Result(ResultType.COMPLETED)

        try:
            run_sync(self.jhelper.get_application(self.application, self.model))
        except ApplicationNotFoundException:
            return Result(ResultType.COMPLETED)

        return Result(ResultType.SKIPPED)

    def run(self, status: Optional[Status] = None) -> Result:
        """Apply terraform configuration to deploy sunbeam machine."""
        machine_ids = []
        try:
            app = run_sync(self.jhelper.get_application(self.application, self.model))
            machine_ids.extend(unit.machine.id for unit in app.units)
        except ApplicationNotFoundException as e:
            LOG.debug(str(e))

        try:
            extra_tfvars = self.extra_tfvars()
            extra_tfvars.update(
                {
                    "machine_ids": machine_ids,
                    "machine_model": self.model,
                }
            )
            self.tfhelper.update_tfvars_and_apply_tf(
                self.client,
                self.manifest,
                tfvar_config=self.config,
                override_tfvars=extra_tfvars,
            )
        except TerraformException as e:
            return Result(ResultType.FAILED, str(e))

        # Note(gboutry): application is in state unknown when it's deployed
        # without units
        try:
            run_sync(
                self.jhelper.wait_application_ready(
                    self.application,
                    self.model,
                    accepted_status=["active", "unknown"],
                    timeout=self.get_application_timeout(),
                )
            )
        except TimeoutException as e:
            LOG.warning(str(e))
            return Result(ResultType.FAILED, str(e))

        return Result(ResultType.COMPLETED)


class AddMachineUnitsStep(BaseStep):
    """Base class to add units of machine application."""

    def __init__(
        self,
        client: Client,
        names: list[str] | str,
        jhelper: JujuHelper,
        config: str,
        application: str,
        model: str,
        banner: str = "",
        description: str = "",
    ):
        super().__init__(banner, description)
        self.client = client
        if isinstance(names, str):
            names = [names]
        self.names = names
        self.jhelper = jhelper
        self.config = config
        self.application = application
        self.model = model
        self.to_deploy = set()

    def get_unit_timeout(self) -> int:
        """Return unit timeout in seconds."""
        return 600  # 10 minutes

    def is_skip(self, status: Optional[Status] = None) -> Result:
        """Determines if the step should be skipped or not.

        :return: ResultType.SKIPPED if the Step should be skipped,
                ResultType.COMPLETED or ResultType.FAILED otherwise
        """
        if len(self.names) == 0:
            return Result(ResultType.SKIPPED)
        nodes: list[dict] = self.client.cluster.list_nodes()

        filtered_nodes = list(filter(lambda node: node["name"] in self.names, nodes))
        if len(filtered_nodes) != len(self.names):
            filtered_node_names = [node["name"] for node in filtered_nodes]
            missing_nodes = set(self.names) - set(filtered_node_names)
            return Result(
                ResultType.FAILED,
                f"Nodes '{','.join(missing_nodes)}' do not exist in cluster database",
            )

        nodes_without_machine_id = []

        for node in filtered_nodes:
            node_machine_id = node.get("machineid", -1)
            if node_machine_id == -1:
                nodes_without_machine_id.append(node["name"])
                continue
            self.to_deploy.add(str(node_machine_id))

        if len(nodes_without_machine_id) > 0:
            return Result(
                ResultType.FAILED,
                f"Nodes '{','.join(nodes_without_machine_id)}' do not have machine id,"
                " are they deployed?",
            )
        try:
            app = run_sync(self.jhelper.get_application(self.application, self.model))
        except ApplicationNotFoundException:
            return Result(
                ResultType.FAILED,
                f"Application {self.application} has not been deployed",
            )

        deployed_units_machine_ids = {unit.machine.id for unit in app.units}
        self.to_deploy -= deployed_units_machine_ids
        if len(self.to_deploy) == 0:
            return Result(ResultType.SKIPPED, "No new units to deploy")

        return Result(ResultType.COMPLETED)

    def add_machine_id_to_tfvar(self) -> None:
        """Add machine id to terraform vars saved in cluster db."""
        try:
            tfvars = read_config(self.client, self.config)
        except ConfigItemNotFoundException:
            tfvars = {}

        machine_ids = set(tfvars.get("machine_ids", []))

        if len(self.to_deploy) > 0 and self.to_deploy.issubset(machine_ids):
            LOG.debug("All machine ids are already in tfvars, skipping update")
            return

        machine_ids.update(self.to_deploy)
        tfvars.update({"machine_ids": sorted(machine_ids)})
        update_config(self.client, self.config, tfvars)

    def get_accepted_unit_status(self) -> dict[str, list[str]]:
        """Accepted status to pass wait_units_ready function."""
        return {"agent": ["idle"], "workload": ["active"]}

    def run(self, status: Optional[Status] = None) -> Result:
        """Add unit to machine application on Juju model."""
        try:
            units = run_sync(
                self.jhelper.add_unit(
                    self.application, self.model, sorted(self.to_deploy)
                )
            )
            self.add_machine_id_to_tfvar()
            run_sync(
                self.jhelper.wait_units_ready(
                    units,
                    self.model,
                    accepted_status=self.get_accepted_unit_status(),
                    timeout=self.get_unit_timeout(),
                )
            )
        except (ApplicationNotFoundException, TimeoutException) as e:
            LOG.warning(str(e))
            return Result(ResultType.FAILED, str(e))

        return Result(ResultType.COMPLETED)


class RemoveMachineUnitStep(BaseStep):
    """Base class to remove unit of machine application."""

    def __init__(
        self,
        client: Client,
        name: str,
        jhelper: JujuHelper,
        config: str,
        application: str,
        model: str,
        banner: str = "",
        description: str = "",
    ):
        super().__init__(banner, description)
        self.client = client
        self.node_name = name
        self.jhelper = jhelper
        self.config = config
        self.application = application
        self.model = model
        self.machine_id = ""
        self.unit = None

    def get_unit_timeout(self) -> int:
        """Return unit timeout in seconds."""
        return 600  # 10 minutes

    def is_skip(self, status: Optional[Status] = None) -> Result:
        """Determines if the step should be skipped or not.

        :return: ResultType.SKIPPED if the Step should be skipped,
                ResultType.COMPLETED or ResultType.FAILED otherwise
        """
        try:
            node = self.client.cluster.get_node_info(self.node_name)
            self.machine_id = str(node.get("machineid"))
        except NodeNotExistInClusterException:
            LOG.debug(f"Machine {self.node_name} does not exist, skipping.")
            return Result(ResultType.SKIPPED)

        try:
            app = run_sync(self.jhelper.get_application(self.application, self.model))
        except ApplicationNotFoundException as e:
            LOG.debug(str(e))
            return Result(
                ResultType.SKIPPED,
                "Application {self.application} has not been deployed yet",
            )

        for unit in app.units:
            if unit.machine.id == self.machine_id:
                LOG.debug(f"Unit {unit.name} is deployed on machine: {self.machine_id}")
                self.unit = unit.name
                return Result(ResultType.COMPLETED)

        return Result(ResultType.SKIPPED)

    def run(self, status: Optional[Status] = None) -> Result:
        """Remove unit from machine application on Juju model."""
        try:
            run_sync(
                self.jhelper.remove_unit(self.application, str(self.unit), self.model)
            )
            run_sync(
                self.jhelper.wait_application_ready(
                    self.application,
                    self.model,
                    accepted_status=["active", "unknown"],
                    timeout=self.get_unit_timeout(),
                )
            )
        except (ApplicationNotFoundException, TimeoutException) as e:
            LOG.warning(str(e))
            return Result(ResultType.FAILED, str(e))

        return Result(ResultType.COMPLETED)


class PatchLoadBalancerServicesStep(BaseStep, abc.ABC):
    def __init__(
        self,
        client: Client,
    ):
        super().__init__(
            "Patch LoadBalancer services",
            "Patch LoadBalancer service annotations",
        )
        self.client = client
        self.lb_annotation = K8SHelper.get_loadbalancer_annotation()

    @abc.abstractmethod
    def services(self) -> list[str]:
        """List of services to patch."""
        pass

    @abc.abstractmethod
    def model(self) -> str:
        """Name of the model to use.

        This must resolve to a namespaces in the cluster.
        """
        pass

    def _get_service(self, service_name: str, find_lb: bool = True) -> Service:
        """Look up a service by name, optionally looking for a LoadBalancer service."""
        search_service = service_name
        if find_lb:
            search_service += "-lb"
        try:
            return self.kube.get(Service, search_service)
        except ApiError as e:
            if e.status.code == 404 and search_service.endswith("-lb"):
                return self._get_service(service_name, find_lb=False)
            raise e

    def is_skip(self, status: Optional[Status] = None) -> Result:
        """Determines if the step should be skipped or not.

        :return: ResultType.SKIPPED if the Step should be skipped,
                ResultType.COMPLETED or ResultType.FAILED otherwise
        """
        try:
            self.kubeconfig = read_config(self.client, K8SHelper.get_kubeconfig_key())
        except ConfigItemNotFoundException:
            LOG.debug("K8S kubeconfig not found", exc_info=True)
            return Result(ResultType.FAILED, "K8S kubeconfig not found")

        kubeconfig = KubeConfig.from_dict(self.kubeconfig)
        try:
            self.kube = KubeClient(kubeconfig, self.model(), trust_env=False)
        except exceptions.ConfigError as e:
            LOG.debug("Error creating k8s client", exc_info=True)
            return Result(ResultType.FAILED, str(e))

        for service_name in self.services():
            try:
                service = self._get_service(service_name, find_lb=True)
            except ApiError as e:
                return Result(ResultType.FAILED, str(e))
            if not service.metadata:
                return Result(
                    ResultType.FAILED, f"k8s service {service_name!r} has no metadata"
                )
            service_annotations = service.metadata.annotations
            if (
                service_annotations is None
                or self.lb_annotation not in service_annotations
            ):
                return Result(ResultType.COMPLETED)

        return Result(ResultType.SKIPPED)

    def run(self, status: Optional[Status] = None) -> Result:
        """Patch LoadBalancer services annotations with LB IP."""
        for service_name in self.services():
            try:
                service = self._get_service(service_name, find_lb=True)
            except ApiError as e:
                return Result(ResultType.FAILED, str(e))
            if not service.metadata:
                return Result(
                    ResultType.FAILED, f"k8s service {service_name!r} has no metadata"
                )
            service_name = str(service.metadata.name)
            service_annotations = service.metadata.annotations
            if service_annotations is None:
                service_annotations = {}
            if self.lb_annotation not in service_annotations:
                if not service.status:
                    return Result(
                        ResultType.FAILED, f"k8s service {service_name!r} has no status"
                    )
                if not service.status.loadBalancer:
                    return Result(
                        ResultType.FAILED,
                        f"k8s service {service_name!r} has no loadBalancer status",
                    )
                if not service.status.loadBalancer.ingress:
                    return Result(
                        ResultType.FAILED,
                        f"k8s service {service_name!r} has no loadBalancer ingress",
                    )
                loadbalancer_ip = service.status.loadBalancer.ingress[0].ip
                service_annotations[self.lb_annotation] = loadbalancer_ip
                service.metadata.annotations = service_annotations
                LOG.debug(f"Patching {service_name!r} to use IP {loadbalancer_ip!r}")
                self.kube.patch(Service, service_name, obj=service)

        return Result(ResultType.COMPLETED)
