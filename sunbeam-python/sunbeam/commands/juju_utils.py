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
from rich.console import Console
from snaphelpers import Snap

from sunbeam.clusterd.client import Client
from sunbeam.commands.juju import RegisterRemoteJujuUserStep, UnregisterJujuController
from sunbeam.jobs.common import run_plan
from sunbeam.jobs.deployment import Deployment

LOG = logging.getLogger(__name__)
console = Console()


@click.command()
@click.option(
    "-f",
    "--force",
    is_flag=True,
    help="Force replacement if controller already exists with the same name",
)
@click.argument("name", type=str)
@click.argument("token", type=str)
@click.pass_context
def register_controller(ctx: click.Context, name: str, token: str, force: bool) -> None:
    """Register existing Juju controller."""
    deployment: Deployment = ctx.obj
    try:
        client = deployment.get_client()
    except ValueError:
        client = Client.from_socket()
    data_location = Snap().paths.user_data

    plan = [
        RegisterRemoteJujuUserStep(client, token, name, data_location, replace=force)
    ]

    run_plan(plan, console)
    console.print(f"Controller {name} registered")


@click.command()
@click.argument("name", type=str)
@click.pass_context
def unregister_controller(ctx: click.Context, name: str) -> None:
    """Unregister external Juju controller."""
    data_location = Snap().paths.user_data

    plan = [UnregisterJujuController(name, data_location)]

    run_plan(plan, console)
    console.print(f"Controller {name} unregistered")
