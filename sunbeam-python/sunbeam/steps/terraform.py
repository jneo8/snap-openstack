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
import shutil

from rich.status import Status

from sunbeam.core.common import BaseStep, Result, ResultType
from sunbeam.core.deployment import Deployment

LOG = logging.getLogger(__name__)


class CleanTerraformPlansStep(BaseStep):
    def __init__(self, deployment: Deployment):
        super().__init__(
            "Clean terraform directories", "Cleaning terraform directories"
        )
        self.tf_plans = deployment.plans_directory

    def is_skip(self, status: Status | None = None) -> Result:
        """Determines if the step should be skipped or not.

        :return: ResultType.SKIPPED if the Step should be skipped,
                ResultType.COMPLETED or ResultType.FAILED otherwise
        """
        if not self.tf_plans.exists():
            return Result(ResultType.SKIPPED)

        return Result(ResultType.COMPLETED)

    def run(self, status: Status | None = None) -> Result:
        """Delete terraform plan directories."""
        try:
            shutil.rmtree(self.tf_plans)
        except Exception as e:
            LOG.error("Error cleaning terraform directories: %s", e)
            return Result(ResultType.FAILED)
        return Result(ResultType.COMPLETED)
