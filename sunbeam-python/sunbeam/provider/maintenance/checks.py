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

from rich.console import Console

from sunbeam.core.checks import Check
from sunbeam.core.juju import JujuHelper
from sunbeam.core.openstack_api import (
    get_admin_connection,
    guests_on_hypervisor,
)

console = Console()
LOG = logging.getLogger(__name__)


class InstancesStatusCheck(Check):
    def __init__(self, jhelper: JujuHelper, node: str, force: bool):
        super().__init__(
            "Check no instance in ERROR/MIGRATING status on nodes",
            "Checking if there are any instance in ERROR/MIGRATING status on nodes",
        )
        self.jhelper = jhelper
        self.node = node
        self.force = force

    def run(self) -> bool:
        """Run the check logic here.

        Return True if check is Ok.
        Otherwise update self.message and return False.
        """
        conn = get_admin_connection(jhelper=self.jhelper)

        not_expected_status_instances: dict[str, str] = {}

        for status in ["ERROR", "MIGRATING"]:
            for inst in guests_on_hypervisor(
                hypervisor_name=self.node,
                conn=conn,
                status=status,
            ):
                not_expected_status_instances[inst.id] = status

        if not_expected_status_instances:
            _msg = f"Instances not in expected status: {not_expected_status_instances}"
            if self.force:
                LOG.warning(f"Ignore issue: {_msg}")
                return True
            self.message = _msg
            return False
        return True


class NoEphemeralDiskCheck(Check):
    def __init__(self, jhelper: JujuHelper, node: str, force: bool):
        super().__init__(
            "Check no instance using ephemeral disk",
            "Checking if there are any instance is using ephemeral disk",
        )
        self.jhelper = jhelper
        self.node = node
        self.force = force

    def run(self) -> bool:
        """Run the check logic here.

        Return True if check is Ok.
        Otherwise update self.message and return False.
        """
        conn = get_admin_connection(jhelper=self.jhelper)

        unexpected_instances = []

        for inst in guests_on_hypervisor(
            hypervisor_name=self.node,
            conn=conn,
        ):
            flavor = conn.compute.find_flavor(inst.flavor.get("id"))
            if flavor.ephemeral > 0:
                unexpected_instances.append(inst.id)
        if unexpected_instances:
            _msg = f"Instances have ephemeral disk: {unexpected_instances}"
            if self.force:
                LOG.warning(f"Ignore issue: {_msg}")
                return True
            self.message = _msg
            return False
        return True


class NoInstancesOnNodeCheck(Check):
    def __init__(self, jhelper: JujuHelper, node: str, force: bool):
        super().__init__(
            "Check no instance on the node",
            "Check no instance on the node",
        )
        self.jhelper = jhelper
        self.node = node
        self.force = force

    def run(self) -> bool:
        """Run the check logic here.

        Return True if check is Ok.
        Otherwise update self.message and return False.
        """
        conn = get_admin_connection(jhelper=self.jhelper)

        instances = guests_on_hypervisor(hypervisor_name=self.node, conn=conn)

        if len(instances) > 0:
            instance_ids = ",".join([inst.id for inst in instances])
            _msg = f"Instances {instance_ids} still on node {self.node}"
            if self.force:
                LOG.warning(f"Ignore issue: {_msg}")
                return True
            self.message = _msg
            return False
        return True


class NovaInDisableStatusCheck(Check):
    def __init__(self, jhelper: JujuHelper, node: str, force: bool):
        super().__init__(
            "Check nova compute is disable on the node",
            "Check nova compute is disable on the node",
        )
        self.jhelper = jhelper
        self.node = node
        self.force = force

    def run(self) -> bool:
        """Run the check logic here.

        Return True if check is Ok.
        Otherwise update self.message and return False.
        """
        conn = get_admin_connection(jhelper=self.jhelper)

        expected_services = []
        for svc in conn.compute.services(
            binary="nova-compute", host=self.node, status="disabled"
        ):
            expected_services.append(svc.id)

        if not len(expected_services) == 1:
            _msg = f"Nova compute still not disabled on node {self.node}"
            if self.force:
                LOG.warning(f"Ignore issue: {_msg}")
                return True
            self.message = _msg
            return False
        return True
