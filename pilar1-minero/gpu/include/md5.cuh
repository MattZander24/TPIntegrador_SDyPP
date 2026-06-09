#include <cstdint>

#define MD5_F(x, y, z) ((x & y) | (~x & z))
#define MD5_G(x, y, z) ((x & z) | (y & ~z))
#define MD5_H(x, y, z) (x ^ y ^ z)
#define MD5_I(x, y, z) (y ^ (x | ~z))

#define MD5_LEFT_ROTATE(x, s) ((x << s) | (x >> (32 - s)))

__constant__ uint32_t md5_K[64] = {
    0xd76aa478, 0xe8c7b756, 0x242070db, 0xc1bdceee,
    0xf57c0faf, 0x4787c62a, 0xa8304613, 0xfd469501,
    0x698098d8, 0x8b44f7af, 0xffff5bb1, 0x895cd7be,
    0x6b901122, 0xfd987193, 0xa679438e, 0x49b40821,
    0xf61e2562, 0xc040b340, 0x265e5a51, 0xe9b6c7aa,
    0xd62f105d, 0x02441453, 0xd8a1e681, 0xe7d3fbc8,
    0x21e1cde6, 0xc33707d6, 0xf4d50d87, 0x455a14ed,
    0xa9e3e905, 0xfcefa3f8, 0x676f02d9, 0x8d2a4c8a,
    0xfffa3942, 0x8771f681, 0x6d9d6122, 0xfde5380c,
    0xa4beea44, 0x4bdecfa9, 0xf6bb4b60, 0xbebfbc70,
    0x289b7ec6, 0xeaa127fa, 0xd4ef3085, 0x04881d05,
    0xd9d4d039, 0xe6db99e5, 0x1fa27cf8, 0xc4ac5665,
    0xf4292244, 0x432aff97, 0xab9423a7, 0xfc93a039,
    0x655b59c3, 0x8f0ccc92, 0xffeff47d, 0x85845dd1,
    0x6fa87e4f, 0xfe2ce6e0, 0xa3014314, 0x4e0811a1,
    0xf7537e82, 0xbd3af235, 0x2ad7d2bb, 0xeb86d391
};

__constant__ uint32_t md5_S[64] = {
    7, 12, 17, 22,  7, 12, 17, 22,  7, 12, 17, 22,  7, 12, 17, 22,
    5,  9, 14, 20,  5,  9, 14, 20,  5,  9, 14, 20,  5,  9, 14, 20,
    4, 11, 16, 23,  4, 11, 16, 23,  4, 11, 16, 23,  4, 11, 16, 23,
    6, 10, 15, 21,  6, 10, 15, 21,  6, 10, 15, 21,  6, 10, 15, 21
};

__device__ void md5_transform(uint32_t state[4], const uint32_t block[16]) {
    uint32_t a = state[0];
    uint32_t b = state[1];
    uint32_t c = state[2];
    uint32_t d = state[3];

    for (int i = 0; i < 64; i++) {
        uint32_t F, g;
        if (i < 16) {
            F = MD5_F(b, c, d);
            g = i;
        } else if (i < 32) {
            F = MD5_G(b, c, d);
            g = (5 * i + 1) % 16;
        } else if (i < 48) {
            F = MD5_H(b, c, d);
            g = (3 * i + 5) % 16;
        } else {
            F = MD5_I(b, c, d);
            g = (7 * i) % 16;
        }

        uint32_t temp = a + F + md5_K[i] + block[g];
        a = d;
        d = c;
        c = b;
        b = b + MD5_LEFT_ROTATE(temp, md5_S[i]);
    }

    state[0] += a;
    state[1] += b;
    state[2] += c;
    state[3] += d;
}

__device__ void md5_hash(const unsigned char* input, size_t len, unsigned char output[16]) {
    uint32_t state[4] = {
        0x67452301, 0xefcdab89, 0x98badcfe, 0x10325476
    };

    size_t padded_len = ((len + 8) / 64 + 1) * 64;
    uint64_t bit_len = (uint64_t)len * 8;

    for (size_t offset = 0; offset < padded_len; offset += 64) {
        uint32_t block[16] = {0};
        unsigned char* b = (unsigned char*)block;

        for (int i = 0; i < 64; i++) {
            size_t pos = offset + i;
            if (pos < len) {
                b[i] = input[pos];
            } else if (pos == len) {
                b[i] = 0x80;
            } else if (pos >= padded_len - 8) {
                b[i] = (bit_len >> ((pos - (padded_len - 8)) * 8)) & 0xff;
            }
        }

        md5_transform(state, block);
    }

    for (int i = 0; i < 4; i++) {
        output[i * 4 + 0] =  state[i]        & 0xff;
        output[i * 4 + 1] = (state[i] >> 8)  & 0xff;
        output[i * 4 + 2] = (state[i] >> 16) & 0xff;
        output[i * 4 + 3] = (state[i] >> 24) & 0xff;
    }
}
