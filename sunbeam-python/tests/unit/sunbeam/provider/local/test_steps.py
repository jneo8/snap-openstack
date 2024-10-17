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

import sunbeam.core.questions
import sunbeam.provider.local.steps as local_steps
import sunbeam.utils


@pytest.fixture(autouse=True)
def mock_run_sync(mocker):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()

    def run_sync(coro):
        return loop.run_until_complete(coro)

    mocker.patch("sunbeam.commands.configure.run_sync", run_sync)
    yield
    loop.close()


@pytest.fixture()
def cclient():
    yield Mock()


@pytest.fixture()
def load_answers():
    with patch.object(sunbeam.core.questions, "load_answers") as p:
        yield p


@pytest.fixture()
def write_answers():
    with patch.object(sunbeam.core.questions, "write_answers") as p:
        yield p


@pytest.fixture()
def question_bank():
    with patch.object(sunbeam.core.questions, "QuestionBank") as p:
        yield p


@pytest.fixture()
def jhelper():
    yield AsyncMock()


class TestLocalSetHypervisorUnitsOptionsStep:
    def test_has_prompts(self, cclient, jhelper):
        step = local_steps.LocalSetHypervisorUnitsOptionsStep(
            cclient, "maas0.local", jhelper, "test-model"
        )
        assert step.has_prompts()

    def test_prompt_remote(
        self,
        cclient,
        jhelper,
        load_answers,
        question_bank,
    ):
        load_answers.return_value = {"user": {"remote_access_location": "remote"}}
        local_hypervisor_bank_mock = Mock()
        question_bank.return_value = local_hypervisor_bank_mock
        local_hypervisor_bank_mock.nic.ask.return_value = "eth2"
        step = local_steps.LocalSetHypervisorUnitsOptionsStep(
            cclient, "maas0.local", jhelper, "test-model"
        )
        nics_result = {
            "nics": [
                {"name": "eth2", "up": True, "connected": True, "configured": False}
            ],
            "candidates": ["eth2"],
        }
        step._fetch_nics = AsyncMock(return_value=nics_result)
        step.prompt()
        assert step.nics["maas0.local"] == "eth2"

    def test_prompt_remote_join(
        self,
        cclient,
        jhelper,
        load_answers,
        question_bank,
    ):
        load_answers.return_value = {"user": {"remote_access_location": "remote"}}
        local_hypervisor_bank_mock = Mock()
        question_bank.return_value = local_hypervisor_bank_mock
        local_hypervisor_bank_mock.nic.ask.return_value = "eth2"
        step = local_steps.LocalSetHypervisorUnitsOptionsStep(
            cclient, "maas0.local", jhelper, "test-model", join_mode=True
        )
        nics_result = {
            "nics": [
                {"name": "eth2", "up": True, "connected": True, "configured": False}
            ],
            "candidates": ["eth2"],
        }
        step._fetch_nics = AsyncMock(return_value=nics_result)
        step.prompt()
        assert step.nics["maas0.local"] == "eth2"

    def test_prompt_local(self, cclient, jhelper, load_answers, question_bank):
        load_answers.return_value = {"user": {"remote_access_location": "local"}}
        local_hypervisor_bank_mock = Mock()
        question_bank.return_value = local_hypervisor_bank_mock
        local_hypervisor_bank_mock.nic.ask.return_value = "eth12"
        step = local_steps.LocalSetHypervisorUnitsOptionsStep(
            cclient, "maas0.local", jhelper, "tes-model"
        )
        step.prompt()
        assert len(step.nics) == 0

    def test_prompt_local_join(
        self,
        cclient,
        jhelper,
        load_answers,
        question_bank,
    ):
        load_answers.return_value = {"user": {"remote_access_location": "local"}}
        local_hypervisor_bank_mock = Mock()
        question_bank.return_value = local_hypervisor_bank_mock
        local_hypervisor_bank_mock.nic.ask.return_value = "eth2"
        step = local_steps.LocalSetHypervisorUnitsOptionsStep(
            cclient, "maas0.local", jhelper, "test-model", join_mode=True
        )
        nics_result = {
            "nics": [
                {"name": "eth2", "up": True, "connected": True, "configured": False}
            ],
            "candidates": ["eth2"],
        }
        step._fetch_nics = AsyncMock(return_value=nics_result)
        step.prompt()
        assert step.nics["maas0.local"] == "eth2"
