# 217. Contains Duplicate
# https://leetcode.com/problems/contains-duplicate/

# --- 2026-09-01 · clean
class Solution:
    def containsDuplicate(self, nums: List[int]) -> bool:
        
        hash_map = {}

        for num in nums:
            if num in hash_map:
                return True
            else:
                hash_map[num] = ""
        
        return False
