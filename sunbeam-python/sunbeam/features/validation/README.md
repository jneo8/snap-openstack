# Validation

This feature provides OpenStack Integration Test Suite: tempest for Sunbeam. It
is based on [tempest-k8s][1] and [tempest-rock][2] project.

## Installation

To enable cloud validation, you need an already bootstrapped Sunbeam instance.
Then, you can install the feature with:

```bash
sunbeam enable validation
```

This feature is also related to the `observability` feature.

## Contents

This feature will install [tempest-k8s][1], and provide the `validation`
subcommand to sunbeam client. For more information, please run

```
sunbeam validation --help
```

Additionally, if you enable `observability` feature, you will also get the
periodic cloud validation feature from this feature. The loki alert rules for
validation results (e.g. when some tempest tests failed) will be configured, and
a summary of validation results will also be shown in Grafana dashboard.

You can configure the periodic validation schedule using `configure` subcommand
in sunbeam client. For more information, please run

```
sunbeam configure validation --help
```

## Removal

To remove the feature, run:

```bash
sunbeam disable validation
```

[1]: https://opendev.org/openstack/sunbeam-charms/src/branch/main/charms/tempest-k8s
[2]: https://github.com/canonical/ubuntu-openstack-rocks/tree/main/rocks/tempest
