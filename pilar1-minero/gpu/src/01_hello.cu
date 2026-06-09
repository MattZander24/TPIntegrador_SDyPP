#include <cstdio>

#define CUDA_CHECK(ans) { gpuAssert((ans), __FILE__, __LINE__); }
inline void gpuAssert(cudaError_t code, const char* file, int line) {
    if (code != cudaSuccess) {
        fprintf(stderr, "CUDA error: %s %s %d\n",
                cudaGetErrorString(code), file, line);
        exit(code);
    }
}

__global__ void hello_kernel(int* out) {
    int tid = blockIdx.x * blockDim.x + threadIdx.x;
    out[tid] = tid;
}

int main() {
    int N = 8;
    int* d_out;
    int h_out[8] = {0};

    CUDA_CHECK(cudaMalloc(&d_out, N * sizeof(int)));
    hello_kernel<<<2, 4>>>(d_out);
    CUDA_CHECK(cudaDeviceSynchronize());
    CUDA_CHECK(cudaMemcpy(h_out, d_out, N * sizeof(int), cudaMemcpyDeviceToHost));
    CUDA_CHECK(cudaFree(d_out));

    printf("Hello from CPU\n");
    for (int i = 0; i < N; i++)
        printf("Hello from GPU thread %d\n", h_out[i]);

    return 0;
}
