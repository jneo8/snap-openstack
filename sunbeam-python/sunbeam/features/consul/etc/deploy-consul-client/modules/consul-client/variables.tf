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

variable "name" {
  description = "Name of the deployed Consul client operator"
  type        = string
  default     = "consul"
}

variable "channel" {
  description = "Channel to use when deploying consul client machine charm"
  type        = string
  default     = "latest/edge"
}

variable "revision" {
  description = "Channel revision to use when deploying consul client machine charm"
  type        = number
  default     = null
}

variable "base" {
  description = "Operator base"
  type        = string
  default     = "ubuntu@22.04"
}

variable "resource-configs" {
  description = "Config to use when deploying consul client machine charm"
  type        = map(string)
  default     = {}
}

variable "endpoint-bindings" {
  description = "Endpoint bindings for consul client"
  type        = set(map(string))
  default     = null
}

variable "principal-application" {
  description = "Name of the deployed principal application that integrates with consul-client"
  type        = string
  default     = null
}

variable "principal-application-model" {
  description = "Name of the model principal application is deployed in"
  type        = string
  default     = "controller"
}

variable "consul-cluster-offer-url" {
  description = "Consul cluster offer url for client to join the cluster"
  type        = string
  default     = null
}