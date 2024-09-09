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

import click
from packaging.version import Version

from sunbeam.core.deployment import Deployment
from sunbeam.core.manifest import CharmManifest, SoftwareConfig
from sunbeam.features.interface.v1.base import FeatureRequirement
from sunbeam.features.interface.v1.openstack import (
    OpenStackControlPlaneFeature,
    TerraformPlanLocation,
)
from sunbeam.versions import OPENSTACK_CHANNEL

LOG = logging.getLogger(__name__)


class ResourceOptimizationFeature(OpenStackControlPlaneFeature):
    version = Version("0.0.1")
    requires = {FeatureRequirement("telemetry")}

    def __init__(self, deployment: Deployment) -> None:
        super().__init__(
            "resource-optimization",
            deployment,
            tf_plan_location=TerraformPlanLocation.SUNBEAM_TERRAFORM_REPO,
        )

    def manifest_defaults(self) -> SoftwareConfig:
        """Feature software configuration."""
        return SoftwareConfig(
            charms={"watcher-k8s": CharmManifest(channel=OPENSTACK_CHANNEL)}
        )

    def manifest_attributes_tfvar_map(self) -> dict:
        """Manifest attributes terraformvars map."""
        return {
            self.tfplan: {
                "charms": {
                    "watcher-k8s": {
                        "channel": "watcher-channel",
                        "revision": "watcher-revision",
                        "config": "watcher-config",
                    }
                }
            }
        }

    def set_application_names(self) -> list:
        """Application names handled by the terraform plan."""
        apps = ["watcher-mysql-router"]
        if self.get_database_topology() == "multi":
            apps.extend(["watcher-mysql"])

        # If there is no storage role and gnocchi is deployed,
        # watcher will be in waiting state.
        if self.deployment.get_client().cluster.list_nodes_by_role("storage"):
            apps.extend(["watcher"])

        return apps

    def set_tfvars_on_enable(self) -> dict:
        """Set terraform variables to enable the application."""
        tfvars = {
            "enable-watcher": True,
            **self.add_horizon_plugin_to_tfvars("watcher"),
        }

        if self.deployment.get_client().cluster.list_nodes_by_role("storage"):
            tfvars.update({"watcher-config": {"collector-plugins": "compute,storage"}})

        return tfvars

    def set_tfvars_on_disable(self) -> dict:
        """Set terraform variables to disable the application."""
        return {
            "enable-watcher": False,
            **self.remove_horizon_plugin_from_tfvars("watcher"),
        }

    def set_tfvars_on_resize(self) -> dict:
        """Set terraform variables to resize the application."""
        return {}

    @click.command()
    def enable_feature(self) -> None:
        """Enable Resource Optimization service (watcher)."""
        super().enable_feature()

    @click.command()
    def disable_feature(self) -> None:
        """Disable Resource Optimization service (watcher)."""
        super().disable_feature()
