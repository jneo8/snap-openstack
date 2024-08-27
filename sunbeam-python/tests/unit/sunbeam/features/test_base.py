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

from unittest.mock import Mock, patch

import click
import pytest
from packaging.version import Version

from sunbeam.clusterd.service import ConfigItemNotFoundException
from sunbeam.core.deployment import Deployment
from sunbeam.core.feature import FEATURES_YAML, FeatureManager
from sunbeam.features.interface.v1.base import (
    BaseFeature,
    EnableDisableFeature,
    FeatureError,
    FeatureRequirement,
    IncompatibleVersionError,
    MissingFeatureError,
    MissingVersionInfoError,
    NotAutomaticFeatureError,
)


@pytest.fixture()
def deployment():
    yield Mock()


@pytest.fixture()
def utils():
    with patch("sunbeam.features.interface.v1.base.utils") as p:
        yield p


@pytest.fixture()
def clickinstantiator():
    with patch("sunbeam.features.interface.v1.base.ClickInstantiator") as p:
        yield p


@pytest.fixture()
def read_config():
    with patch("sunbeam.features.interface.v1.base.read_config") as p:
        yield p


@pytest.fixture()
def update_config():
    with patch("sunbeam.features.interface.v1.base.update_config") as p:
        yield p


@pytest.fixture(autouse=True)
def base_feature_abc():
    """Disable abstract methods for ease of testing."""
    base_abstract_methods = BaseFeature.__abstractmethods__
    enable_abstract_methods = EnableDisableFeature.__abstractmethods__
    BaseFeature.__abstractmethods__ = frozenset()
    EnableDisableFeature.__abstractmethods__ = frozenset()
    yield
    BaseFeature.__abstractmethods__ = base_abstract_methods
    EnableDisableFeature.__abstractmethods__ = enable_abstract_methods


def feature_classes() -> list[type[EnableDisableFeature]]:
    with patch("snaphelpers.Snap"):
        manager = FeatureManager()
        yaml_file = manager.get_core_features_path() / FEATURES_YAML
        classes = []
        for klass in manager.get_feature_classes(yaml_file):
            if issubclass(klass, EnableDisableFeature):
                classes.append(klass)
        return classes


