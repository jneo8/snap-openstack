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

import importlib
import logging
from pathlib import Path
from typing import Dict, List, Optional

import click
import yaml

from sunbeam import utils
from sunbeam.jobs.common import SunbeamException
from sunbeam.jobs.deployment import Deployment
from sunbeam.jobs.manifest import SoftwareConfig

LOG = logging.getLogger(__name__)
FEATURES_YAML = "features.yaml"


class FeatureManager:
    """Class to expose functions to interact with features.

    Implement the functions required either by sunbeam
    cli or any other cluster operations that need to be
    triggered on all or some of the features.
    """

    @classmethod
    def get_core_features_path(cls) -> Path:
        """Returns the path where the features are defined."""
        return Path(__file__).parent.parent / "features"

    @classmethod
    def get_features_map(
        cls,
        feature_file: Path,
        raise_exception: bool = False,
    ) -> Dict[str, type]:
        """Return dict of {feature name: feature class} from feature yaml.

        :param feature_file: Feature yaml file
        :param raise_exception: If set to true, raises an exception in case
                                feature class is not loaded. By default, ignores
                                by logging the error message.

        :returns: Dict of feature classes
        :raises: ModuleNotFoundError or AttributeError
        """
        features_yaml = {}
        with feature_file.open() as file:
            features_yaml = yaml.safe_load(file)

        features = features_yaml.get("sunbeam-features", {}).get("features", [])
        feature_classes = {}

        for feature in features:
            module = None
            feature_class = feature.get("path")
            if feature_class is None:
                continue
            module_class_ = feature_class.rsplit(".", 1)
            try:
                module = importlib.import_module(module_class_[0])
                feature_class = getattr(module, module_class_[1])
                feature_classes[feature["name"]] = feature_class
            # Catching Exception instead of specific errors as features
            # can raise any exception based on implementation.
            except Exception as e:
                # Exceptions observed so far
                # ModuleNotFoundError, AttributeError, NameError
                LOG.debug(str(e))
                LOG.warning(f"Ignored loading feature: {feature_class}")
                if raise_exception:
                    raise e

                continue

        LOG.debug(f"Feature classes: {feature_classes}")
        return feature_classes

    @classmethod
    def get_feature_classes(
        cls, feature_file: Path, raise_exception: bool = False
    ) -> List[type]:
        """Return a list of feature classes from features yaml.

        :param feature_file: Features yaml file
        :param raise_exception: If set to true, raises an exception in case
                                feature class is not loaded. By default, ignores
                                by logging the error message.

        :returns: List of feature classes
        :raises: ModuleNotFoundError or AttributeError
        """
        return list(cls.get_features_map(feature_file, raise_exception).values())

    @classmethod
    def get_all_feature_classes(cls) -> List[type]:
        """Return a list of feature classes."""
        core_feature_file = cls.get_core_features_path() / FEATURES_YAML
        features = cls.get_feature_classes(core_feature_file)
        return features

    @classmethod
    def get_features(cls, deployment: Deployment) -> list:
        """Returns list of feature name and description.

        :param deployment: Deployment instance.
        :returns: List of feature name and description

        Sample output:
        [
            ("pro", "Ubuntu pro management feature"),
        ]
        """
        feature_file = cls.get_core_features_path() / FEATURES_YAML

        features_yaml = {}
        with feature_file.open() as file:
            features_yaml = yaml.safe_load(file)

        features_list = features_yaml.get("sunbeam-features", {}).get("features", {})
        return [
            (feature.get("name"), feature.get("description"))
            for feature in features_list
        ]

    @classmethod
    def enabled_features(cls, deployment: Deployment) -> list:
        """Returns feature names that are enabled.

        :param deployment: Deployment instance.
        :returns: List of enabled features
        """
        enabled_features = []
        for feature in cls.get_all_feature_classes():
            p = feature(deployment)
            if hasattr(feature, "enabled") and p.enabled:
                enabled_features.append(p.name)

        LOG.debug(f"Enabled features: {enabled_features}")
        return enabled_features

    @classmethod
    def get_all_feature_manifests(
        cls, deployment: Deployment
    ) -> dict[str, SoftwareConfig]:
        """Return a dict of all feature manifest defaults."""
        manifests = {}
        features = cls.get_all_feature_classes()
        for klass in features:
            feature = klass(deployment)
            manifests[feature.name] = feature.manifest_defaults()

        return manifests

    @classmethod
    def get_all_feature_manifest_tfvar_map(cls, deployment: Deployment) -> dict:
        """Return a dict of all feature manifest attributes terraformvars map."""
        tfvar_map = {}
        features = cls.get_all_feature_classes()
        for klass in features:
            feature = klass(deployment)
            m_dict = feature.manifest_attributes_tfvar_map()
            utils.merge_dict(tfvar_map, m_dict)

        return tfvar_map

    @classmethod
    def add_manifest_section(
        cls, deployment: Deployment, software_config: SoftwareConfig
    ) -> None:
        """Allow every feature to augment the manifest."""
        features = cls.get_all_feature_classes()
        for klass in features:
            feature = klass(deployment)
            feature.add_manifest_section(software_config)

    @classmethod
    def get_preseed_questions_content(cls, deployment: Deployment) -> list:
        """Allow every feature to add preseed questions to the preseed file."""
        content = []
        features = cls.get_all_feature_classes()
        for klass in features:
            feature = klass(deployment)
            content.extend(feature.preseed_questions_content())

        return content

    @classmethod
    def get_all_charms_in_openstack_plan(cls, deployment: Deployment) -> list:
        """Return all charms in openstack-plan from all features."""
        charms = []
        features = cls.get_all_feature_classes()
        for klass in features:
            feature = klass(deployment)
            m_dict = feature.manifest_attributes_tfvar_map()
            charms_from_feature = list(
                m_dict.get("openstack-plan", {}).get("charms", {}).keys()
            )
            charms.extend(charms_from_feature)

        return charms

    @classmethod
    def update_proxy_model_configs(cls, deployment: Deployment) -> None:
        """Make all features update proxy model configs."""
        features = cls.get_all_feature_classes()
        for klass in features:
            feature = klass(deployment)
            feature.update_proxy_model_configs()

    @classmethod
    def register(
        cls,
        deployment: Deployment,
        cli: click.Group,
    ) -> None:
        """Register the features.

        Register the features. Once registeted, all the commands/groups defined by
        features will be shown as part of sunbeam cli.

        :param deployment: Deployment instance.
        :param cli: Main click group for sunbeam cli.
        """
        LOG.debug("Registering features")
        for feature in cls.get_all_feature_classes():
            try:
                feature(deployment).register(cli)
            except (ValueError, SunbeamException) as e:
                LOG.debug("Failed to register feature: %r", str(feature))
                if "Clusterd address" in str(e) or "Insufficient permissions" in str(e):
                    LOG.debug(
                        "Sunbeam not bootstrapped. Ignoring feature registration."
                    )
                    continue
                raise e

    @classmethod
    def resolve_feature(cls, feature: str) -> Optional[type]:
        """Resolve a feature name to a class.

        Lookup features to find a feature with the given name.
        """
        feature_file = cls.get_core_features_path() / FEATURES_YAML
        features = cls.get_features_map(feature_file)
        return features.get(feature)

    @classmethod
    def is_feature_version_changed(cls, feature) -> bool:
        """Check if feature version is changed.

        Compare the feature version in the database and the newly loaded one
        from features.yaml. Return true if versions are different.

        :param feature: Feature object
        :returns: True if versions are different.
        """
        LOG.debug("In feature version changed check")
        if not hasattr(feature, "get_feature_info") or not hasattr(feature, "version"):
            raise AttributeError("Feature is not a valid feature class")
        return not feature.get_feature_info().get("version", "0.0.0") == str(
            feature.version
        )

    @classmethod
    def update_features(
        cls,
        deployment: Deployment,
        upgrade_release: bool = False,
    ) -> None:
        """Call feature upgrade hooks.

        Get all the features and call the corresponding feature upgrade hooks
        if the feature is enabled and version is changed.

        :param deployment: Deployment instance.
        :param upgrade_release: Upgrade release flag.
        """
        for feature in cls.get_all_feature_classes():
            p = feature(deployment)
            LOG.debug(f"Object created {p.name}")
            if (
                hasattr(feature, "enabled")
                and p.enabled  # noqa W503
                and hasattr(feature, "upgrade_hook")  # noqa W503
            ):
                LOG.debug(f"Upgrading feature {p.name}")
                try:
                    p.upgrade_hook(upgrade_release=upgrade_release)
                except TypeError:
                    LOG.debug(
                        (
                            f"Feature {p.name} does not support upgrades "
                            "between channels"
                        )
                    )
                    p.upgrade_hook()
