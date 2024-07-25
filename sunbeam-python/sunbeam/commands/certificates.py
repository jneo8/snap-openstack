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

from sunbeam.jobs.common import BaseStep, Result, ResultType, Status
from sunbeam.jobs.juju import (
    ApplicationNotFoundException,
    JujuHelper,
    JujuWaitException,
    TimeoutException,
    run_sync,
)
from sunbeam.jobs.manifest import CharmManifest, Manifest

LOG = logging.getLogger(__name__)
APPLICATION = "tls-operator"
CHARM = "self-signed-certificates"
CERTIFICATES_APP_TIMEOUT = 1200


class DeployCertificatesProviderApplicationStep(BaseStep):
    """Deploy tls operator application."""

    def __init__(
        self,
        jhelper: JujuHelper,
        manifest: Manifest,
        model: str,
    ):
        super().__init__(
            "Deploy tls operator",
            "Deploying TLS Operator",
        )
        self.jhelper = jhelper
        self.manifest = manifest
        self.model = model
        self.app = APPLICATION

    def is_skip(self, status: Status | None = None) -> Result:
        """Check whether or not to deploy tls operator."""
        try:
            run_sync(self.jhelper.get_application(self.app, self.model))
        except ApplicationNotFoundException:
            return Result(ResultType.COMPLETED)
        return Result(ResultType.SKIPPED)

    def run(self, status: Status | None = None) -> Result:
        """Deploy sunbeam clusterd to infra machines."""
        self.update_status(status, "fetching infra machines")
        clusterd_machines = run_sync(self.jhelper.get_machines(self.model))
        machines = list(clusterd_machines.keys())

        if len(machines) == 0:
            return Result(ResultType.FAILED, f"No machines found in {self.model} model")

        # Deploy on first controller machine
        machines = machines[:1]
        self.update_status(status, "deploying application")
        charm_manifest: CharmManifest = self.manifest.software.charms[CHARM]
        run_sync(
            self.jhelper.deploy(
                APPLICATION,
                CHARM,
                self.model,
                1,
                channel=charm_manifest.channel,
                revision=charm_manifest.revision,
                to=machines,
                config=charm_manifest.config,
            )
        )

        apps = run_sync(self.jhelper.get_application_names(self.model))
        try:
            run_sync(
                self.jhelper.wait_until_active(
                    self.model,
                    apps,
                    timeout=CERTIFICATES_APP_TIMEOUT,
                )
            )
        except (JujuWaitException, TimeoutException) as e:
            LOG.warning(str(e))
            return Result(ResultType.FAILED, str(e))

        return Result(ResultType.COMPLETED)
