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


import inspect
import logging
import typing
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Literal, Type

import click
from packaging.requirements import Requirement
from packaging.version import Version
from snaphelpers import Snap

from sunbeam.clusterd.service import ConfigItemNotFoundException
from sunbeam.features.interface import utils
from sunbeam.jobs.common import SunbeamException, read_config, update_config
from sunbeam.jobs.deployment import Deployment
from sunbeam.jobs.feature import FeatureManager
from sunbeam.jobs.manifest import SoftwareConfig

LOG = logging.getLogger(__name__)


class FeatureError(SunbeamException):
    """Common feature exception base class."""


class MissingFeatureError(FeatureError):
    """Exception raised when feature is not found."""


class MissingVersionInfoError(FeatureError):
    """Exception raised when feature version info is not found."""


class IncompatibleVersionError(FeatureError):
    """Exception raised when feature version is incompatible."""


class InvalidRequirementError(FeatureError):
    """Exception raised when feature requirement is invalid."""


class DisabledFeatureError(FeatureError):
    """Exception raised when feature is disabled."""


class NotAutomaticFeatureError(FeatureError):
    """Exception rased when feature cannot be automatically enabled."""


class ClickInstantiator:
    """Support invoking click commands on instance methods."""

    def __init__(self, command, klass, client):
        self.command = command
        self.klass = klass
        self.client = client

    def __call__(self, *args, **kwargs):
        """Invoke the click command on the instance method."""
        return self.command(self.klass(self.client), *args, **kwargs)


