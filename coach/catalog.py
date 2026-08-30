import json

import httpx

from coach.config import CATALOG_PATH

GRAPHQL_URL = "https://leetcode.com/graphql/"
PAGE_SIZE = 100

QUERY = """
query problemsetQuestionList($categorySlug: String, $limit: Int, $skip: Int, $filters: QuestionListFilterInput) {
  problemsetQuestionList: questionList(
    categorySlug: $categorySlug
    limit: $limit
    skip: $skip
    filters: $filters
  ) {
    total: totalNum
    questions: data {
      difficulty
      frontendQuestionId: questionFrontendId
      paidOnly: isPaidOnly
      title
      titleSlug
      topicTags { slug }
    }
  }
}
"""

HEADERS = {
    "Content-Type": "application/json",
    "Referer": "https://leetcode.com/problemset/",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
}


def fetch() -> list[dict]:
    problems = []
    skip = 0
    with httpx.Client(headers=HEADERS, timeout=30, http2=True) as client:
        while True:
            payload = {
                "query": QUERY,
                "variables": {
                    "categorySlug": "all-code-essentials",
                    "skip": skip,
                    "limit": PAGE_SIZE,
                    "filters": {},
                },
            }
            response = client.post(GRAPHQL_URL, json=payload)
            response.raise_for_status()
            page = response.json()["data"]["problemsetQuestionList"]
            for q in page["questions"]:
                if not q["frontendQuestionId"].isdigit():
                    continue
                problems.append(
                    {
                        "number": int(q["frontendQuestionId"]),
                        "slug": q["titleSlug"],
                        "title": q["title"],
                        "difficulty": q["difficulty"],
                        "paid_only": q["paidOnly"],
                        "tags": [t["slug"] for t in q["topicTags"]],
                    }
                )
            skip += PAGE_SIZE
            if skip >= page["total"]:
                return problems


def save(problems: list[dict]) -> None:
    CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CATALOG_PATH.write_text(json.dumps(problems, indent=1))


def load() -> list[dict]:
    return json.loads(CATALOG_PATH.read_text())
