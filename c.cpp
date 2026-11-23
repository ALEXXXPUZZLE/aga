#include <stdio.h>
#include <math.h>

int main() {
    float a, b, c;
    float p, S;
    float h_a, h_b, h_c;

    a = 5.0;
    b = 6.0;
    c = 7.0;

    p = (a + b + c) / 2.0;
    
    S = sqrt(p * (p - a) * (p - b) * (p - c));

    h_a = (2.0 / a) * S;
    h_b = (2.0 / b) * S;
    h_c = (2.0 / c) * S;

    printf("ha = %.2f\n", h_a);
    printf("hb = %.2f\n", h_b);
    printf("hc = %.2f\n", h_c);

    return 0;
}