class BaseFeature(ABC):
    """Base class for Feature interface."""

    # Version of feature interface used by Feature
    interface_version = Version("0.0.1")

    # Version of feature
    version = Version("0.0.0")

    # Name of feature
    name: str

    # Deployment object
    deployment: Deployment

    def __init__(self, name: str, deployment: Deployment) -> None:
        """Constructor for Base feature.

        :param name: Name of the feature
        """
        self.name = name
        self.deployment = deployment

    @property
    def feature_key(self) -> str:
        """Key used to store feature info in cluster database Config table."""
        return self._get_feature_key(self.name)

    def _get_feature_key(self, feature: str) -> str:
        """Generate feature key from feature."""
        return f"Feature-{feature}"

    def install_hook(self) -> None:
        """Install hook for the feature.

        snap-openstack install hook handler invokes this function on all the
        features. Features should override this function if required.
        """
        pass

    def upgrade_hook(self, upgrade_release: bool = False) -> None:
        """Upgrade hook for the feature.

        snap-openstack upgrade hook handler invokes this function on all the
        features. Features should override this function if required.
        """
        pass

    def configure_hook(self) -> None:
        """Configure hook for the feature.

        snap-openstack configure hook handler invokes this function on all the
        features. Features should override this function if required.
        """
        pass

    def pre_refresh_hook(self) -> None:
        """Pre refresh hook for the feature.

        snap-openstack pre-refresh hook handler invokes this function on all the
        features. Features should override this function if required.
        """
        pass

    def post_refresh_hook(self) -> None:
        """Post refresh hook for the feature.

        snap-openstack post-refresh hook handler invokes this function on all the
        features. Features should override this function if required.
        """
        pass

    def remove_hook(self) -> None:
        """Remove hook for the feature.

        snap-openstack remove hook handler invokes this function on all the
        features. Features should override this function if required.
        """
        pass

    def get_feature_info(self) -> dict:
        """Get feature information from clusterdb.

        :returns: Dictionay with feature details like version, and any other information
                  uploded by feature.
        """
        try:
            return read_config(self.deployment.get_client(), self.feature_key)
        except ConfigItemNotFoundException as e:
            LOG.debug(str(e))
            return {}

    def update_feature_info(self, info: dict) -> None:
        """Update feature information in clusterdb.

        Adds version info as well to the info dictionary to update in the cluster db.

        :param info: Feature specific information as dictionary
        """
        info_from_db = self.get_feature_info()
        info_from_db.update(info)
        info_from_db.update({"version": str(self.version)})
        update_config(self.deployment.get_client(), self.feature_key, info_from_db)

    def fetch_feature_version(self, feature: str) -> Version:
        """Fetch feature version stored in database.

        :param feature: Name of the feature
        :returns: Version of the feature
        """
        try:
            config = read_config(
                self.deployment.get_client(), self._get_feature_key(feature)
            )
        except ConfigItemNotFoundException as e:
            raise MissingFeatureError(f"Feature {feature} not found") from e
        version = config.get("version")
        if version is None:
            raise MissingVersionInfoError(
                f"Version info for feature {feature} not found"
            )

        return Version(version)

    def manifest_defaults(self) -> SoftwareConfig:
        """Return manifest part of the feature.

        Define manifest charms involved and default values for charm attributes
        and terraform plan.
        Sample manifest:
        {
            "charms": {
                "heat-k8s": {
                    "channel": <>.
                    "revision": <>,
                    "config": <>,
                }
            },
            "terraform": {
                "<feature>-plan": {
                    "source": <Path of terraform plan>,
                }
            }
        }

        The features that uses terraform plan should override this function.
        """
        return SoftwareConfig()

    def add_manifest_section(self, manifest) -> None:
        """Add manifest section.

        Any new attributes to the manifest introduced by the feature will be read as
        dict. This function should convert the new attribute to a dataclass if
        required and reassign it to manifest object. This will also help in
        validation of new attributes.
        """
        pass

    def manifest_attributes_tfvar_map(self) -> dict:
        """Return terraform var map for the manifest attributes.

        Map terraform variable for each manifest attribute.
        Sample return value:
        {
            <tf plan1>: {
                "charms": {
                    "heat-k8s": {
                        "channel": <tfvar for heat channel>,
                        "revision": <tfvar for heat revision>,
                        "config": <tfvar for heat config>,
                    }
                }
            },
            <tfplan2>: {
                "caas-config": {
                    "image-url": <tfvar map for caas image url>
                }
            }
        }

        The features that uses terraform plan should override this function.
        """
        return {}

    def preseed_questions_content(self) -> list:
        """Generate preseed manifest content.

        The returned content will be used in generation of manifest.
        """
        return []

    def update_proxy_model_configs(self) -> None:
        """Update proxy model configs.

        Features that creates a new model should override this function
        to update model-configs for the model.
        Feature can get proxies using get_proxy_settings(self.feature.deployment)
        """
        pass

    def get_terraform_plans_base_path(self) -> Path:
        """Return Terraform plan base location."""
        return Snap().paths.user_common

    def validate_commands(self) -> bool:
        """Validate the commands dictionary.

        Validate if the dictionary follows the format
        {<group>: [{"name": <command name>, "command": <command function>}]}

        Validates if the command is of type click.Group or click.Command.

        :returns: True if validation is successful, else False.
        """
        LOG.debug(f"Validating commands: {self.commands}")
        for group, commands in self.commands().items():
            for command in commands:
                cmd_name = command.get("name")
                cmd_func = command.get("command")
                if None in (cmd_name, cmd_func):
                    LOG.warning(
                        f"Feature {self.name}: Commands dictionary is not in "
                        "required format"
                    )
                    return False

                if not any(
                    [
                        isinstance(cmd_func, click.Group),
                        isinstance(cmd_func, click.Command),
                    ]
                ):
                    LOG.warning(
                        f"Feature {self.name}: {cmd_func} should be either "
                        "click.Group or click.Command"
                    )
                    return False

        LOG.debug("Validation successful")
        return True

    def is_openstack_control_plane(self) -> bool:
        """Is feature deploys openstack control plane.

        :returns: True if feature deploys openstack control plane, else False.
                  Defaults to False.
        """
        return False

    def is_cluster_bootstrapped(self) -> bool:
        """Is sunbeam cluster bootstrapped.

        :returns: True if sunbeam cluster is bootstrapped, else False.
        """
        try:
            return self.deployment.get_client().cluster.check_sunbeam_bootstrapped()
        except ValueError:
            return False

    @abstractmethod
    def commands(self) -> dict:
        """Dict of clickgroup along with commands.

        Should be of form
        {<group>: [{"name": <command name>, "command": <command function>}]}

        command can be click.Group or click.Command.

        Example:
        {
            "enable": [
                {
                    "name": "subcmd",
                    "command": self.enable_subcmd,
                },
            ],
            "disable": [
                {
                    "name": "subcmd",
                    "command": self.disable_subcmd,
                },
            ],
            "init": [
                {
                    "name": "subgroup",
                    "command": self.trobuleshoot,
                },
            ],
            "subgroup": [
                {
                    "name": "subcmd",
                    "command": self.troubleshoot_subcmd,
                },
            ],
        }

        Based on above example, expected the subclass to define following functions:

        @click.command()
        def enable_subcmd(self):
            pass

        @click.command()
        def disable_subcmd(self):
            pass

        @click.group()
        def troublshoot(self):
            pass

        @click.command()
        def troubleshoot_subcmd(self):
            pass

        Example of one function that requires options:

        @click.command()
        @click.option(
            "-t",
            "--token",
            help="Ubuntu Pro token to use for subscription attachment",
            prompt=True,
        )
        def enable_subcmd(self, token: str):
            pass

        The user can invoke the above commands like:

        sunbeam enable subcmd
        sunbeam disable subcmd
        sunbeam troubleshoot subcmd
        """

    def register(self, cli: click.Group) -> None:
        """Register feature groups and commands.

        :param cli: Sunbeam main cli group
        """
        LOG.debug(f"Registering feature {self.name}")
        if not self.validate_commands():
            LOG.warning(f"Not able to register the feature {self.name}")
            return

        groups = utils.get_all_registered_groups(cli)
        LOG.debug(f"Registered groups: {groups}")
        for group, commands in self.commands().items():
            group_obj = groups.get(group)
            if not group_obj:
                cmd_names = [command.get("name") for command in commands]
                LOG.warning(
                    f"Feature {self.name}: Not able to register command "
                    f"{cmd_names} in group {group} as group does not exist"
                )
                continue

            for command in commands:
                cmd = command.get("command")
                cmd_name = command.get("name")
                if cmd_name in group_obj.list_commands({}):
                    if isinstance(cmd, click.Command):
                        LOG.warning(
                            f"Feature {self.name}: Discarding adding command "
                            f"{cmd_name} as it already exists in group {group}"
                        )
                    else:
                        # Should be sub group and already exists
                        LOG.debug(
                            f"Feature {self.name}: Group {cmd_name} already "
                            f"part of parent group {group}"
                        )
                    continue

                cmd.callback = ClickInstantiator(
                    cmd.callback, type(self), self.deployment
                )
                group_obj.add_command(cmd, cmd_name)
                LOG.debug(
                    f"Feature {self.name}: Command {cmd_name} registered in "
                    f"group {group}"
                )

                # Add newly created click groups to the registered groups so that
                # commands within the feature can be registered on group.
                # This allows feature to create new groups and commands in single place.
                if isinstance(cmd, click.Group):
                    groups[f"{group}.{cmd_name}"] = cmd


