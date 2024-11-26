# Vault service

This feature provides Vault service for Sunbeam. It's based on [Vault](https://developer.hashicorp.com/vault/docs).
The feature is used as a backend to store secrets for OpenStack Barbican service.

## Installation

To enable the Vault service, you need an already bootstraped Sunbeam instance. Then, you can install the feature with:

```bash
sunbeam enable vault
```

## Vault configuration

Enabling Vault service deploys vault and keeps them in sealed, uninitialized state.

Initialize the vault using the command:

```bash
sunbeam vault init KEY_SHARES KEY_THRESHOLD
```

This command outputs vault keys and the root token.
Copy each of them in separate file and keep them secure.

Unseal the vault using the command:

```bash
cat <key file> | sunbeam vault unseal -
```

Run this command KEY_THRESHOLD times with different key each time.
This will unseal the leader unit.

Repeat the unseal process again to unseal the non-leader units.

Authorize Vault charm using the command:

```bash
cat <root token file> | sunbeam vault authorize-charm -
```

## Development mode

Vault can be deployed in development mode which will automatically initialize, unseal the vault and
authorize the vault charm.

This can be done during enable step using the command:

```bash
sunbeam enable vault --dev-mode
```

Since this is for development purpose only 1 key share will be created.

In cases where the vault is sealed again due to restart of pod or node, rerun enable command
again with --dev-mode option to unseal the vault.

## Contents

This feature will install the following services:
- Vault: Secert and Encryption management system [charm](https://github.com/canonical/vault-k8s-operator/) [ROCK](https://github.com/canonical/vault-rock)

Services are constituted of charms, i.e. operator code, and ROCKs, the corresponding OCI images.


## Removal

To remove the feature, run:

```bash
sunbeam disable vault
```