class TestBaseFeature:
    def test_validate_commands(self, deployment):
        with patch.object(BaseFeature, "commands") as mock_commands:
            feature = BaseFeature("test", deployment)
            mock_commands.return_value = {
                "group1": [{"name": "cmd1", "command": click.Command("cmd1")}]
            }
            feature = BaseFeature("test", deployment)
            result = feature.validate_commands()
            assert result is True

    def test_validate_commands_missing_command_function(self, deployment):
        with patch.object(BaseFeature, "commands") as mock_commands:
            mock_commands.return_value = {"group1": [{"name": "cmd1"}]}
            feature = BaseFeature("test", deployment)
            result = feature.validate_commands()
            assert result is False

    def test_validate_commands_missing_command_name(self, deployment):
        with patch.object(BaseFeature, "commands") as mock_commands:
            mock_commands.return_value = {
                "group1": [{"command": click.Command("cmd1")}]
            }
            feature = BaseFeature("test", deployment)
            result = feature.validate_commands()
            assert result is False

    def test_validate_commands_empty_command_list(self, deployment):
        with patch.object(BaseFeature, "commands") as mock_commands:
            mock_commands.return_value = {"group1": []}
            feature = BaseFeature("test", deployment)
            result = feature.validate_commands()
            assert result is True

    def test_validate_commands_subgroup_as_command(self, deployment):
        with patch.object(BaseFeature, "commands") as mock_commands:
            mock_commands.return_value = {
                "group1": [{"name": "subgroup1", "command": click.Group("subgroup1")}]
            }
            feature = BaseFeature("test", deployment)
            result = feature.validate_commands()
            assert result is True

    def test_register(self, deployment, utils, clickinstantiator):
        with patch.object(BaseFeature, "commands") as mock_commands:
            cli = Mock()
            mock_groups = Mock()
            mock_group_obj = Mock()
            utils.get_all_registered_groups.return_value = mock_groups
            mock_groups.get.return_value = mock_group_obj
            mock_group_obj.list_commands.return_value = []

            cmd1_obj = click.Command("cmd1")
            mock_commands.return_value = {
                "group1": [{"name": "cmd1", "command": cmd1_obj}]
            }
            feature = BaseFeature("test", deployment)
            feature.register(cli)
            clickinstantiator.assert_called_once()
            mock_group_obj.add_command.assert_called_once_with(cmd1_obj, "cmd1")

    def test_register_when_command_already_exists(
        self, deployment, utils, clickinstantiator
    ):
        with patch.object(BaseFeature, "commands") as mock_commands:
            cli = Mock()
            mock_groups = Mock()
            mock_group_obj = Mock()
            utils.get_all_registered_groups.return_value = mock_groups
            mock_groups.get.return_value = mock_group_obj
            mock_group_obj.list_commands.return_value = ["cmd1"]

            cmd1_obj = click.Command("cmd1")
            mock_commands.return_value = {
                "group1": [{"name": "cmd1", "command": cmd1_obj}]
            }
            feature = BaseFeature("test", deployment)
            feature.register(cli)
            mock_group_obj.add_command.assert_not_called()
            clickinstantiator.assert_not_called()

    def test_register_when_group_doesnot_exists(
        self, deployment, utils, clickinstantiator
    ):
        with patch.object(BaseFeature, "commands") as mock_commands:
            cli = Mock()
            mock_groups = Mock()
            utils.get_all_registered_groups.return_value = mock_groups
            mock_groups.get.return_value = None

            cmd1_obj = click.Command("cmd1")
            mock_commands.return_value = {
                "group1": [{"name": "cmd1", "command": cmd1_obj}]
            }
            feature = BaseFeature("test", deployment)
            feature.register(cli)
            clickinstantiator.assert_not_called()

    def test_get_feature_info(self, deployment, read_config):
        mock_info = {"version": "0.0.1"}
        read_config.return_value = mock_info
        feature = BaseFeature("test", deployment)
        info = feature.get_feature_info()
        assert info == mock_info

    def test_get_feature_info_no_config_in_db(self, deployment, read_config):
        read_config.side_effect = ConfigItemNotFoundException()
        feature = BaseFeature("test", deployment)
        info = feature.get_feature_info()
        assert info == {}

    def test_update_feature_info(self, deployment, read_config, update_config):
        mock_info = {}
        read_config.return_value = mock_info
        feature = BaseFeature("test", deployment)
        feature.update_feature_info({"test": "test"})
        assert update_config.call_args.args[2] == {"test": "test", "version": "0.0.0"}

    def test_update_feature_info_with_config_in_database(
        self, deployment, read_config, update_config
    ):
        mock_info = {"version": "0.0.1", "enabled": "true"}
        read_config.return_value = mock_info
        feature = BaseFeature("test", deployment)
        feature.update_feature_info({"test": "test"})
        assert update_config.call_args.args[2] == {
            "enabled": "true",
            "test": "test",
            "version": "0.0.0",
        }

    def test_fetch_feature_version_with_valid_feature(self, deployment, read_config):
        client_instance = Mock()
        deployment.get_client.return_value = client_instance
        feature_key = "test_feature"
        config = {"version": "1.0.0"}
        read_config.return_value = config

        feature = BaseFeature("test", deployment)
        version = feature.fetch_feature_version(feature_key)
        assert version == Version("1.0.0")
        read_config.assert_called_once_with(client_instance, f"Feature-{feature_key}")

    def test_fetch_feature_version_with_missing_feature(self, deployment, read_config):
        client_instance = Mock()
        deployment.get_client.return_value = client_instance
        feature_key = "test_feature"
        read_config.side_effect = ConfigItemNotFoundException
        feature = BaseFeature("test", deployment)
        with pytest.raises(MissingFeatureError):
            feature.fetch_feature_version(feature_key)
        read_config.assert_called_once_with(client_instance, f"Feature-{feature_key}")

    def test_fetch_feature_version_with_missing_version_info(
        self, deployment, read_config
    ):
        client_instance = Mock()
        deployment.get_client.return_value = client_instance
        feature_key = "test_feature"
        config = {}
        read_config.return_value = config
        feature = BaseFeature("test", deployment)
        with pytest.raises(MissingVersionInfoError):
            feature.fetch_feature_version(feature_key)
        read_config.assert_called_once_with(client_instance, f"Feature-{feature_key}")


class DummyFeature(EnableDisableFeature):
    version = Version("0.0.1")

    def __init__(self, deployment):
        super().__init__("test_feature", deployment)

    def enable_feature(self) -> None:
        pass

    def disable_feature(self) -> None:
        pass

    def run_enable_plans(self) -> None:
        pass

    def run_disable_plans(self) -> None:
        pass


