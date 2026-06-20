# Secrets para el cluster GPU (k3s)

Estos archivos cifrados con SOPS + Age se despliegan en el CI/CD al cluster k3s.

## Setup

```bash
# 1. Generar par de claves Age
age-keygen -o ~/.config/sops/age/keys.txt

# 2. Actualizar .sops.yaml con la clave pública

# 3. Cifrar secrets
sops --encrypt \
  --age age1... \
  rabbitmq-credentials.yaml > rabbitmq-credentials.enc.yaml
```

## Archivos

| Archivo | Contenido |
|---------|-----------|
| `rabbitmq-credentials.enc.yaml` | Usuario/contraseña RabbitMQ |
| `rabbitmq-ca.enc.yaml` | CA certificado para TLS |

## En CI/CD

El workflow `04-gpu-workers.yml` usa GitHub Secrets directamente
(no SOPS), como alternativa más simple. SOPS queda disponible
si se prefiere GitOps.
