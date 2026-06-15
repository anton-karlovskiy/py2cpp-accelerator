import time

def calculate_pi(iterations, multiplier, offset):
    result = 1.0
    for i in range(1, iterations + 1):
        denominator = i * multiplier - offset
        result -= (1 / denominator)
        denominator = i * multiplier + offset
        result += (1 / denominator)
    return result

start_time = time.time()
result = calculate_pi(200_000_000, 4, 1) * 4
end_time = time.time()

print(f"Result: {result:.12f}")
print(f"Execution Time: {(end_time - start_time):.6f} seconds")
