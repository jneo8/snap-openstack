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

"""Vault feature.

Vault secure, store and tightly control access to tokens, passwords, certificates,
encryption keys for protecting secrets and other sensitive data.
"""

import logging

import click
from packaging.version import Version

from sunbeam.core.deployment import Deployment
from sunbeam.core.manifest import CharmManifest, FeatureConfig, SoftwareConfig
from sunbeam.features.interface.v1.openstack import (
    OpenStackControlPlaneFeature,
    TerraformPlanLocation,
)
from sunbeam.utils import click_option_show_hints, pass_method_obj
from sunbeam.versions import VAULT_CHANNEL

LOG = logging.getLogger(__name__)


class VaultFeature(OpenStackControlPlaneFeature):
    version = Version("0.0.1")

    name = "vault"
    tf_plan_location = TerraformPlanLocation.SUNBEAM_TERRAFORM_REPO

    def default_software_overrides(self) -> SoftwareConfig:
        """Manifest pluing part in dict format."""
        return SoftwareConfig(
            charms={"vault-k8s": CharmManifest(channel=VAULT_CHANNEL)}
        )

    def manifest_attributes_tfvar_map(self) -> dict:
        """Manifest attrbitues to terraformvars map."""
        return {
            self.tfplan: {
                "charms": {
                    "vault-k8s": {
                        "channel": "vault-channel",
                        "revision": "vault-revision",
                        "config": "vault-config",
                    }
                }
            }
        }

    def set_application_names(self, deployment: Deployment) -> list:
        """Application names handled by the terraform plan."""
        return ["vault"]

    def set_tfvars_on_enable(
        self, deployment: Deployment, config: FeatureConfig
    ) -> dict:
        """Set terraform variables to enable the application."""
        return {
            "enable-vault": True,
        }

    def set_tfvars_on_disable(self, deployment: Deployment) -> dict:
        """Set terraform variables to disable the application."""
        return {"enable-vault": False}

    def set_tfvars_on_resize(
        self, deployment: Deployment, config: FeatureConfig
    ) -> dict:
        """Set terraform variables to resize the application."""
        return {}

    @click.command()
    @click_option_show_hints
    @pass_method_obj
    def enable_cmd(self, deployment: Deployment, show_hints: bool) -> None:
        """Enable Vault.

        Vault secure, store and tightly control access to tokens, passwords,
        certificates, encryption keys for protecting secrets and other sensitive data.
        """
        self.enable_feature(deployment, FeatureConfig(), show_hints)

    @click.command()
    @click_option_show_hints
    @pass_method_obj
    def disable_cmd(self, deployment: Deployment, show_hints: bool) -> None:
        """Disable Vault."""
        self.disable_feature(deployment, show_hints)
