#include <cstdio>

__global__ void hello_kernel() {
    printf("Hello from GPU thread %d (block %d)\n",
           threadIdx.x, blockIdx.x);
}

int main() {
    printf("Hello from CPU\n");
    hello_kernel<<<2, 4>>>();
    cudaDeviceSynchronize();
    return 0;
}
