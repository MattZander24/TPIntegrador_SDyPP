#include <cstdio>
#include <cstring>
#include "md5.cuh"

__global__ void md5_kernel(const unsigned char* input, size_t len, unsigned char* output) {
    md5_hash(input, len, output);
}

int main(int argc, char* argv[]) {
    if (argc < 2) {
        printf("Uso: %s <string>\n", argv[0]);
        return 1;
    }

    size_t len = strlen(argv[1]);

    unsigned char* d_input;
    unsigned char* d_output;
    unsigned char h_output[16];

    cudaMalloc(&d_input, len + 1);
    cudaMalloc(&d_output, 16);
    cudaMemcpy(d_input, argv[1], len + 1, cudaMemcpyHostToDevice);

    md5_kernel<<<1, 1>>>(d_input, len, d_output);
    cudaDeviceSynchronize();
    cudaMemcpy(h_output, d_output, 16, cudaMemcpyDeviceToHost);

    printf("MD5(\"%s\") = ", argv[1]);
    for (int i = 0; i < 16; i++)
        printf("%02x", h_output[i]);
    printf("\n");

    cudaFree(d_input);
    cudaFree(d_output);
    return 0;
}
