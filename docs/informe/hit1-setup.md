# Hit #1 — Introducción al mundo de CUDA

## Entorno utilizado

- **Plataforma:** Google Colab (T4 GPU)
- **CUDA Toolkit:** 12.x (preinstalado en Colab)
- **Driver NVIDIA:** provisto por el entorno Colab
- **Lenguaje:** C++ con extensiones CUDA

## Motivo de la elección

La máquina local tiene GPU AMD integrada, incompatible con CUDA. Google Colab ofrece:

- GPU NVIDIA T4 gratuita con CUDA preinstalado
- Sin configuración adicional
- Acceso vía navegador
- Compatible con `nvcc` y `%%cu` magic

## Verificación

```bash
!nvcc --version
!nvidia-smi
```

## Recursos consultados

- CUDA Toolkit: https://developer.nvidia.com/cuda-downloads
- Google Colab: https://colab.research.google.com
- Nsight VS Code Edition: https://marketplace.visualstudio.com/items?itemName=NVIDIA.nsight-vscode-edition
