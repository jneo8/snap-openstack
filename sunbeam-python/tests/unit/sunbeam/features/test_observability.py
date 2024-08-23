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

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from sunbeam.core.common import ResultType
from sunbeam.core.juju import TimeoutException
from sunbeam.core.terraform import TerraformException
from sunbeam.features.observability import feature as observability_feature


@pytest.fixture(autouse=True)
def mock_run_sync(mocker):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()

    def run_sync(coro):
        return loop.run_until_complete(coro)

    mocker.patch("sunbeam.features.observability.feature.run_sync", run_sync)
    yield
    loop.close()


@pytest.fixture()
def tfhelper():
    yield Mock()


@pytest.fixture()
def jhelper():
    yield AsyncMock()


@pytest.fixture()
def observabilityfeature():
    with patch("sunbeam.features.observability.feature.ObservabilityFeature") as p:
        yield p


@pytest.fixture()
def ssnap():
    with patch("sunbeam.core.k8s.Snap") as p:
        yield p


@pytest.fixture()
def update_config():
    with patch("sunbeam.features.observability.feature.update_config") as p:
        yield p


class TestDeployObservabilityStackStep:
    def test_run(self, tfhelper, jhelper, observabilityfeature, ssnap):
        ssnap().config.get.return_value = "k8s"
        observabilityfeature.deployment.proxy_settings.return_value = {}
        step = observability_feature.DeployObservabilityStackStep(
            observabilityfeature, tfhelper, jhelper
        )
        result = step.run()

        tfhelper.update_tfvars_and_apply_tf.assert_called_once()
        jhelper.wait_until_active.assert_called_once()
        assert result.result_type == ResultType.COMPLETED

    def test_run_tf_apply_failed(self, tfhelper, jhelper, observabilityfeature, ssnap):
        ssnap().config.get.return_value = "k8s"
        observabilityfeature.deployment.proxy_settings.return_value = {}
        tfhelper.update_tfvars_and_apply_tf.side_effect = TerraformException(
            "apply failed..."
        )

        step = observability_feature.DeployObservabilityStackStep(
            observabilityfeature, tfhelper, jhelper
        )
        result = step.run()

        tfhelper.update_tfvars_and_apply_tf.assert_called_once()
        jhelper.wait_until_active.assert_not_called()
        assert result.result_type == ResultType.FAILED
        assert result.message == "apply failed..."

    def test_run_waiting_timed_out(
        self, tfhelper, jhelper, observabilityfeature, ssnap
    ):
        ssnap().config.get.return_value = "k8s"
        observabilityfeature.deployment.proxy_settings.return_value = {}
        jhelper.wait_until_active.side_effect = TimeoutException("timed out")

        step = observability_feature.DeployObservabilityStackStep(
            observabilityfeature, tfhelper, jhelper
        )
        result = step.run()

        tfhelper.update_tfvars_and_apply_tf.assert_called_once()
        jhelper.wait_until_active.assert_called_once()
        assert result.result_type == ResultType.FAILED
        assert result.message == "timed out"


class TestRemoveObservabilityStackStep:
    def test_run(self, tfhelper, jhelper, observabilityfeature, ssnap):
        ssnap().config.get.return_value = "k8s"
        step = observability_feature.RemoveObservabilityStackStep(
            observabilityfeature, tfhelper, jhelper
        )
        result = step.run()

        tfhelper.destroy.assert_called_once()
        jhelper.wait_model_gone.assert_called_once()
        assert result.result_type == ResultType.COMPLETED

    def test_run_tf_destroy_failed(
        self, tfhelper, jhelper, observabilityfeature, ssnap
    ):
        ssnap().config.get.return_value = "k8s"
        tfhelper.destroy.side_effect = TerraformException("destroy failed...")

        step = observability_feature.RemoveObservabilityStackStep(
            observabilityfeature, tfhelper, jhelper
        )
        result = step.run()

        tfhelper.destroy.assert_called_once()
        jhelper.wait_model_gone.assert_not_called()
        assert result.result_type == ResultType.FAILED
        assert result.message == "destroy failed..."

    def test_run_waiting_timed_out(
        self, tfhelper, jhelper, observabilityfeature, ssnap
    ):
        ssnap().config.get.return_value = "k8s"
        jhelper.wait_model_gone.side_effect = TimeoutException("timed out")

        step = observability_feature.RemoveObservabilityStackStep(
            observabilityfeature, tfhelper, jhelper
        )
        result = step.run()

        tfhelper.destroy.assert_called_once()
        jhelper.wait_model_gone.assert_called_once()
        assert result.result_type == ResultType.FAILED
        assert result.message == "timed out"


