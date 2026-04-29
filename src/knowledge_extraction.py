"""知识抽取模块 - 从结构化数据和非结构化文本中提取实体和关系"""

import json
import logging
import re
import time

from openai import OpenAI

from src.config import (
    DATA_PROCESSED_DIR,
    DATA_RAW_DIR,
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
)
from src.ontology import ENTITY_TYPES, RELATION_TYPES, get_ontology_prompt_description

logger = logging.getLogger(__name__)


# ============================================================
# Wikidata 结构化数据解析
# ============================================================

# Wikidata 属性 ID → 关系类型映射
WIKIDATA_PROPERTY_MAP = {
    "P19": ("BORN_IN", "Place"),       # place of birth
    "P20": ("DIED_IN", "Place"),       # place of death
    "P69": ("EDUCATED_AT", "Institution"),  # educated at
    "P108": ("WORKED_AT", "Institution"),   # employer
    "P184": ("ADVISED_BY", "Person"),       # doctoral advisor
    "P185": ("ADVISED_BY", "Person"),       # doctoral student (reverse)
    "P50": ("AUTHORED", "Publication"),     # author
    "P800": ("KNOWN_FOR", "Concept"),       # notable work
    "P166": ("RECEIVED", "Award"),          # award received
    "P101": ("FIELD_OF_WORK", "Field"),     # field of work
    "P802": ("ADVISED", "Person"),          # student
    "P1066": ("ADVISED_BY", "Person"),      # student of
    "P22": ("RELATED_TO", "Person"),        # father
    "P25": ("RELATED_TO", "Person"),        # mother
    "P3373": ("RELATED_TO", "Person"),      # sibling
    "P26": ("RELATED_TO", "Person"),        # spouse
    "P451": ("RELATED_TO", "Person"),       # partner
    "P937": ("WORKED_AT", "Place"),         # work location
    "P106": ("FIELD_OF_WORK", "Field"),     # occupation (映射到领域)
    "P463": ("PART_OF", "Institution"),     # member of
    "P138": ("KNOWN_FOR", "Concept"),       # named after
}

# 关系属性说明
FAMILY_RELATION_MAP = {
    "P22": "father",
    "P25": "mother",
    "P3373": "sibling",
    "P26": "spouse",
    "P451": "partner",
}


def _extract_qid(uri: str) -> str:
    """从 Wikidata URI 提取 QID"""
    if uri and "/" in uri:
        return uri.rsplit("/", 1)[-1]
    return uri


def _extract_pid(uri: str) -> str:
    """从 Wikidata property URI 提取 PID"""
    if uri and "/" in uri:
        return uri.rsplit("/", 1)[-1]
    return uri


