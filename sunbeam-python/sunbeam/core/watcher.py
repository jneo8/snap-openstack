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
from typing import Any

import tenacity
from watcherclient import v1 as watcher
from watcherclient.common.apiclient.exceptions import NotFound
from watcherclient.v1 import client as watcher_client

from sunbeam.core.common import SunbeamException, read_config
from sunbeam.core.deployment import Deployment
from sunbeam.core.juju import JujuHelper
from sunbeam.core.openstack_api import get_admin_connection
from sunbeam.steps.openstack import REGION_CONFIG_KEY

LOG = logging.getLogger(__name__)

# Timeout of seconds while waiting for the watcher resource to reach the target state.
WAIT_TIMEOUT = 60 * 3
# Sleep interval (in seconds) between querying watcher resources.
WAIT_SLEEP_INTERVAL = 5
ENABLE_MAINTENANCE_AUDIT_TEMPLATE_NAME = "Sunbeam Cluster Maintaining Template"
ENABLE_MAINTENANCE_STRATEGY_NAME = "host_maintenance"
ENABLE_MAINTENANCE_GOAL_NAME = "cluster_maintaining"

WORKLOAD_BALANCING_GOAL_NAME = "workload_balancing"
WORKLOAD_BALANCING_STRATEGY_NAME = "workload_stabilization"
WORKLOAD_BALANCING_AUDIT_TEMPLATE_NAME = "Sunbeam Cluster Workload Balancing Template"


def get_watcher_client(deployment: Deployment) -> watcher_client.Client:
    region = read_config(deployment.get_client(), REGION_CONFIG_KEY)["region"]
    conn = get_admin_connection(
        jhelper=JujuHelper(deployment.get_connected_controller())
    )

    watcher_endpoint = conn.session.get_endpoint(
        service_type="infra-optim",
        region_name=region,
    )
    return watcher_client.Client(session=conn.session, endpoint=watcher_endpoint)


def _create_host_maintenance_audit_template(
    client: watcher_client.Client,
) -> watcher.AuditTemplate:
    template = client.audit_template.create(
        name=ENABLE_MAINTENANCE_AUDIT_TEMPLATE_NAME,
        description="Audit template for cluster maintaining",
        goal=ENABLE_MAINTENANCE_GOAL_NAME,
        strategy=ENABLE_MAINTENANCE_STRATEGY_NAME,
    )
    return template


def _create_workload_balancing_audit_template(
    client: watcher_client.Client,
) -> watcher.AuditTemplate:
    template = client.audit_template.create(
        name=WORKLOAD_BALANCING_AUDIT_TEMPLATE_NAME,
        description="Audit template for workload balancing",
        goal=WORKLOAD_BALANCING_GOAL_NAME,
        strategy=WORKLOAD_BALANCING_STRATEGY_NAME,
    )
    return template


def get_enable_maintenance_audit_template(
    client: watcher_client.Client,
) -> watcher.AuditTemplate:
    try:
        template = client.audit_template.get(ENABLE_MAINTENANCE_AUDIT_TEMPLATE_NAME)
    except NotFound:
        template = _create_host_maintenance_audit_template(client=client)
    return template


def get_workload_balancing_audit_template(
    client: watcher_client.Client,
) -> watcher.AuditTemplate:
    try:
        template = client.audit_template.get(WORKLOAD_BALANCING_AUDIT_TEMPLATE_NAME)
    except NotFound:
        template = _create_workload_balancing_audit_template(client=client)
    return template


@tenacity.retry(
    reraise=True,
    stop=tenacity.stop_after_delay(WAIT_TIMEOUT),
    wait=tenacity.wait_fixed(WAIT_SLEEP_INTERVAL),
)
def _wait_resource_in_target_state(
    client: watcher_client.Client,
    resource_name: str,
    resource_uuid: str,
    states: list[str] = ["SUCCEEDED", "FAILED"],
) -> watcher.Audit:
    src = getattr(client, resource_name).get(resource_uuid)
    if src.state not in states:
        raise SunbeamException(f"{resource_name} {resource_uuid} not in target state")
    return src


def create_audit(
    client: watcher_client.Client,
    template: watcher.AuditTemplate,
    audit_type: str = "ONESHOT",
    parameters: dict[str, Any] = {},
) -> watcher.Audit:
    audit = client.audit.create(
        audit_template_uuid=template.uuid,
        audit_type=audit_type,
        parameters=parameters,
    )
    audit_details = _wait_resource_in_target_state(
        client=client,
        resource_name="audit",
        resource_uuid=audit.uuid,
    )

    if audit_details.state == "SUCCEEDED":
        LOG.debug(f"Create Watcher audit {audit.uuid} successfully")
    else:
        LOG.debug(f"Create Watcher audit {audit.uuid} failed")
        raise SunbeamException(
            f"Create watcher audit failed, template: {template.name}"
        )

    _check_audit_plans_recommended(client=client, audit=audit)
    return audit


def _check_audit_plans_recommended(client: watcher_client.Client, audit: watcher.Audit):
    action_plans = client.action_plan.list(audit=audit.uuid)
    # Verify all the action_plan's state is RECOMMENDED.
    # In case there is not action been generated, the action plan state
    # will be SUCCEEDED at the beginning.
    if not all(plan.state in ["RECOMMENDED", "SUCCEEDED"] for plan in action_plans):
        raise SunbeamException(
            f"Not all action plan for audit({audit.uuid}) is RECOMMENDED"
        )


def get_actions(
    client: watcher_client.Client, audit: watcher.Audit
) -> list[watcher.Action]:
    """Get list of actions by audit."""
    return client.action.list(audit=audit.uuid, detail=True)


def exec_audit(client: watcher_client.Client, audit: watcher.Audit):
    """Run audit's action plans."""
    action_plans = client.action_plan.list(audit=audit.uuid)
    for action_plan in action_plans:
        _exec_plan(client=client, action_plan=action_plan)
    LOG.info(f"All Action plan for Audit {audit.uuid} execution successfully")


def _exec_plan(client: watcher_client.Client, action_plan: watcher.ActionPlan):
    """Run action plan."""
    if action_plan.state == "SUCCEEDED":
        LOG.debug(f"action plan {action_plan.uuid} state is SUCCEEDED, skip execution")
        return
    client.action_plan.start(action_plan_id=action_plan.uuid)

    action_plan_details = _wait_resource_in_target_state(
        client=client,
        resource_name="action_plan",
        resource_uuid=action_plan.uuid,
    )

    if action_plan_details.state == "SUCCEEDED":
        LOG.debug(f"Action plan {action_plan.uuid} execution successfully")
    else:
        LOG.debug(f"Action plan {action_plan.uuid} execution failed")

    # Even if an action fails, the action plan can still be in the SUCCEEDED state.
    # To handle this, we check if there are any failed actions at this point.
    _raise_on_failed_action(client=client, action_plan=action_plan)


def _raise_on_failed_action(
    client: watcher_client.Client, action_plan: watcher.ActionPlan
):
    """Raise exception on failed action."""
    actions = client.action.list(action_plan=action_plan.uuid, detail=True)
    info = {}
    for action in actions:
        if not action.state == "FAILED":
            continue
        info[action.uuid] = {
            "action": action.action_type,
            "updated-at": action.updated_at,
            "description": action.description,
            "input_parameters": action.input_parameters,
        }
    if len(info) > 0:
        raise SunbeamException(f"Actions in FAILED state. {info}")
