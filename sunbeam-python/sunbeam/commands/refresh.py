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
import logging
from pathlib import Path

import click
from rich.console import Console

from sunbeam.core.common import run_plan
from sunbeam.core.deployment import Deployment
from sunbeam.core.juju import JujuHelper
from sunbeam.core.manifest import AddManifestStep
from sunbeam.steps.upgrades.base import UpgradeCoordinator
from sunbeam.steps.upgrades.inter_channel import ChannelUpgradeCoordinator
from sunbeam.steps.upgrades.intra_channel import LatestInChannelCoordinator
from sunbeam.utils import click_option_show_hints

LOG = logging.getLogger(__name__)
console = Console()


@click.command()
@click.option(
    "-c",
    "--clear-manifest",
    is_flag=True,
    default=False,
    help="Clear the manifest file.",
    type=bool,
)
@click.option(
    "-m",
    "--manifest",
    "manifest_path",
    help="Manifest file.",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option(
    "--upgrade-release",
    is_flag=True,
    show_default=True,
    default=False,
    help="Upgrade OpenStack release.",
)
@click_option_show_hints
@click.pass_context
def refresh(
    ctx: click.Context,
    upgrade_release: bool,
    manifest_path: Path | None = None,
    clear_manifest: bool = False,
    show_hints: bool = False,
) -> None:
    """Refresh deployment.

    Refresh the deployment. If --upgrade-release is supplied then charms are
    upgraded the channels aligned with this snap revision
    """
    if clear_manifest and manifest_path:
        raise click.ClickException(
            "Options manifest and clear_manifest are mutually exclusive"
        )

    deployment: Deployment = ctx.obj
    client = deployment.get_client()
    # Validate manifest file
    manifest = None
    if clear_manifest:
        run_plan([AddManifestStep(client, clear=True)], console, show_hints)
    elif manifest_path:
        manifest = deployment.get_manifest(manifest_path)
        run_plan([AddManifestStep(client, manifest_path)], console, show_hints)

    if not manifest:
        LOG.debug("Getting latest manifest from cluster db")
        manifest = deployment.get_manifest()

    LOG.debug(f"Manifest used for deployment - core: {manifest.core}")
    jhelper = JujuHelper(deployment.get_connected_controller())
    upgrade_coordinator: UpgradeCoordinator
    if upgrade_release:
        upgrade_coordinator = ChannelUpgradeCoordinator(
            deployment, client, jhelper, manifest
        )
        upgrade_coordinator.run_plan(show_hints)
    else:
        upgrade_coordinator = LatestInChannelCoordinator(
            deployment, client, jhelper, manifest
        )
        upgrade_coordinator.run_plan(show_hints)
    click.echo("Refresh complete.")
