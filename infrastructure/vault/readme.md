How to Fix: Initialize and Unseal Vault
Port-forward to the Vault service (so you can access the API/UI directly):

kubectl port-forward svc/vault 8200:8200 -n flux-system

Initialize Vault (in a new terminal):

export VAULT_ADDR='http://127.0.0.1:8200'
vault operator init

Save the unseal keys and root token output!
Unseal Vault (repeat 3 times with different unseal keys):

vault operator unseal <unseal-key-1>
vault operator unseal <unseal-key-2>
vault operator unseal <unseal-key-3>

(Optional) Login to the UI

Visit http://localhost:8200/ui and log in with the root token.
Now your Ingress should work!

Once unsealed, the Vault pod will accept connections and your Ingress at /vault will proxy correctly.