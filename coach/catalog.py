import html
import json
import re

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

CONTENT_QUERY = """
query questionContent($titleSlug: String!) {
  question(titleSlug: $titleSlug) {
    content
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


_SUPERSCRIPT = re.compile(r"<sup>(.*?)</sup>", re.IGNORECASE | re.DOTALL)
_LIST_ITEM = re.compile(r"<li>", re.IGNORECASE)
_BLOCK_CLOSE = re.compile(r"</(p|div|ul|ol|pre|li)>|<br\s*/?>", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")


def _clean_html(raw: str) -> str:
    """LeetCode's `content` is a fragment of problem-statement HTML - flatten it to
    plain text good enough for an LLM prompt, not a faithful re-rendering."""
    text = _SUPERSCRIPT.sub(r"^\1", raw)
    text = _LIST_ITEM.sub("\n- ", text)
    text = _BLOCK_CLOSE.sub("\n", text)
    text = _TAG.sub("", text)
    text = html.unescape(text).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def fetch_content(slug: str) -> str | None:
    """One problem's statement (with its constraints), cleaned to plain text.

    A single request per problem, not part of the bulk `fetch()` - callers fetch this
    lazily, only for a problem actually under review. Paid-only or missing questions
    return None rather than raising, so a review can fall back to no constraints text.
    """
    with httpx.Client(headers=HEADERS, timeout=30, http2=True) as client:
        response = client.post(
            GRAPHQL_URL,
            json={"query": CONTENT_QUERY, "variables": {"titleSlug": slug}},
        )
        response.raise_for_status()
        question = response.json()["data"]["question"]
    if not question or not question["content"]:
        return None
    return _clean_html(question["content"])


def save(problems: list[dict]) -> None:
    CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CATALOG_PATH.write_text(json.dumps(problems, indent=1))


def load() -> list[dict]:
    return json.loads(CATALOG_PATH.read_text())
