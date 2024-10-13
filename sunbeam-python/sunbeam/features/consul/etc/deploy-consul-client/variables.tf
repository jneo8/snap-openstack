# Terraform manifest for deployment of Consul client
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

variable "principal-application" {
  description = "Name of the deployed principal application that integrates with consul-client"
  default     = "openstack-hypervisor"
}

variable "principal-application-model" {
  description = "Name of the model principal application is deployed in"
  default     = "controller"
}

variable "consul-channel" {
  description = "Channel to use when deploying consul-client machine charm"
  type        = string
  default     = "latest/edge"
}

variable "consul-revision" {
  description = "Channel revision to use when deploying consul-client machine charm"
  type        = number
  default     = null
}

variable "consul-config" {
  description = "Config to use when deploying consul-client machine charm"
  type        = map(string)
  default     = {}
}

variable "consul-config-map" {
  description = "Operator configs for specific Consul client deployment (applied on top of consul-config for specific application)"
  type        = map(map(string))
  default     = {}
}

variable "consul-endpoint-bindings-map" {
  description = "Endpoint bindings for consul-client per application"
  type        = map(set(map(string)))
  default     = null
}

variable "openstack-state-backend" {
  description = "backend type used for openstack state"
  type        = string
  default     = "local"
}

variable "openstack-state-config" {
  type = map(any)
}

variable "enable-consul-management" {
  description = "Enable Consul client on management network"
  type        = bool
  default     = false
}

variable "enable-consul-tenant" {
  description = "Enable Consul client on tenant network"
  type        = bool
  default     = false
}

variable "enable-consul-storage" {
  description = "Enable Consul client on storage network"
  type        = bool
  default     = false
}
