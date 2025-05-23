# HashiCorp Vault: Initialize and Unseal Guide

This guide explains how to initialize and unseal your self-hosted HashiCorp Vault instance on Kubernetes.

---

## 1. Port-forward to the Vault Service

Open a terminal and run:

```sh
kubectl port-forward svc/vault 8200:8200 -n flux-system
```

---

## 2. Initialize Vault

Open a **new terminal** and set the Vault address:

```sh
export VAULT_ADDR='http://127.0.0.1:8200'
```

Then initialize Vault:

```sh
vault operator init
```

> **Important:**  
> Save the unseal keys and root token output somewhere safe!  
> You will need them to unseal and administer Vault.

---

## 3. Unseal Vault

Unseal Vault by running the following command **three times**, each with a different unseal key:

```sh
vault operator unseal <unseal-key-1>
vault operator unseal <unseal-key-2>
vault operator unseal <unseal-key-3>
```

---

## 4. (Optional) Login to the Vault UI

- Visit [http://localhost:8200/ui](http://localhost:8200/ui)
- Log in with the **root token** from the initialization step.

---

## 5. Access Vault via Ingress

Once unsealed, the Vault pod will accept connections and your Ingress at `/vault` will proxy correctly.

---

**You’re ready to use Vault!**