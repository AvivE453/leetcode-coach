from evals.bank.controls import PRELUDE, external_code

NUMBER = 1834
SLUG = "single-threaded-cpu"
TITLE = "Single-Threaded CPU"
DIFFICULTY = "Medium"
SPLIT = "test"
METHOD = "getOrder"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (([[1, 2], [2, 4], [3, 2], [4, 1]],), [0, 2, 3, 1], "general"),
    (([[7, 10], [7, 12], [7, 5], [7, 4], [7, 2]],), [4, 3, 2, 0, 1], "general"),
    (([[5, 2], [1, 4]],), [1, 0], "general"),
    (([[1, 3], [10, 1], [2, 2]],), [0, 2, 1], "general"),
    (([[1, 2], [1, 2], [1, 1]],), [2, 0, 1], "general"),
    (([[1, 1]],), [0], "edge"),
]

SCALE = ([[1, (i * 37) % 1000 + 1] for i in range(2000)],)
SPACE_SCALE = ([[i // 2 + 1, (i * 37) % 1000 + 1] for i in range(2000)],)


def reference(tasks):
    waiting = set(range(len(tasks)))
    time, order = 0, []
    while waiting:
        ready = [i for i in waiting if tasks[i][0] <= time]
        if not ready:
            time = min(tasks[i][0] for i in waiting)
            continue
        task = min(ready, key=lambda i: (tasks[i][1], i))
        waiting.remove(task)
        order.append(task)
        time += tasks[task][1]
    return order


def valid(tasks):
    # 1 <= tasks.length <= 10^5, tasks[i] = [enqueueTime, processingTime], both in [1, 10^9]
    return 1 <= len(tasks) <= 10**5 and all(
        len(task) == 2 and 1 <= task[0] <= 10**9 and 1 <= task[1] <= 10**9 for task in tasks)


def generate(rng):
    return ([[rng.randint(1, 10), rng.randint(1, 5)] for _ in range(rng.randint(1, 8))],)


MUTANTS = [
    {
        "id": "ties-go-to-the-later-task",
        "mutation": "wrong-operator",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def getOrder(self, tasks: List[List[int]]) -> List[int]:
        tasks = sorted([(t[0], t[1], i) for i, t in enumerate(tasks)])
        result, heap = [], []
        cur_task_index = 0
        cur_time = tasks[0][0]

        while len(result) < len(tasks):
            while (cur_task_index < len(tasks)) and (tasks[cur_task_index][0] <= cur_time):
                heapq.heappush(heap, (tasks[cur_task_index][1], -tasks[cur_task_index][2]))
                cur_task_index += 1
            if heap:
                time_difference, original_index = heapq.heappop(heap)
                cur_time += time_difference
                result.append(-original_index)
            elif cur_task_index < len(tasks):
                cur_time = tasks[cur_task_index][0]

        return result
''',
    },
    {
        "id": "enqueues-in-input-order",
        "mutation": "missing-precondition",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def getOrder(self, tasks: List[List[int]]) -> List[int]:
        tasks = [(t[0], t[1], i) for i, t in enumerate(tasks)]
        result, heap = [], []
        cur_task_index = 0
        cur_time = tasks[0][0]

        while len(result) < len(tasks):
            while (cur_task_index < len(tasks)) and (tasks[cur_task_index][0] <= cur_time):
                heapq.heappush(heap, (tasks[cur_task_index][1], tasks[cur_task_index][2]))
                cur_task_index += 1
            if heap:
                time_difference, original_index = heapq.heappop(heap)
                cur_time += time_difference
                result.append(original_index)
            elif cur_task_index < len(tasks):
                cur_time = tasks[cur_task_index][0]

        return result
''',
    },
    {
        "id": "scans-for-the-next-task",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def getOrder(self, tasks: List[List[int]]) -> List[int]:
        done = [False] * len(tasks)
        time = 0
        order = []
        while len(order) < len(tasks):
            best = -1
            for i, (enqueue, process) in enumerate(tasks):
                if not done[i] and enqueue <= time and (best == -1 or process < tasks[best][1]):
                    best = i
            if best == -1:
                time = min(tasks[i][0] for i in range(len(tasks)) if not done[i])
                continue
            done[best] = True
            order.append(best)
            time += tasks[best][1]
        return order
''',
    },
]

CLEAN_VARIANTS = []
