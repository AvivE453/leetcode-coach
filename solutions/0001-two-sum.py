# 1. Two Sum
# https://leetcode.com/problems/two-sum/

# --- 2026-09-01 · clean
class Solution(object):
    def twoSum(self, nums, target):
        """
        :type nums: List[int]
        :type target: int
        :rtype: List[int]
        """
        d = {}
        for i,num in enumerate(nums) :
            if (target - num) in d:
                return [i,d[target - num]]
            else:
                d[num]=i

# --- 2026-09-01 · clean
class Solution(object):
    def twoSum(self, nums, target):
        """
        :type nums: List[int]
        :type target: int
        :rtype: List[int]
        """
        d = {}


        
        for i,num in enumerate(nums) :
            if (target - num) in d:
                return [i,d[target - num]]
            else:
                d[num]=i
