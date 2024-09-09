# Optimization service

This feature provides Resource Optimization service for Sunbeam. It's based on [Watcher](https://docs.openstack.org/watcher/latest/), a Resource Optimization service for OpenStack.

## Installation

To enable the Resource Optimization service, you need an already bootstraped Sunbeam instance. Then, you can install the feature with:

```bash
sunbeam enable resource-optimization
```

## Contents

This feature will install the following services:
- Watcher: Resource Optimization service for OpenStack [charm](https://opendev.org/openstack/charm-watcher-k8s) [ROCK](https://github.com/canonical/ubuntu-openstack-rocks/tree/main/rocks/watcher-consolidated)
- MySQL Router for Watcher [charm](https://github.com/canonical/mysql-router-k8s-operator) [ROCK](https://github.com/canonical/charmed-mysql-rock)
- MySQL Instance in the case of a multi-mysql installation (for large deployments) [charm](https://github.com/canonical/mysql-k8s-operator) [ROCK](https://github.com/canonical/charmed-mysql-rock)

Services are constituted of charms, i.e. operator code, and ROCKs, the corresponding OCI images.


## Removal

To remove the feature, run:

```bash
sunbeam disable resource-optimization
```
