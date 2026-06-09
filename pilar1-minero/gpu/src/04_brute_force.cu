#include <cstdio>
#include <cstring>
#include <cstdlib>
#include "md5.cuh"

__device__ int ull_to_str(unsigned long long n, unsigned char* out) {
    if (n == 0) {
        out[0] = '0';
        return 1;
    }
    unsigned char temp[20];
    int len = 0;
    while (n > 0) {
        temp[len++] = '0' + (n % 10);
        n /= 10;
    }
    for (int i = 0; i < len; i++)
        out[i] = temp[len - 1 - i];
    return len;
}

__global__ void brute_force_kernel(
    const unsigned char* base, size_t base_len,
    const unsigned char* target, int target_bytes,
    unsigned long long* found_nonce,
    unsigned char* found_hash
) {
    unsigned long long tid = blockIdx.x * blockDim.x + threadIdx.x;
    unsigned long long total = gridDim.x * blockDim.x;
    unsigned char buf[256];
    unsigned char hash[16];

    for (int i = 0; i < (int)base_len; i++)
        buf[i] = base[i];

    for (unsigned long long nonce = tid; ; nonce += total) {
        if (*found_nonce != ~0ULL)
            return;

        int nlen = ull_to_str(nonce, buf + base_len);
        md5_hash(buf, base_len + nlen, hash);

        bool match = true;
        for (int j = 0; j < target_bytes; j++) {
            if (hash[j] != target[j]) {
                match = false;
                break;
            }
        }

        if (match) {
            *found_nonce = nonce;
            for (int j = 0; j < 16; j++)
                found_hash[j] = hash[j];
            return;
        }
    }
}

int hex_to_byte(const char* hex, unsigned char* out, int max_bytes) {
    int len = strlen(hex) / 2;
    if (len > max_bytes) len = max_bytes;
    for (int i = 0; i < len; i++) {
        unsigned int b;
        sscanf(hex + 2 * i, "%2x", &b);
        out[i] = (unsigned char)b;
    }
    return len;
}

int main(int argc, char* argv[]) {
    if (argc < 3) {
        printf("Uso: %s <cadena> <prefijo_hex>\n", argv[0]);
        printf("Ej: %s \"hola\" \"00\"\n", argv[0]);
        return 1;
    }

    unsigned char target_bytes[8];
    int tlen = hex_to_byte(argv[2], target_bytes, 8);

    size_t base_len = strlen(argv[1]);
    unsigned char *d_base, *d_target, *d_hash;
    unsigned long long *d_found, h_found = ~0ULL;
    unsigned char h_hash[16];

    unsigned char* h_base = (unsigned char*)argv[1];

    cudaMalloc(&d_base, base_len + 1);
    cudaMalloc(&d_target, tlen);
    cudaMalloc(&d_hash, 16);
    cudaMalloc(&d_found, sizeof(unsigned long long));

    cudaMemcpy(d_base, h_base, base_len + 1, cudaMemcpyHostToDevice);
    cudaMemcpy(d_target, target_bytes, tlen, cudaMemcpyHostToDevice);
    cudaMemcpy(d_found, &h_found, sizeof(unsigned long long), cudaMemcpyHostToDevice);

    int blocks = 256;
    int threads = 256;

    printf("Buscando nonce para MD5(\"%s\" + nonce) que empiece con \"%s\"...\n",
           argv[1], argv[2]);
    printf("Lanzando %d threads en %d bloques\n", threads, blocks);

    brute_force_kernel<<<blocks, threads>>>(
        d_base, base_len, d_target, tlen, d_found, d_hash
    );
    cudaDeviceSynchronize();

    cudaMemcpy(&h_found, d_found, sizeof(unsigned long long), cudaMemcpyDeviceToHost);
    if (h_found != ~0ULL) {
        cudaMemcpy(h_hash, d_hash, 16, cudaMemcpyDeviceToHost);
        printf("Encontrado! nonce = %llu\n", h_found);
        printf("MD5(\"%s%llu\") = ", argv[1], h_found);
        for (int i = 0; i < 16; i++)
            printf("%02x", h_hash[i]);
        printf("\n");
    } else {
        printf("No se encontró nonce\n");
    }

    cudaFree(d_base);
    cudaFree(d_target);
    cudaFree(d_hash);
    cudaFree(d_found);
    return 0;
}
