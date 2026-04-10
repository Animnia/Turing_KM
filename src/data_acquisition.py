"""数据采集模块 - 从 Wikidata SPARQL 和 Wikipedia API 获取原始数据"""

import json
import logging
import time

import requests

from src.config import (
    DATA_RAW_DIR,
    TURING_WIKIDATA_QID,
    TURING_WIKIPEDIA_TITLE,
    WIKIDATA_SPARQL_ENDPOINT,
    WIKIPEDIA_API_URL,
)

logger = logging.getLogger(__name__)


# ============================================================
# Wikidata SPARQL 数据采集
# ============================================================


def _sparql_query(query: str) -> list[dict]:
    """执行 SPARQL 查询并返回结果"""
    headers = {"Accept": "application/sparql-results+json", "User-Agent": "TuringKG/1.0"}
    resp = requests.get(
        WIKIDATA_SPARQL_ENDPOINT,
        params={"query": query, "format": "json"},
        headers=headers,
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("results", {}).get("bindings", [])


def fetch_turing_basic_info() -> dict:
    """获取图灵基本信息"""
    query = f"""
    SELECT ?property ?propertyLabel ?value ?valueLabel WHERE {{
      wd:{TURING_WIKIDATA_QID} ?prop ?value .
      ?property wikibase:directClaim ?prop .
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,zh". }}
    }}
    LIMIT 500
    """
    results = _sparql_query(query)
    logger.info("获取图灵基本属性: %d 条", len(results))
    return {"type": "basic_info", "qid": TURING_WIKIDATA_QID, "results": results}


def fetch_turing_related_people() -> list[dict]:
    """获取与图灵相关的人物"""
    query = f"""
    SELECT DISTINCT ?person ?personLabel ?personDescription ?relation ?relationLabel
           ?birthDate ?deathDate WHERE {{
      {{
        wd:{TURING_WIKIDATA_QID} ?prop ?person .
        ?relation wikibase:directClaim ?prop .
        ?person wdt:P31 wd:Q5 .
      }} UNION {{
        ?person ?prop wd:{TURING_WIKIDATA_QID} .
        ?relation wikibase:directClaim ?prop .
        ?person wdt:P31 wd:Q5 .
      }}
      OPTIONAL {{ ?person wdt:P569 ?birthDate . }}
      OPTIONAL {{ ?person wdt:P570 ?deathDate . }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,zh". }}
    }}
    LIMIT 200
    """
    results = _sparql_query(query)
    logger.info("获取关联人物: %d 条", len(results))
    return results


def fetch_turing_related_institutions() -> list[dict]:
    """获取与图灵相关的机构"""
    query = f"""
    SELECT DISTINCT ?inst ?instLabel ?instDescription ?relation ?relationLabel
           ?country ?countryLabel WHERE {{
      wd:{TURING_WIKIDATA_QID} ?prop ?inst .
      ?relation wikibase:directClaim ?prop .
      ?inst wdt:P31/wdt:P279* ?type .
      VALUES ?type {{ wd:Q43229 wd:Q3918 wd:Q875538 wd:Q31855 wd:Q7075 }}
      OPTIONAL {{ ?inst wdt:P17 ?country . }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,zh". }}
    }}
    LIMIT 100
    """
    results = _sparql_query(query)
    logger.info("获取关联机构: %d 条", len(results))
    return results


def fetch_turing_works() -> list[dict]:
    """获取图灵的著作/出版物"""
    query = f"""
    SELECT DISTINCT ?work ?workLabel ?workDescription ?date WHERE {{
      ?work wdt:P50 wd:{TURING_WIKIDATA_QID} .
      OPTIONAL {{ ?work wdt:P577 ?date . }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,zh". }}
    }}
    LIMIT 100
    """
    results = _sparql_query(query)
    logger.info("获取著作: %d 条", len(results))
    return results


def fetch_turing_concepts() -> list[dict]:
    """获取以图灵命名或与图灵强相关的概念"""
    query = f"""
    SELECT DISTINCT ?concept ?conceptLabel ?conceptDescription ?field ?fieldLabel WHERE {{
      {{
        wd:{TURING_WIKIDATA_QID} wdt:P800 ?concept .
      }} UNION {{
        ?concept wdt:P138 wd:{TURING_WIKIDATA_QID} .
      }} UNION {{
        wd:{TURING_WIKIDATA_QID} wdt:P106 ?concept .
      }}
      OPTIONAL {{ ?concept wdt:P425 ?field . }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,zh". }}
    }}
    LIMIT 100
    """
    results = _sparql_query(query)
    logger.info("获取关联概念: %d 条", len(results))
    return results


def fetch_turing_awards() -> list[dict]:
    """获取图灵获得的奖项和荣誉"""
    query = f"""
    SELECT DISTINCT ?award ?awardLabel ?awardDescription ?date WHERE {{
      wd:{TURING_WIKIDATA_QID} wdt:P166 ?award .
      OPTIONAL {{ ?award wdt:P585 ?date . }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,zh". }}
    }}
    LIMIT 50
    """
    results = _sparql_query(query)
    logger.info("获取奖项: %d 条", len(results))
    return results


def fetch_turing_education() -> list[dict]:
    """获取图灵的教育经历"""
    query = f"""
    SELECT ?school ?schoolLabel ?schoolDescription ?degree ?degreeLabel
           ?startDate ?endDate WHERE {{
      wd:{TURING_WIKIDATA_QID} wdt:P69 ?school .
      OPTIONAL {{ ?school wdt:P512 ?degree . }}
      OPTIONAL {{ ?school wdt:P580 ?startDate . }}
      OPTIONAL {{ ?school wdt:P582 ?endDate . }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,zh". }}
    }}
    """
    results = _sparql_query(query)
    logger.info("获取教育经历: %d 条", len(results))
    return results


def fetch_turing_fields() -> list[dict]:
    """获取图灵的研究领域"""
    query = f"""
    SELECT ?field ?fieldLabel ?fieldDescription WHERE {{
      wd:{TURING_WIKIDATA_QID} wdt:P101 ?field .
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,zh". }}
    }}
    """
    results = _sparql_query(query)
    logger.info("获取研究领域: %d 条", len(results))
    return results


def fetch_wikidata() -> dict:
    """执行所有 Wikidata 查询并保存"""
    logger.info("=== 开始 Wikidata 数据采集 ===")

    data = {
        "qid": TURING_WIKIDATA_QID,
        "basic_info": fetch_turing_basic_info(),
        "related_people": fetch_turing_related_people(),
        "institutions": fetch_turing_related_institutions(),
        "works": fetch_turing_works(),
        "concepts": fetch_turing_concepts(),
        "awards": fetch_turing_awards(),
        "education": fetch_turing_education(),
        "fields": fetch_turing_fields(),
    }

    output_path = DATA_RAW_DIR / "wikidata_turing.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info("Wikidata 数据已保存至 %s", output_path)
    return data


# ============================================================
# Wikipedia 文本采集
# ============================================================


def fetch_wikipedia_sections() -> dict:
    """获取 Wikipedia 文章全文，按章节分段"""
    logger.info("=== 开始 Wikipedia 文本采集 ===")

    headers = {"User-Agent": "TuringKG/1.0 (Academic project; Python/requests)"}

    # 获取章节列表
    params = {
        "action": "parse",
        "page": TURING_WIKIPEDIA_TITLE,
        "prop": "sections",
        "format": "json",
    }
    resp = requests.get(WIKIPEDIA_API_URL, params=params, headers=headers, timeout=30)
    resp.raise_for_status()
    sections_data = resp.json().get("parse", {}).get("sections", [])

    # 获取纯文本内容
    params_text = {
        "action": "query",
        "titles": TURING_WIKIPEDIA_TITLE,
        "prop": "extracts",
        "explaintext": True,
        "format": "json",
    }
    resp_text = requests.get(WIKIPEDIA_API_URL, params=params_text, headers=headers, timeout=30)
    resp_text.raise_for_status()
    pages = resp_text.json().get("query", {}).get("pages", {})
    full_text = ""
    for page in pages.values():
        full_text = page.get("extract", "")

    # 按章节分割文本
    sections = []
    section_titles = [s.get("line", "") for s in sections_data if s.get("level") == "2"]

    if section_titles:
        parts = [full_text]
        for title in section_titles:
            new_parts = []
            for part in parts:
                split = part.split(f"\n\n\n== {title} ==\n", 1)
                if len(split) == 2:
                    new_parts.append(split[0])
                    new_parts.append(split[1])
                else:
                    # 尝试其他分割格式
                    split2 = part.split(f"\n== {title} ==\n", 1)
                    if len(split2) == 2:
                        new_parts.append(split2[0])
                        new_parts.append(split2[1])
                    else:
                        new_parts.append(part)
            parts = new_parts

        # 第一部分是导言
        if parts:
            sections.append({"title": "Introduction", "text": parts[0].strip()})

        # 后续部分按章节标题配对
        for i, title in enumerate(section_titles):
            idx = i + 1
            if idx < len(parts):
                sections.append({"title": title, "text": parts[idx].strip()})
    else:
        sections.append({"title": "Full Article", "text": full_text})

    # 如果分割效果不佳，回退到按 == 标题 == 分割
    if len(sections) <= 1 and full_text:
        import re

        section_pattern = re.compile(r"\n==\s*(.+?)\s*==\n")
        parts = section_pattern.split(full_text)
        sections = [{"title": "Introduction", "text": parts[0].strip()}]
        for i in range(1, len(parts), 2):
            if i + 1 < len(parts):
                sections.append({"title": parts[i].strip(), "text": parts[i + 1].strip()})

    data = {
        "title": TURING_WIKIPEDIA_TITLE,
        "sections": sections,
        "section_count": len(sections),
        "total_chars": len(full_text),
    }

    output_path = DATA_RAW_DIR / "wikipedia_turing.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info("Wikipedia 数据已保存至 %s (%d 个章节, %d 字符)", output_path, len(sections), len(full_text))
    return data


def fetch_all() -> dict:
    """执行所有数据采集任务"""
    wikidata = fetch_wikidata()
    time.sleep(1)  # 避免请求过快
    wikipedia = fetch_wikipedia_sections()
    return {"wikidata": wikidata, "wikipedia": wikipedia}