class FeatureRequirement(Requirement):
    def __init__(self, requirement_string: str, optional: bool = False):
        super().__init__(requirement_string)
        self.optional = optional

    @property
    def klass(self) -> Type["EnableDisableFeature"]:
        """Return the feature class for the requirement."""
        klass = FeatureManager().resolve_feature(self.name)
        if klass is None:
            raise InvalidRequirementError(f"Feature {self.name} not found")
        if not issubclass(klass, EnableDisableFeature):
            raise InvalidRequirementError(
                f"Feature {self.name} is not of type EnableDisableFeature"
            )
        return klass


@typing.runtime_checkable
class NamedEnabledDisableFeatureProtocol(typing.Protocol):
    def __init__(self, deployment: Deployment) -> None:
        pass

    @property
    def enabled(self) -> bool:
        """Is the feature enabled."""
        ...


class EnableDisableFeature(BaseFeature):
    """Interface for features of type on/off.

    Features that can be enabled or disabled can use this interface instead
    of BaseFeature.
    """

    interface_version = Version("0.0.1")

    requires: set[FeatureRequirement] = set()

    def __init__(self, name: str, deployment: Deployment) -> None:
        """Constructor for feature interface.

        :param name: Name of the feature
        """
        super().__init__(name, deployment)
        self.user_manifest: Path | None = None

    @property
    def enabled(self) -> bool:
        """Feature is enabled or disabled.

        Retrieves enabled field from the Feature info saved in
        the database and returns enabled based on the enabled field.

        :returns: True if feature is enabled, else False.
        """
        info = self.get_feature_info()
        return info.get("enabled", "false").lower() == "true"

    def check_enabled_requirement_is_compatible(self, requirement: FeatureRequirement):
        """Check if an enabled requirement is compatible with current requirer."""
        if len(requirement.specifier) == 0:
            # No version requirement, so no need to check version
            return

        try:
            current_version = self.fetch_feature_version(requirement.name)
            LOG.debug(f"Feature {requirement.name} version {current_version} found")
        except MissingVersionInfoError as e:
            LOG.debug(f"Version info for feature {requirement.name} not found")
            raise FeatureError(
                f"{requirement.name} has no version recorded,"
                f" {requirement.specifier} required"
            ) from e

        if not requirement.specifier.contains(current_version):
            raise IncompatibleVersionError(
                f"Feature {self.name} requires '{requirement.name}"
                f"{requirement.specifier}' but enabled feature is {current_version}"
            )

    def check_feature_class_is_compatible(
        self, feature: "EnableDisableFeature", requirement: FeatureRequirement
    ):
        """Check if actual feature class is compatible with requirements."""
        if len(requirement.specifier) == 0:
            # No version requirement, so no need to check version
            return

        klass_version_compatible = all(
            (
                feature.version,
                requirement.specifier,
                requirement.specifier.contains(feature.version),
            )
        )

        if not klass_version_compatible:
            message = (
                f"Feature {self.name} requires '{requirement.name}"
                f"{requirement.specifier}' but loaded feature version"
                f" is {feature.version}"
            )
            raise IncompatibleVersionError(
                " ".join(
                    (
                        "Feature has an incompatible version.",
                        "This should not happen.",
                        message,
                    )
                )
            )

    def check_feature_is_automatically_enableable(
        self, feature: "EnableDisableFeature"
    ):
        """Check whether a feature can be automatically enabled."""
        spec = inspect.getfullargspec(feature.enable_feature)
        if spec.args != ["self"]:
            raise NotAutomaticFeatureError(
                f"Feature {self.name} depends on {feature.name},"
                f" and {feature.name} cannot be automatically enabled."
                " Please enable it by running"
                f" 'sunbeam enable {feature.name} <config options...>'"
            )

    def check_enablement_requirements(
        self,
        state: Literal["enable"] | Literal["disable"] = "enable",
    ):
        """Check whether the feature can be enabled."""
        features = FeatureManager().get_all_feature_classes()
        for klass in features:
            if not isinstance(klass, NamedEnabledDisableFeatureProtocol):
                LOG.debug(
                    f"Skipping {klass} as it does not respect"
                    " NamedEnabledDisableFeatureProtocol"
                )
                continue
            feature = klass(self.deployment)
            if not feature.enabled:
                continue
            for requirement in feature.requires:
                if requirement.name != self.name:
                    continue
                if state == "disable":
                    raise FeatureError(
                        f"{feature.name} is enabled and requires {self.name}"
                    )
                message = (
                    f"Feature {feature.name} is enabled and "
                    f"requires '{requirement.name}{requirement.specifier}'"
                )
                LOG.debug(message)
                if requirement.specifier.contains(self.version):
                    # we found the feature, and it's compatible
                    break
                raise IncompatibleVersionError(message)

    def enable_requirements(self):
        """Iterate through requirements, enable features if possible."""
        for requirement in self.requires:
            if not isinstance(requirement.klass, NamedEnabledDisableFeatureProtocol):
                LOG.debug(
                    f"Skipping {requirement.klass} as it does not respect"
                    " NamedEnabledDisableFeatureProtocol"
                )
                continue
            feature = requirement.klass(self.deployment)

            if feature.enabled:
                self.check_enabled_requirement_is_compatible(requirement)
                # Feature is already enabled, and has a compatible version.
                continue

            if requirement.optional:
                # Skip enablement since feature is optional
                continue
            self.check_feature_class_is_compatible(feature, requirement)
            self.check_feature_is_automatically_enableable(feature)

            ctx = click.get_current_context()
            ctx.invoke(feature.enable_feature)

    def pre_enable(self) -> None:
        """Handler to perform tasks before enabling the feature."""
        self.check_enablement_requirements()
        self.enable_requirements()

    def post_enable(self) -> None:
        """Handler to perform tasks after the feature is enabled."""
        pass

    @abstractmethod
    def run_enable_plans(self) -> None:
        """Run plans to enable feature.

        The feature implementation is expected to override this function and
        specify the plans to be run to deploy the workload supported by feature.
        """

    @abstractmethod
    def enable_feature(self) -> None:
        """Enable feature command."""
        self.user_manifest = None
        current_click_context = click.get_current_context()
        while current_click_context.parent is not None:
            if (
                current_click_context.parent.command.name == "enable"
                and "manifest" in current_click_context.parent.params  # noqa: W503
            ):
                if manifest := current_click_context.parent.params.get("manifest"):
                    self.user_manifest = Path(manifest)
            current_click_context = current_click_context.parent

        self.pre_enable()
        self.run_enable_plans()
        self.post_enable()
        self.update_feature_info({"enabled": "true"})

    def pre_disable(self) -> None:
        """Handler to perform tasks before disabling the feature."""
        self.check_enablement_requirements(state="disable")

    def post_disable(self) -> None:
        """Handler to perform tasks after the feature is disabled."""
        pass

    @abstractmethod
    def run_disable_plans(self) -> None:
        """Run plans to disable feature.

        The feature implementation is expected to override this function and
        specify the plans to be run to destroy the workload supported by feature.
        """

    @abstractmethod
    def disable_feature(self) -> None:
        """Disable feature command."""
        self.pre_disable()
        self.run_disable_plans()
        self.post_disable()
        self.update_feature_info({"enabled": "false"})

    def commands(self) -> dict:
        """Dict of clickgroup along with commands."""
        return {
            "enable": [{"name": self.name, "command": self.enable_feature}],
            "disable": [{"name": self.name, "command": self.disable_feature}],
        }
