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

variable "machine-ids" {
  description = "List of machine ids to include"
  type        = list(string)
  default     = []
}

variable "charm-channel" {
  description = "Charm channel to deploy openstack-hypervisor charm from"
  type        = string
  default     = "2024.1/stable"
}

variable "charm-revision" {
  description = "Charm channel revision to deploy openstack-hypervisor charm from"
  type        = number
  default     = null
}

variable "charm-config" {
  description = "Charm config to deploy openstack-hypervisor charm from"
  type        = map(string)
  default     = {}
}

variable "machine-model" {
  description = "Name of model to deploy sunbeam-machine into."
  type        = string
}
