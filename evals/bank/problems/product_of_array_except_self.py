NUMBER = 238
SLUG = "product-of-array-except-self"
TITLE = "Product of Array Except Self"
DIFFICULTY = "Medium"

CANONICAL = '''\
class Solution:
    def productExceptSelf(self, nums):
        n = len(nums)
        out = [1] * n
        prefix = 1
        for i in range(n):
            out[i] = prefix
            prefix *= nums[i]
        suffix = 1
        for i in range(n - 1, -1, -1):
            out[i] *= suffix
            suffix *= nums[i]
        return out
'''

TESTS = [
    (([1, 2, 3, 4],), [24, 12, 8, 6], "general"),
    (([-1, 1, 0, -3, 3],), [0, 0, 9, 0, 0], "edge"),
    (([2, 3],), [3, 2], "general"),
    (([0, 0],), [0, 0], "edge"),
]

SCALE = ([1] * 3000,)  # all ones: keeps arithmetic O(1) so timing measures the loop shape

MUTANTS = [
    {
        "id": "division",
        "mutation": "unsafe-arithmetic",
        "intended": "edge-case",
        "code": '''\
class Solution:
    def productExceptSelf(self, nums):
        total = 1
        for x in nums:
            total *= x
        return [total // x for x in nums]
''',
    },
    {
        "id": "brute-force",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": '''\
class Solution:
    def productExceptSelf(self, nums):
        out = []
        for i in range(len(nums)):
            product = 1
            for j in range(len(nums)):
                if i != j:
                    product *= nums[j]
            out.append(product)
        return out
''',
    },
]