def feature_klass(version_: str, enabled: bool = False) -> type[EnableDisableFeature]:
    class CompatibleFeature(EnableDisableFeature):
        version = Version(version_)
        requires = {FeatureRequirement("test_req>=1.0.0")}

        def __init__(self, deployment: Deployment) -> None:
            super().__init__("test_feature", deployment)

        @property
        def enabled(self) -> bool:
            return enabled

        def enable_feature(self, *args, **kwargs) -> None:
            pass

        def disable_feature(self, *args, **kwargs) -> None:
            pass

        def run_enable_plans(self) -> None:
            pass

        def run_disable_plans(self) -> None:
            pass

    return CompatibleFeature


class TestEnableDisableFeature:
    def test_check_enabled_feature_is_compatible_with_compatible_requirement(
        self, deployment, mocker
    ):
        feature = DummyFeature(deployment)
        mocker.patch.object(feature, "fetch_feature_version", return_value="1.0.0")
        requirement = FeatureRequirement("test_feature>=1.0.0")
        feature.check_enabled_requirement_is_compatible(requirement)

    def test_check_enabled_feature_is_compatible_with_missing_version_info(
        self, deployment, mocker
    ):
        feature = DummyFeature(deployment)

        mocker.patch.object(
            feature, "fetch_feature_version", side_effect=MissingVersionInfoError
        )
        requirement = FeatureRequirement("test_feature>=1.0.0")
        with pytest.raises(FeatureError):
            feature.check_enabled_requirement_is_compatible(requirement)

    def test_check_enabled_feature_is_compatible_with_incompatible_requirement(
        self, deployment, mocker
    ):
        feature = DummyFeature(deployment)

        mocker.patch.object(feature, "fetch_feature_version", return_value="0.9.0")
        requirement = FeatureRequirement("test_feature>=1.0.0")
        with pytest.raises(IncompatibleVersionError):
            feature.check_enabled_requirement_is_compatible(requirement)

    def test_check_enabled_feature_is_compatible_with_optional_requirement(
        self, deployment, mocker
    ):
        feature = DummyFeature(deployment)

        mocker.patch.object(
            feature, "fetch_feature_version", side_effect=MissingVersionInfoError
        )
        requirement = FeatureRequirement("test_feature>=1.0.0", optional=True)
        with pytest.raises(FeatureError):
            feature.check_enabled_requirement_is_compatible(requirement)

    def test_check_enabled_feature_is_compatible_with_no_specifier_and_optional_requirement(  # noqa: E501
        self, deployment, mocker
    ):
        feature = DummyFeature(deployment)

        mocker.patch.object(
            feature, "fetch_feature_version", side_effect=MissingVersionInfoError
        )
        requirement = FeatureRequirement("test_feature", optional=True)
        feature.check_enabled_requirement_is_compatible(requirement)

    def test_check_enabled_feature_is_compatible_with_no_specifier_and_required_requirement(  # noqa: E501
        self, deployment, mocker
    ):
        feature = DummyFeature(deployment)

        mocker.patch.object(
            feature, "fetch_feature_version", side_effect=MissingVersionInfoError
        )
        requirement = FeatureRequirement("test_feature", optional=False)
        feature.check_enabled_requirement_is_compatible(requirement)

    def test_check_feature_class_is_compatible_with_compatible_requirement(
        self, deployment
    ):
        feature = DummyFeature(deployment)

        requirement = FeatureRequirement("test_feature>=1.0.0")

        klass = feature_klass("1.0.0")
        feature.check_feature_class_is_compatible(klass(deployment), requirement)

    def test_check_feature_class_is_compatible_with_incompatible_requirement(
        self, deployment
    ):
        feature = DummyFeature(deployment)

        requirement = FeatureRequirement("test_feature>=2.0.0")

        klass = feature_klass("1.0.0")
        with pytest.raises(IncompatibleVersionError):
            feature.check_feature_class_is_compatible(klass(deployment), requirement)

    def test_check_feature_class_is_compatible_with_core_feature_and_incompatible_version(
        self, deployment
    ):
        feature = DummyFeature(deployment)

        requirement = FeatureRequirement("test_feature>=1.0.0")

        klass = feature_klass("0.5.0")
        with pytest.raises(IncompatibleVersionError):
            feature.check_feature_class_is_compatible(klass(deployment), requirement)

    def test_check_feature_class_is_compatible_with_no_specifier(self, deployment):
        feature = DummyFeature(deployment)

        requirement = FeatureRequirement("test_feature")

        klass = feature_klass("1.0.0")
        feature.check_feature_class_is_compatible(klass(deployment), requirement)

    def test_check_feature_is_automatically_enableable_with_automatically_enableable_feature(  # noqa: E501
        self, deployment
    ):
        feature = DummyFeature(deployment)
        feature.check_feature_is_automatically_enableable(feature)  # type: ignore

    def test_check_feature_is_automatically_enableable_with_non_automatically_enableable_feature(  # noqa: E501
        self, deployment
    ):
        class DummyFeatureInner(DummyFeature):
            def enable_feature(self, necessary_arg) -> None:
                return super().enable_feature()

        required_feature = DummyFeatureInner(deployment=deployment)

        feature = DummyFeature(deployment)
        with pytest.raises(NotAutomaticFeatureError):
            feature.check_feature_is_automatically_enableable(required_feature)  # type: ignore # noqa: E501

    @pytest.mark.parametrize("klass", feature_classes())
    def test_core_features_requirements(self, deployment, klass):
        feature = klass(deployment=deployment)

        for requirement in feature.requires:
            feature.check_feature_class_is_compatible(
                requirement.klass(deployment=deployment), requirement
            )

    def test_check_enablement_requirements_with_enabled_compatible_requirement(
        self, deployment, mocker
    ):
        feature = DummyFeature(deployment)
        feature.name = "test_req"
        feature.version = Version("1.0.1")
        klass = feature_klass("0.0.1")
        mocker.patch.object(
            klass,
            "get_feature_info",
            return_value={"version": klass.version, "enabled": "true"},
        )
        mocker.patch.object(
            FeatureManager, "get_all_feature_classes", return_value=[klass]
        )
        feature.check_enablement_requirements()

    def test_check_enablement_requirements_with_disabled_compatible_requirement(
        self, deployment, mocker
    ):
        feature = DummyFeature(deployment)
        feature.name = "test_req"
        klass = feature_klass("0.0.1", enabled=False)
        mocker.patch.object(
            klass,
            "get_feature_info",
            return_value={"version": klass.version, "enabled": "false"},
        )
        mocker.patch.object(
            FeatureManager, "get_all_feature_classes", return_value=[klass]
        )
        feature.check_enablement_requirements()

    def test_check_enablement_requirements_with_enabled_incompatible_requirement(
        self, deployment, mocker
    ):
        feature = DummyFeature(deployment)
        feature.name = "test_req"
        klass = feature_klass("0.0.1", True)
        mocker.patch.object(
            klass,
            "get_feature_info",
            return_value={"version": klass.version, "enabled": "true"},
        )
        mocker.patch.object(
            FeatureManager, "get_all_feature_classes", return_value=[klass]
        )
        with pytest.raises(IncompatibleVersionError):
            feature.check_enablement_requirements()

    def test_check_enablement_requirements_with_disabled_incompatible_requirement(
        self, deployment, mocker
    ):
        feature = DummyFeature(deployment)
        feature.name = "test_req"
        klass = feature_klass("0.0.1")
        mocker.patch.object(
            klass,
            "get_feature_info",
            return_value={"version": klass.version, "enabled": "false"},
        )
        mocker.patch.object(
            FeatureManager, "get_all_feature_classes", return_value=[klass]
        )
        feature.check_enablement_requirements()

    def test_check_enablement_requirements_with_enabled_dependant(
        self, deployment, mocker
    ):
        feature = DummyFeature(deployment)
        feature.name = "test_req"
        klass = feature_klass("0.0.1", enabled=True)
        mocker.patch.object(
            klass,
            "get_feature_info",
            return_value={"version": klass.version, "enabled": "true"},
        )
        mocker.patch.object(
            FeatureManager, "get_all_feature_classes", return_value=[klass]
        )
        with pytest.raises(FeatureError):
            feature.check_enablement_requirements("disable")

    def test_check_enablement_requirements_with_disabled_dependant(
        self, deployment, mocker
    ):
        feature = DummyFeature(deployment)
        feature.name = "test_req"
        klass = feature_klass("0.0.1")
        mocker.patch.object(
            klass,
            "get_feature_info",
            return_value={"version": klass.version, "enabled": "false"},
        )
        mocker.patch.object(
            FeatureManager, "get_all_feature_classes", return_value=[klass]
        )
        feature.check_enablement_requirements("disable")