class TestDeployGrafanaAgentStep:
    def test_run(self, tfhelper, jhelper, observabilityfeature):
        step = observability_feature.DeployGrafanaAgentStep(
            observabilityfeature, tfhelper, jhelper
        )
        result = step.run()

        tfhelper.update_tfvars_and_apply_tf.assert_called_once()
        jhelper.wait_application_ready.assert_called_once()
        assert result.result_type == ResultType.COMPLETED

    def test_run_tf_apply_failed(self, tfhelper, jhelper, observabilityfeature):
        tfhelper.update_tfvars_and_apply_tf.side_effect = TerraformException(
            "apply failed..."
        )

        step = observability_feature.DeployGrafanaAgentStep(
            observabilityfeature, tfhelper, jhelper
        )
        result = step.run()

        tfhelper.update_tfvars_and_apply_tf.assert_called_once()
        jhelper.wait_application_ready.assert_not_called()
        assert result.result_type == ResultType.FAILED
        assert result.message == "apply failed..."

    def test_run_waiting_timed_out(self, tfhelper, jhelper, observabilityfeature):
        jhelper.wait_application_ready.side_effect = TimeoutException("timed out")

        step = observability_feature.DeployGrafanaAgentStep(
            observabilityfeature, tfhelper, jhelper
        )
        result = step.run()

        tfhelper.update_tfvars_and_apply_tf.assert_called_once()
        jhelper.wait_application_ready.assert_called_once()
        assert result.result_type == ResultType.FAILED
        assert result.message == "timed out"


class TestRemoveGrafanaAgentStep:
    def test_run(self, tfhelper, jhelper, observabilityfeature, update_config):
        step = observability_feature.RemoveGrafanaAgentStep(
            observabilityfeature, tfhelper, jhelper
        )
        result = step.run()

        tfhelper.destroy.assert_called_once()
        jhelper.wait_application_gone.assert_called_once()
        assert result.result_type == ResultType.COMPLETED

    def test_run_tf_destroy_failed(self, tfhelper, jhelper, observabilityfeature):
        tfhelper.destroy.side_effect = TerraformException("destroy failed...")

        step = observability_feature.RemoveGrafanaAgentStep(
            observabilityfeature, tfhelper, jhelper
        )
        result = step.run()

        tfhelper.destroy.assert_called_once()
        jhelper.wait_application_gone.assert_not_called()
        assert result.result_type == ResultType.FAILED
        assert result.message == "destroy failed..."

    def test_run_waiting_timed_out(self, tfhelper, jhelper, observabilityfeature):
        jhelper.wait_application_gone.side_effect = TimeoutException("timed out")

        step = observability_feature.RemoveGrafanaAgentStep(
            observabilityfeature, tfhelper, jhelper
        )
        result = step.run()

        tfhelper.destroy.assert_called_once()
        jhelper.wait_application_gone.assert_called_once()
        assert result.result_type == ResultType.FAILED
        assert result.message == "timed out"


class TestRemoveSaasApplicationsStep:
    def test_is_skip(self, jhelper):
        jhelper.get_model_status.return_value = {
            "remote-applications": {
                "test-1": {"offer-url": "admin/offering_model.test-1"},
                "test-2": {"endpoints": [{"interface": "grafana_dashboard"}]},
                "test-3": {"endpoints": [{"interface": "identity_credentials"}]},
            }
        }
        step = observability_feature.RemoveSaasApplicationsStep(
            jhelper,
            "test",
            "offering_model",
            observability_feature.OBSERVABILITY_OFFER_INTERFACES,
        )
        result = step.is_skip()
        assert step._remote_app_to_delete == ["test-1", "test-2"]
        assert result.result_type == ResultType.COMPLETED

    def test_is_skip_no_remote_app(self, jhelper):
        jhelper.get_model_status.return_value = {}
        step = observability_feature.RemoveSaasApplicationsStep(
            jhelper,
            "test",
            "offering_model",
            observability_feature.OBSERVABILITY_OFFER_INTERFACES,
        )
        result = step.is_skip()
        assert result.result_type == ResultType.SKIPPED

    def test_is_skip_no_saas_app(self, jhelper):
        jhelper.get_model_status.return_value = {
            "remote-applications": {
                "test-1": {"offer-url": "admin/offering_model.test-1"},
                "test-3": {"endpoints": [{"interface": "identity_credentials"}]},
            }
        }
        step = observability_feature.RemoveSaasApplicationsStep(
            jhelper,
            "test",
            "offering_model-no-apps",
            observability_feature.OBSERVABILITY_OFFER_INTERFACES,
        )
        result = step.is_skip()
        assert result.result_type == ResultType.SKIPPED

    def test_run(self, jhelper):
        step = observability_feature.RemoveSaasApplicationsStep(
            jhelper,
            "test",
            "offering_model",
            observability_feature.OBSERVABILITY_OFFER_INTERFACES,
        )
        step._remote_app_to_delete = ["test-1"]
        result = step.run()
        assert result.result_type == ResultType.COMPLETED


