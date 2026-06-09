#include <cstdio>
#include <cstring>
#include <cstdlib>
#include "md5.cuh"

__device__ int ull_to_str(unsigned long long n, unsigned char* out) {
    if (n == 0) { out[0] = '0'; return 1; }
    unsigned char temp[20];
    int len = 0;
    while (n > 0) { temp[len++] = '0' + (n % 10); n /= 10; }
    for (int i = 0; i < len; i++) out[i] = temp[len - 1 - i];
    return len;
}

__device__ int hex_digit(unsigned char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return 0;
}

__device__ bool check_prefix(const unsigned char* hash, const char* prefix, int hex_len) {
    for (int i = 0; i < hex_len; i++) {
        int hash_nibble = i % 2 ? (hash[i/2] & 0xf) : ((hash[i/2] >> 4) & 0xf);
        if (hash_nibble != hex_digit(prefix[i]))
            return false;
    }
    return true;
}

__global__ void brute_force_kernel(
    const unsigned char* base, size_t base_len,
    const char* prefix, int hex_len,
    unsigned long long* found_nonce, unsigned char* found_hash
) {
    unsigned long long tid = blockIdx.x * blockDim.x + threadIdx.x;
    unsigned long long total = gridDim.x * blockDim.x;
    unsigned char buf[256], hash[16];

    for (int i = 0; i < (int)base_len; i++) buf[i] = base[i];

    for (unsigned long long nonce = tid; ; nonce += total) {
        if (*found_nonce != ~0ULL) return;
        int nlen = ull_to_str(nonce, buf + base_len);
        md5_hash(buf, base_len + nlen, hash);
        if (check_prefix(hash, prefix, hex_len)) {
            *found_nonce = nonce;
            for (int j = 0; j < 16; j++) found_hash[j] = hash[j];
            return;
        }
    }
}

int main(int argc, char* argv[]) {
    if (argc < 3) {
        printf("Uso: %s <cadena> <prefijo_hex>\n", argv[0]);
        printf("Ej: %s \"hola\" \"00\"\n", argv[0]);
        return 1;
    }

    int hex_len = strlen(argv[2]);
    size_t base_len = strlen(argv[1]);
    unsigned char *d_base, *d_hash, h_hash[16];
    char *d_prefix;
    unsigned long long *d_found, h_found = ~0ULL;

    cudaMalloc(&d_base, base_len + 1);
    cudaMalloc(&d_prefix, hex_len + 1);
    cudaMalloc(&d_hash, 16);
    cudaMalloc(&d_found, sizeof(unsigned long long));

    cudaMemcpy(d_base, argv[1], base_len + 1, cudaMemcpyHostToDevice);
    cudaMemcpy(d_prefix, argv[2], hex_len + 1, cudaMemcpyHostToDevice);
    cudaMemcpy(d_found, &h_found, sizeof(unsigned long long), cudaMemcpyHostToDevice);

    int blocks = 256, threads = 256;
    printf("Buscando MD5(\"%s\"+nonce) empiece con \"%s\" (%d hex chars)...\n",
           argv[1], argv[2], hex_len);

    brute_force_kernel<<<blocks, threads>>>(
        d_base, base_len, d_prefix, hex_len, d_found, d_hash);
    cudaDeviceSynchronize();

    cudaMemcpy(&h_found, d_found, sizeof(unsigned long long), cudaMemcpyDeviceToHost);
    if (h_found != ~0ULL) {
        cudaMemcpy(h_hash, d_hash, 16, cudaMemcpyDeviceToHost);
        printf("Nonce = %llu\nMD5 = ", h_found);
        for (int i = 0; i < 16; i++) printf("%02x", h_hash[i]);
        printf("\n");
    } else {
        printf("No encontrado\n");
    }

    cudaFree(d_base); cudaFree(d_prefix);
    cudaFree(d_hash); cudaFree(d_found);
    return 0;
}
