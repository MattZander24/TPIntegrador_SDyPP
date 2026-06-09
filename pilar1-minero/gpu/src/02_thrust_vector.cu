#include <thrust/host_vector.h>
#include <thrust/device_vector.h>
#include <iostream>

int main() {
    thrust::host_vector<int> h_vec(4);
    h_vec[0] = 10;
    h_vec[1] = 20;
    h_vec[2] = 30;
    h_vec[3] = 40;

    thrust::device_vector<int> d_vec = h_vec;

    thrust::host_vector<int> result = d_vec;

    std::cout << "Thrust device_vector contents:\n";
    for (size_t i = 0; i < result.size(); i++)
        std::cout << "  result[" << i << "] = " << result[i] << "\n";

    return 0;
}