def parse_wikidata_triples() -> dict:
    """将 Wikidata 原始数据解析为统一的实体-关系三元组"""
    logger.info("=== 开始解析 Wikidata 结构化数据 ===")

    raw_path = DATA_RAW_DIR / "wikidata_turing.json"
    with open(raw_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    entities = {}  # id → entity dict
    relations = []  # list of relation dicts

    # 添加图灵本人
    turing_id = "person_alan_turing"
    entities[turing_id] = {
        "id": turing_id,
        "type": "Person",
        "name": "Alan Turing",
        "name_zh": "艾伦·图灵",
        "birth_date": "1912-06-23",
        "death_date": "1954-06-07",
        "nationality": "British",
        "description": "British mathematician, computer scientist, logician, cryptanalyst, philosopher, and theoretical biologist",
        "occupation": "mathematician, computer scientist, cryptanalyst",
        "wikidata_id": "Q7251",
    }

    # --- 解析关联人物 ---
    for item in raw_data.get("related_people", []):
        person_uri = item.get("person", {}).get("value", "")
        qid = _extract_qid(person_uri)
        if not qid or not qid.startswith("Q"):
            continue

        name = item.get("personLabel", {}).get("value", qid)
        if name == qid:  # 没有获取到标签
            continue

        pid = _extract_qid(item.get("relation", {}).get("value", ""))
        eid = f"person_{name.lower().replace(' ', '_').replace('.', '')}"

        if eid not in entities:
            entities[eid] = {
                "id": eid,
                "type": "Person",
                "name": name,
                "description": item.get("personDescription", {}).get("value", ""),
                "birth_date": item.get("birthDate", {}).get("value", "")[:10] if item.get("birthDate") else "",
                "death_date": item.get("deathDate", {}).get("value", "")[:10] if item.get("deathDate") else "",
                "wikidata_id": qid,
            }

        # 确定关系类型
        if pid in WIKIDATA_PROPERTY_MAP:
            rel_type, _ = WIKIDATA_PROPERTY_MAP[pid]
            rel = {"source": turing_id, "relation": rel_type, "target": eid}
            if pid in FAMILY_RELATION_MAP:
                rel["properties"] = {"relationship": FAMILY_RELATION_MAP[pid]}
            relations.append(rel)

    # --- 解析机构 ---
    for item in raw_data.get("institutions", []):
        inst_uri = item.get("inst", {}).get("value", "")
        qid = _extract_qid(inst_uri)
        if not qid or not qid.startswith("Q"):
            continue

        name = item.get("instLabel", {}).get("value", qid)
        if name == qid:
            continue

        pid = _extract_qid(item.get("relation", {}).get("value", ""))
        eid = f"inst_{name.lower().replace(' ', '_').replace('.', '')}"

        if eid not in entities:
            entities[eid] = {
                "id": eid,
                "type": "Institution",
                "name": name,
                "description": item.get("instDescription", {}).get("value", ""),
                "location": item.get("countryLabel", {}).get("value", ""),
                "wikidata_id": qid,
            }

        if pid in WIKIDATA_PROPERTY_MAP:
            rel_type, _ = WIKIDATA_PROPERTY_MAP[pid]
        else:
            rel_type = "WORKED_AT"
        relations.append({"source": turing_id, "relation": rel_type, "target": eid})

    # --- 解析教育经历 ---
    for item in raw_data.get("education", []):
        school_uri = item.get("school", {}).get("value", "")
        qid = _extract_qid(school_uri)
        if not qid or not qid.startswith("Q"):
            continue

        name = item.get("schoolLabel", {}).get("value", qid)
        if name == qid:
            continue

        eid = f"inst_{name.lower().replace(' ', '_').replace('.', '')}"
        if eid not in entities:
            entities[eid] = {
                "id": eid,
                "type": "Institution",
                "name": name,
                "description": item.get("schoolDescription", {}).get("value", ""),
                "institution_type": "university",
                "wikidata_id": qid,
            }

        relations.append({"source": turing_id, "relation": "EDUCATED_AT", "target": eid})

    # --- 解析著作 ---
    for item in raw_data.get("works", []):
        work_uri = item.get("work", {}).get("value", "")
        qid = _extract_qid(work_uri)
        if not qid or not qid.startswith("Q"):
            continue

        name = item.get("workLabel", {}).get("value", qid)
        if name == qid:
            continue

        eid = f"pub_{name.lower().replace(' ', '_').replace('.', '')[:60]}"
        date_val = item.get("date", {}).get("value", "")

        if eid not in entities:
            entities[eid] = {
                "id": eid,
                "type": "Publication",
                "name": name,
                "description": item.get("workDescription", {}).get("value", ""),
                "year": date_val[:4] if date_val else "",
                "wikidata_id": qid,
            }

        relations.append({"source": turing_id, "relation": "AUTHORED", "target": eid})

    # --- 解析概念（notable work / named after） ---
    for item in raw_data.get("concepts", []):
        concept_uri = item.get("concept", {}).get("value", "")
        qid = _extract_qid(concept_uri)
        if not qid or not qid.startswith("Q"):
            continue

        name = item.get("conceptLabel", {}).get("value", qid)
        if name == qid:
            continue

        eid = f"concept_{name.lower().replace(' ', '_').replace('.', '')[:60]}"
        if eid not in entities:
            entities[eid] = {
                "id": eid,
                "type": "Concept",
                "name": name,
                "description": item.get("conceptDescription", {}).get("value", ""),
                "wikidata_id": qid,
            }

        relations.append({"source": turing_id, "relation": "KNOWN_FOR", "target": eid})

    # --- 解析奖项 ---
    for item in raw_data.get("awards", []):
        award_uri = item.get("award", {}).get("value", "")
        qid = _extract_qid(award_uri)
        if not qid or not qid.startswith("Q"):
            continue

        name = item.get("awardLabel", {}).get("value", qid)
        if name == qid:
            continue

        eid = f"award_{name.lower().replace(' ', '_').replace('.', '')[:60]}"
        if eid not in entities:
            entities[eid] = {
                "id": eid,
                "type": "Award",
                "name": name,
                "description": item.get("awardDescription", {}).get("value", ""),
                "wikidata_id": qid,
            }

        relations.append({"source": turing_id, "relation": "RECEIVED", "target": eid})

    # --- 解析研究领域 ---
    for item in raw_data.get("fields", []):
        field_uri = item.get("field", {}).get("value", "")
        qid = _extract_qid(field_uri)
        if not qid or not qid.startswith("Q"):
            continue

        name = item.get("fieldLabel", {}).get("value", qid)
        if name == qid:
            continue

        eid = f"field_{name.lower().replace(' ', '_').replace('.', '')[:60]}"
        if eid not in entities:
            entities[eid] = {
                "id": eid,
                "type": "Field",
                "name": name,
                "description": item.get("fieldDescription", {}).get("value", ""),
                "wikidata_id": qid,
            }

        relations.append({"source": turing_id, "relation": "FIELD_OF_WORK", "target": eid})

    result = {"entities": entities, "relations": relations}

    output_path = DATA_PROCESSED_DIR / "wikidata_triples.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    logger.info("Wikidata 解析完成: %d 个实体, %d 条关系", len(entities), len(relations))
    return result


# ============================================================
# DeepSeek API 非结构化文本抽取
# ============================================================


def _build_extraction_prompt(section_title: str, section_text: str) -> str:
    """构建知识抽取的 prompt"""
    ontology_desc = get_ontology_prompt_description()

    return f"""你是一个知识图谱构建专家。请从以下关于 Alan Turing（艾伦·图灵）的文本中提取实体和关系。

{ontology_desc}

## 要求:
1. 提取所有提及的实体，确定其类型
2. 提取实体间的关系，确定关系类型
3. 为每个实体提供尽可能完整的属性
4. 返回严格的 JSON 格式，不要输出其他内容
5. 实体 id 用英文小写+下划线格式，如 "person_alan_turing"
6. 日期使用 ISO 8601 格式 (YYYY-MM-DD)
7. Alan Turing 本人的 id 固定为 "person_alan_turing"

## 输出 JSON 格式:
```json
{{
  "entities": [
    {{
      "id": "entity_id",
      "type": "EntityType",
      "name": "English Name",
      "name_zh": "中文名(如有)",
      "properties": {{}}
    }}
  ],
  "relations": [
    {{
      "source": "source_entity_id",
      "relation": "RELATION_TYPE",
      "target": "target_entity_id",
      "properties": {{}}
    }}
  ]
}}
```

## 文本章节: {section_title}

{section_text}

请提取上述文本中的所有实体和关系，以 JSON 格式输出:"""


def _repair_truncated_json(content: str) -> dict:
    """尝试修复被截断的 JSON 输出"""
    import re

    # 尝试找到最后一个完整的实体或关系
    # 首先尝试只解析 entities 部分
    result = {"entities": [], "relations": []}

    # 尝试修复：添加缺失的闭合括号
    for suffix in [']}', '"]}', '"}]}', '"}],"relations":[]}', '"}]}']:
        try:
            fixed = content.rstrip() + suffix
            parsed = json.loads(fixed)
            return parsed
        except json.JSONDecodeError:
            continue

    # 尝试提取 entities 数组中已完成的部分
    entities_match = re.search(r'"entities"\s*:\s*\[', content)
    if entities_match:
        start = entities_match.end()
        # 找到最后一个完整的 } (实体结束)
        brace_depth = 0
        last_complete = start
        for i in range(start, len(content)):
            if content[i] == '{':
                brace_depth += 1
            elif content[i] == '}':
                brace_depth -= 1
                if brace_depth == 0:
                    last_complete = i + 1

        if last_complete > start:
            try:
                entities_str = '[' + content[start:last_complete] + ']'
                result["entities"] = json.loads(entities_str)
            except json.JSONDecodeError:
                pass

    # 尝试提取 relations 数组
    relations_match = re.search(r'"relations"\s*:\s*\[', content)
    if relations_match:
        start = relations_match.end()
        brace_depth = 0
        last_complete = start
        for i in range(start, len(content)):
            if content[i] == '{':
                brace_depth += 1
            elif content[i] == '}':
                brace_depth -= 1
                if brace_depth == 0:
                    last_complete = i + 1

        if last_complete > start:
            try:
                relations_str = '[' + content[start:last_complete] + ']'
                result["relations"] = json.loads(relations_str)
            except json.JSONDecodeError:
                pass

    return result


# ============================================================
# Schema 校验与脏数据过滤
# ============================================================

# 名称黑名单（不区分大小写的子串）：明显是维基元数据/管理页面
_NAME_BLACKLIST_PATTERNS = [
    r"\bwikipedia\b",
    r"wikiproject",
    r"wiki99",
    r"^category[: ]",
    r"^template[: ]",
    r"^portal[: ]",
    r"^help[: ]",
    r"^talk[: ]",
    r"^user[: ]",
    r"^file[: ]",
    r"main page",
    r"disambiguation",
]

# 类型相关的精细黑名单：(规范化名称, 类型) → 丢弃
_TYPED_NAME_BLACKLIST = {
    ("atheism", "Institution"),
    ("turing", "Concept"),  # 纯名为 "Turing" 的概念多为编程语言/无关
}

_BLACKLIST_RE = re.compile("|".join(_NAME_BLACKLIST_PATTERNS), re.IGNORECASE)


def _validate_extracted(extracted: dict) -> dict:
    """对 LLM 抽取结果做 schema 校验和黑名单过滤。

    - 实体类型必须在 ENTITY_TYPES 内
    - 实体名称不能命中黑名单
    - 关系类型必须在 RELATION_TYPES 内
    - 丢弃引用了被删除实体的关系
    """
    raw_entities = extracted.get("entities", {}) or {}
    raw_relations = extracted.get("relations", []) or []

    # 兼容 dict 或 list
    if isinstance(raw_entities, list):
        ent_iter = raw_entities
    else:
        ent_iter = raw_entities.values()

    valid_entities = {}
    dropped_entities = 0
    dropped_blacklist = 0
    dropped_type = 0

    for entity in ent_iter:
        eid = entity.get("id", "")
        etype = entity.get("type", "")
        name = (entity.get("name") or "").strip()

        if not eid or not name:
            dropped_entities += 1
            continue

        if etype not in ENTITY_TYPES:
            dropped_type += 1
            continue

        # 名称黑名单
        norm = name.strip().lower()
        if _BLACKLIST_RE.search(name):
            dropped_blacklist += 1
            continue
        if (norm, etype) in _TYPED_NAME_BLACKLIST:
            dropped_blacklist += 1
            continue
        # 名称过短或纯标点
        if len(re.sub(r"[\W_]+", "", name)) < 2:
            dropped_blacklist += 1
            continue

        valid_entities[eid] = entity

    valid_ids = set(valid_entities.keys())
    valid_relations = []
    dropped_rel_type = 0
    dropped_rel_ref = 0

    for rel in raw_relations:
        rtype = rel.get("relation", "")
        src = rel.get("source", "")
        tgt = rel.get("target", "")
        if rtype not in RELATION_TYPES:
            dropped_rel_type += 1
            continue
        if src not in valid_ids or tgt not in valid_ids:
            dropped_rel_ref += 1
            continue
        if src == tgt:
            continue
        valid_relations.append(rel)

    logger.info(
        "Schema 校验: 实体 %d→%d (类型不合法 %d, 黑名单 %d, 缺字段 %d); "
        "关系 %d→%d (类型不合法 %d, 引用缺失 %d)",
        len(raw_entities), len(valid_entities),
        dropped_type, dropped_blacklist, dropped_entities,
        len(raw_relations), len(valid_relations),
        dropped_rel_type, dropped_rel_ref,
    )

    return {"entities": valid_entities, "relations": valid_relations}


def extract_from_text_llm(sections: list[dict]) -> dict:
    """使用 DeepSeek API 从 Wikipedia 文本中抽取知识"""
    logger.info("=== 开始 DeepSeek API 知识抽取 ===")

    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)

    all_entities = {}
    all_relations = []

    for i, section in enumerate(sections):
        title = section.get("title", "")
        text = section.get("text", "")

        if not text or len(text) < 50:
            logger.info("跳过章节 '%s' (文本过短: %d 字符)", title, len(text))
            continue

        # 截断过长的文本（分为较小的段落以确保输出不被截断）
        if len(text) > 4000:
            text = text[:4000]

        logger.info("[%d/%d] 正在抽取章节: %s (%d 字符)", i + 1, len(sections), title, len(text))

        prompt = _build_extraction_prompt(title, text)

        try:
            response = client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=[
                    {"role": "system", "content": "你是一个专业的知识图谱构建助手，擅长从文本中抽取结构化的实体和关系。请严格按照要求的JSON格式输出。注意控制输出长度，每个章节最多抽取20个最重要的实体。description字段请控制在50字以内。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=8192,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content

            # 尝试修复被截断的 JSON
            try:
                result = json.loads(content)
            except json.JSONDecodeError:
                result = _repair_truncated_json(content)

            # 合并实体
            for entity in result.get("entities", []):
                eid = entity.get("id", "")
                if eid:
                    if eid not in all_entities:
                        all_entities[eid] = entity
                    else:
                        # 合并属性（新属性不覆盖已有的非空属性）
                        for k, v in entity.items():
                            if v and (k not in all_entities[eid] or not all_entities[eid][k]):
                                all_entities[eid][k] = v

            # 合并关系
            for rel in result.get("relations", []):
                if rel.get("source") and rel.get("relation") and rel.get("target"):
                    all_relations.append(rel)

            logger.info("  → 抽取到 %d 个实体, %d 条关系",
                        len(result.get("entities", [])), len(result.get("relations", [])))

        except json.JSONDecodeError as e:
            logger.warning("  → 章节 '%s' JSON 解析失败: %s", title, e)
        except Exception as e:
            logger.warning("  → 章节 '%s' 抽取失败: %s", title, e)

        # API 调用间隔
        time.sleep(1)

    result = {"entities": all_entities, "relations": all_relations}

    # Schema 校验与脏数据过滤
    result = _validate_extracted(result)

    output_path = DATA_PROCESSED_DIR / "extracted_triples.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    logger.info("DeepSeek 抽取完成: %d 个实体, %d 条关系", len(all_entities), len(all_relations))
    return result


def extract_all() -> dict:
    """执行所有知识抽取任务"""
    # Step 1: 解析 Wikidata 结构化数据
    wikidata_triples = parse_wikidata_triples()

    # Step 2: 使用 DeepSeek 抽取 Wikipedia 文本
    wiki_path = DATA_RAW_DIR / "wikipedia_turing.json"
    with open(wiki_path, "r", encoding="utf-8") as f:
        wiki_data = json.load(f)

    extracted_triples = extract_from_text_llm(wiki_data.get("sections", []))

    return {"wikidata": wikidata_triples, "extracted": extracted_triples}