class TestIntegrateRemoteCosOffersStep:
    def test_run(self, jhelper, observabilityfeature, snap, run):
        observabilityfeature.grafana_offer_url = "remotecos:admin/grafana"
        observabilityfeature.prometheus_offer_url = "remotecos:admin/prometheus"
        observabilityfeature.loki_offer_url = "remotecos:admin/loki"
        observabilityfeature.deployment.openstack_machines_model = "test-model"
        step = observability_feature.IntegrateRemoteCosOffersStep(
            observabilityfeature, jhelper
        )

        result = step.run()
        jhelper.wait_application_ready.assert_called()
        assert result.result_type == ResultType.COMPLETED

    def test_run_waiting_timedout(self, jhelper, observabilityfeature, snap, run):
        jhelper.wait_application_ready.side_effect = TimeoutException("timed out")

        observabilityfeature.grafana_offer_url = "remotecos:admin/grafana"
        observabilityfeature.prometheus_offer_url = "remotecos:admin/prometheus"
        observabilityfeature.loki_offer_url = "remotecos:admin/loki"
        observabilityfeature.deployment.openstack_machines_model = "test-model"
        step = observability_feature.IntegrateRemoteCosOffersStep(
            observabilityfeature, jhelper
        )

        result = step.run()
        jhelper.wait_application_ready.assert_called()
        assert result.result_type == ResultType.FAILED
        assert result.message == "timed out"


class TestRemoveRemoteCosOffersStep:
    def test_run(self, jhelper, observabilityfeature, snap, run):
        observabilityfeature.deployment.openstack_machines_model = "test-model"
        jhelper.get_model_status.side_effect = [
            {
                "relations": [
                    {"key": "grafana-agent:logging-consumer loki:loki_push_api"}
                ]
            },
            {
                "relations": [
                    {
                        "key": "openstack-hypervisor:identity-service keystone:identity_service"
                    }
                ]
            },
        ]
        step = observability_feature.RemoveRemoteCosOffersStep(
            observabilityfeature, jhelper
        )

        result = step.run()
        run.assert_called_once()
        jhelper.wait_application_ready.assert_called()
        assert result.result_type == ResultType.COMPLETED

    def test_run_no_remote_offers(self, jhelper, observabilityfeature, snap, run):
        observabilityfeature.deployment.openstack_machines_model = "test-model"
        jhelper.get_model_status.side_effect = [{}, {}]
        step = observability_feature.RemoveRemoteCosOffersStep(
            observabilityfeature, jhelper
        )

        result = step.run()
        run.assert_not_called()
        jhelper.wait_application_ready.assert_called()
        assert result.result_type == ResultType.COMPLETED

    def test_run_waiting_timedout(self, jhelper, observabilityfeature, snap, run):
        observabilityfeature.deployment.openstack_machines_model = "test-model"
        jhelper.get_model_status.side_effect = [
            {
                "relations": [
                    {"key": "grafana-agent:logging-consumer loki:loki_push_api"}
                ]
            },
            {
                "relations": [
                    {
                        "key": "openstack-hypervisor:identity-service keystone:identity_service"
                    }
                ]
            },
        ]
        jhelper.wait_application_ready.side_effect = TimeoutException("timed out")
        step = observability_feature.RemoveRemoteCosOffersStep(
            observabilityfeature, jhelper
        )

        result = step.run()
        run.assert_called_once()
        jhelper.wait_application_ready.assert_called()
        assert result.result_type == ResultType.FAILED
        assert result.message == "timed out"
