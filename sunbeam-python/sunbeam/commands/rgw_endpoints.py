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
import yaml
from rich.console import Console
from rich.table import Table

from sunbeam.jobs import juju
from sunbeam.jobs.checks import VerifyBootstrappedCheck
from sunbeam.jobs.common import FORMAT_TABLE, FORMAT_YAML, run_preflight_checks
from sunbeam.jobs.deployment import Deployment

LOG = logging.getLogger(__name__)
console = Console()


@click.command()
@click.option(
    "-f",
    "--format",
    type=click.Choice([FORMAT_TABLE, FORMAT_YAML]),
    default=FORMAT_TABLE,
    help="Output format, defaults to table.",
)
@click.pass_context
def radosgw_url(ctx: click.Context, format: str) -> None:
    """Retrieve Rados Gateway Endpoints."""
    deployment: Deployment = ctx.obj
    preflight_checks = []
    preflight_checks.append(VerifyBootstrappedCheck(deployment.get_client()))
    run_preflight_checks(preflight_checks, console)
    jhelper = juju.JujuHelper(deployment.get_connected_controller())

    with console.status("Retrieving rgw endpoints from MicroCeph service ... "):
        # Retrieve config from juju actions
        model = deployment.infrastructure_model
        app = "microceph"
        action_cmd = "get-rgw-endpoints"
        unit = juju.run_sync(jhelper.get_leader_unit(app, model))
        if not unit:
            _message = f"Unable to get {app} leader"
            raise click.ClickException(_message)

        action_result = juju.run_sync(jhelper.run_action(unit, model, action_cmd))

        if action_result.get("return-code", 0) > 1:
            _message = "Unable to retrieve rgw endpoints from MicroCeph service"
            raise click.ClickException(_message)

        action_result.pop("return-code")
        if format == FORMAT_TABLE:
            table = Table()
            table.add_column("Endpoint", justify="center")
            table.add_column("URL", justify="center")
            table.add_row("S3", action_result.get("s3"))
            table.add_row("Swift", action_result.get("swift"))
            console.print(table)
        else:
            console.print(yaml.dump(action_result, sort_keys=True))
