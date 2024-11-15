# Terraform module for deployment of Consul client
#
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

terraform {
  required_providers {
    juju = {
      source  = "juju/juju"
      version = "= 0.14.0"
    }
  }
}

resource "juju_application" "consul-client" {
  name  = var.name
  trust = false
  model = var.principal-application-model
  units = 0

  charm {
    name     = "consul-client"
    channel  = var.channel
    revision = var.revision
    base     = var.base
  }

  config            = var.resource-configs
  endpoint_bindings = var.endpoint-bindings
}

# juju integrate <principal-application>:juju-info consul-client:general-info
resource "juju_integration" "principal-application-to-consul-client" {
  model = var.principal-application-model

  application {
    name     = juju_application.consul-client.name
    endpoint = "juju-info"
  }

  application {
    name     = var.principal-application
    endpoint = "juju-info"
  }
}

# juju integrate <consul-client>:consul-cluster consul-cluster-offer-url
resource "juju_integration" "consul-client-to-consul-server" {
  count = var.consul-cluster-offer-url != null ? 1 : 0
  model = var.principal-application-model

  application {
    name     = juju_application.consul-client.name
    endpoint = "consul-cluster"
  }

  application {
    offer_url = var.consul-cluster-offer-url
  }
}