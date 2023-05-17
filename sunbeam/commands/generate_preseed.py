# Copyright (c) 2022 Canonical Ltd.
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
from rich.console import Console

import sunbeam.jobs.questions
from sunbeam.clusterd.client import Client
from sunbeam.clusterd.service import ClusterServiceUnavailableException
from sunbeam.commands.configure import (
    CLOUD_CONFIG_SECTION,
    ext_net_questions,
    ext_net_questions_local_only,
    user_questions,
)
from sunbeam.commands.microk8s import microk8s_addons_questions

LOG = logging.getLogger(__name__)
console = Console()


def show_questions(
    question_bank, section=None, section_description=None, comment_out=False
):
    ident = ""
    if comment_out:
        comment = "# "
    else:
        comment = ""
    if section:
        if section_description:
            console.print(f"{comment}{ident}# {section_description}")
        console.print(f"{comment}{ident}{section}:")
        ident = "  "
    for key, question in question_bank.questions.items():
        default = question.calculate_default() or ""
        try:
            # If the question implements a render_default function then
            # use it. It may be needed to mask passwords etc
            default = question.render_default(default)
        except AttributeError:
            pass
        console.print(f"{comment}{ident}# {question.question}")
        console.print(f"{comment}{ident}{key}: {default}")


@click.command()
def generate_preseed() -> None:
    """Generate preseed file."""
    client = Client()
    try:
        variables = sunbeam.jobs.questions.load_answers(client, CLOUD_CONFIG_SECTION)
    except ClusterServiceUnavailableException:
        variables = {}
    microk8s_addons_bank = sunbeam.jobs.questions.QuestionBank(
        questions=microk8s_addons_questions(),
        console=console,
        previous_answers=variables.get("addons", {}),
    )
    show_questions(microk8s_addons_bank, section="addons")
    user_bank = sunbeam.jobs.questions.QuestionBank(
        questions=user_questions(),
        console=console,
        previous_answers=variables.get("user"),
    )
    show_questions(user_bank, section="user")
    ext_net_bank_local = sunbeam.jobs.questions.QuestionBank(
        questions=ext_net_questions_local_only(),
        console=console,
        previous_answers=variables.get("external_network"),
    )
    show_questions(
        ext_net_bank_local,
        section="external_network",
        section_description="Local Access",
    )
    ext_net_bank_remote = sunbeam.jobs.questions.QuestionBank(
        questions=ext_net_questions(),
        console=console,
        previous_answers=variables.get("external_network"),
    )
    show_questions(
        ext_net_bank_remote,
        section="external_network",
        section_description="Remote Access",
        comment_out=True,
    )
