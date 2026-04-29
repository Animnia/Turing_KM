"""知识融合与清洗模块 - 合并多源数据、实体对齐、去重、质量检查"""

import json
import logging
import re
from collections import defaultdict
from difflib import SequenceMatcher

from src.config import DATA_PROCESSED_DIR
from src.ontology import ENTITY_TYPES, RELATION_TYPES

logger = logging.getLogger(__name__)

# 实体名称模糊匹配阈值（同类型内）
_FUZZY_NAME_THRESHOLD = 0.88

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
_BLACKLIST_RE = re.compile("|".join(_NAME_BLACKLIST_PATTERNS), re.IGNORECASE)
# (规范化名称, 类型) → 丢弃
_TYPED_NAME_BLACKLIST = {
    ("atheism", "Institution"),
    ("turing", "Concept"),
}


def _is_blacklisted(name: str, etype: str) -> bool:
    """统一的实体黑名单判断，供 Wikidata 与 LLM 抽取共用。"""
    if not name:
        return True
    if _BLACKLIST_RE.search(name):
        return True
    norm = name.strip().lower()
    if (norm, etype) in _TYPED_NAME_BLACKLIST:
        return True
    if len(re.sub(r"[\W_]+", "", name)) < 2:
        return True
    return False


# ============================================================
# 实体名称归一化
# ============================================================


def _normalize_name(name: str) -> str:
    """归一化实体名称，用于模糊匹配"""
    name = name.lower().strip()
    # 去除括号内容
    name = re.sub(r"\s*\(.*?\)\s*", " ", name)
    # 去除多余空格
    name = re.sub(r"\s+", " ", name).strip()
    # 去除标点
    name = re.sub(r"[.,;:'\"-]", "", name)
    return name


def _normalize_date(date_str: str) -> str:
    """将日期标准化为 ISO 8601 格式"""
    if not date_str:
        return ""
    # 处理 Wikidata 日期格式 (可能带时区)
    date_str = date_str.strip()
    # 取前10位 (YYYY-MM-DD)
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})", date_str)
    if match:
        return match.group(0)
    # 只有年份
    match = re.match(r"(\d{4})", date_str)
    if match:
        return match.group(1)
    return date_str


def _generate_entity_id(entity_type: str, name: str) -> str:
    """生成统一的实体 ID"""
    prefix_map = {
        "Person": "person",
        "Institution": "inst",
        "Publication": "pub",
        "Concept": "concept",
        "Event": "event",
        "Place": "place",
        "Award": "award",
        "Field": "field",
    }
    prefix = prefix_map.get(entity_type, entity_type.lower())
    slug = _normalize_name(name).replace(" ", "_")[:60]
    return f"{prefix}_{slug}"


# ============================================================
# 实体对齐
# ============================================================


def _build_name_index(entities: dict) -> dict:
    """构建名称到实体 ID 的索引"""
    index = {}
    for eid, entity in entities.items():
        name = entity.get("name", "")
        norm = _normalize_name(name)
        if norm:
            if norm not in index:
                index[norm] = []
            index[norm].append(eid)
        # 也索引中文名
        name_zh = entity.get("name_zh", "")
        if name_zh:
            index.setdefault(name_zh, []).append(eid)
    return index


def align_entities(wikidata_entities: dict, extracted_entities: dict) -> dict:
    """对齐 Wikidata 和 DeepSeek 抽取的实体。

    优先级（高 → 低）:
      1) wikidata_id (QID) 完全相同 → 直接合并
      2) 归一化名称完全一致 + 实体类型相同 → 合并
      3) 归一化名称模糊相似度 ≥ 阈值 + 实体类型相同 → 合并
      4) 否则作为新实体加入
    """
    logger.info("=== 开始实体对齐 ===")

    # Wikidata 数据作为基准
    merged = {}
    for eid, entity in wikidata_entities.items():
        merged[eid] = {**entity}

    # 索引: QID → eid
    qid_index = {}
    # 索引: (norm_name, type) → eid
    typed_name_index = {}
    # 索引: type → list[(norm_name, eid)] 用于模糊匹配
    type_to_names = defaultdict(list)

    for eid, entity in merged.items():
        qid = entity.get("wikidata_id", "")
        etype = entity.get("type", "")
        norm = _normalize_name(entity.get("name", ""))
        if qid:
            qid_index[qid] = eid
        if norm and etype:
            typed_name_index[(norm, etype)] = eid
            type_to_names[etype].append((norm, eid))
            # 中文名也建索引
            norm_zh = _normalize_name(entity.get("name_zh", ""))
            if norm_zh:
                typed_name_index[(norm_zh, etype)] = eid

    id_mapping = {}
    new_count = 0
    aligned_qid = 0
    aligned_exact = 0
    aligned_fuzzy = 0
    aligned_id = 0

    for eid, entity in extracted_entities.items():
        name = entity.get("name", "")
        norm_name = _normalize_name(name)
        etype = entity.get("type", "")
        qid = entity.get("wikidata_id", "")

        matched_id = None
        match_via = None

        # 0) 实体 ID 已存在于基准（多由 prompt 中固定的规范 ID 触发）
        if eid in merged:
            matched_id = eid
            match_via = "id"

        # 1) QID 精确匹配
        if not matched_id and qid and qid in qid_index:
            matched_id = qid_index[qid]
            match_via = "qid"

        # 2) (归一化名称, 类型) 精确匹配
        if not matched_id and norm_name and etype:
            matched_id = typed_name_index.get((norm_name, etype))
            if matched_id:
                match_via = "exact"

        # 3) 同类型内的模糊相似度匹配
        if not matched_id and norm_name and etype and etype in type_to_names:
            best_id = None
            best_ratio = 0.0
            for cand_norm, cand_id in type_to_names[etype]:
                if not cand_norm:
                    continue
                ratio = SequenceMatcher(None, norm_name, cand_norm).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_id = cand_id
            if best_id and best_ratio >= _FUZZY_NAME_THRESHOLD:
                matched_id = best_id
                match_via = f"fuzzy({best_ratio:.2f})"

        if matched_id:
            id_mapping[eid] = matched_id
            existing = merged[matched_id]
            for k, v in entity.items():
                if k == "id":
                    continue
                if v and (k not in existing or not existing.get(k)):
                    existing[k] = v
            if match_via == "qid":
                aligned_qid += 1
            elif match_via == "exact":
                aligned_exact += 1
            elif match_via == "id":
                aligned_id += 1
            else:
                aligned_fuzzy += 1
        else:
            entity_type = entity.get("type", "Concept")
            new_id = _generate_entity_id(entity_type, name)
            if new_id in merged:
                new_id = f"{new_id}_{new_count}"
            entity["id"] = new_id
            merged[new_id] = entity
            id_mapping[eid] = new_id
            new_count += 1
            # 更新索引以便后续抽取实体相互对齐
            if norm_name and entity_type:
                typed_name_index[(norm_name, entity_type)] = new_id
                type_to_names[entity_type].append((norm_name, new_id))
            new_qid = entity.get("wikidata_id", "")
            if new_qid:
                qid_index[new_qid] = new_id

    logger.info(
        "实体对齐完成: ID 对齐 %d, QID 对齐 %d, 精确名 %d, 模糊名 %d, 新增 %d, 合并后共 %d 个实体",
        aligned_id, aligned_qid, aligned_exact, aligned_fuzzy, new_count, len(merged),
    )

    return merged, id_mapping


# ============================================================
# 关系融合与清洗
# ============================================================


def merge_relations(
    wikidata_relations: list,
    extracted_relations: list,
    id_mapping: dict,
    entities: dict,
) -> list:
    """合并和去重关系"""
    logger.info("=== 开始关系融合 ===")

    all_relations = []
    seen = set()

    def _add_relation(rel: dict):
        """添加去重后的关系"""
        source = rel.get("source", "")
        target = rel.get("target", "")
        rel_type = rel.get("relation", "")

        # 通过 id_mapping 更新引用
        source = id_mapping.get(source, source)
        target = id_mapping.get(target, target)

        if not source or not target or not rel_type:
            return
        if source not in entities or target not in entities:
            return
        if source == target:
            return

        # 验证关系类型是否合法
        if rel_type not in RELATION_TYPES:
            return

        key = (source, rel_type, target)
        if key not in seen:
            seen.add(key)
            cleaned_rel = {
                "source": source,
                "relation": rel_type,
                "target": target,
            }
            props = rel.get("properties", {})
            if props:
                cleaned_rel["properties"] = props
            all_relations.append(cleaned_rel)

    # Wikidata 关系优先
    for rel in wikidata_relations:
        _add_relation(rel)

    # 然后是 DeepSeek 抽取的关系
    for rel in extracted_relations:
        _add_relation(rel)

    logger.info("关系融合完成: 共 %d 条唯一关系", len(all_relations))
    return all_relations


# ============================================================
# 数据清洗
# ============================================================


def _flatten_for_neo4j(entity: dict) -> dict:
    """将实体属性展平/规范化为 Neo4j 支持的原语类型。

    - 嵌套 dict 'properties' 里的字段提升到顶层（不覆盖已有非空字段）
    - 其余非原语类型转为字符串 / 丢弃
    """
    nested = entity.pop("properties", None)
    if isinstance(nested, dict):
        for k, v in nested.items():
            if k in entity and entity.get(k):
                continue
            entity[k] = v
    out = {}
    for k, v in entity.items():
        if v is None:
            continue
        if isinstance(v, (str, int, float, bool)):
            out[k] = v
        elif isinstance(v, list):
            # 仅保留原语数组
            prim = [x for x in v if isinstance(x, (str, int, float, bool))]
            if prim:
                out[k] = prim
        elif isinstance(v, dict):
            # 二次嵌套：序列化为字符串
            try:
                out[k] = json.dumps(v, ensure_ascii=False)
            except Exception:
                pass
        else:
            out[k] = str(v)
    return out


def clean_entities(entities: dict) -> dict:
    """清洗实体数据"""
    logger.info("=== 开始实体清洗 ===")

    cleaned = {}
    for eid, entity in entities.items():
        # 标准化日期
        for date_field in ["birth_date", "death_date", "start_date", "end_date"]:
            if date_field in entity:
                entity[date_field] = _normalize_date(entity[date_field])

        # 确保有 name
        if not entity.get("name"):
            continue

        # 确保有 type
        if entity.get("type") not in ENTITY_TYPES:
            # 尝试根据 id 前缀推断
            prefix = eid.split("_")[0] if "_" in eid else ""
            type_map = {
                "person": "Person", "inst": "Institution", "pub": "Publication",
                "concept": "Concept", "event": "Event", "place": "Place",
                "award": "Award", "field": "Field",
            }
            entity["type"] = type_map.get(prefix, "Concept")

        # 确保 id 一致
        entity["id"] = eid

        # 展平嵌套属性 + 仅保留 Neo4j 支持的原语类型
        entity = _flatten_for_neo4j(entity)

        # 去除空属性
        cleaned[eid] = {k: v for k, v in entity.items() if v}

    logger.info("实体清洗完成: %d → %d 个实体", len(entities), len(cleaned))
    return cleaned


# ============================================================
# 质量检查
# ============================================================


def quality_check(entities: dict, relations: list) -> dict:
    """对融合后的知识图谱进行质量检查"""
    logger.info("=== 开始质量检查 ===")

    stats = {
        "total_entities": len(entities),
        "total_relations": len(relations),
        "entity_types": defaultdict(int),
        "relation_types": defaultdict(int),
        "orphan_entities": 0,
    }

    # 统计实体类型分布
    for entity in entities.values():
        stats["entity_types"][entity.get("type", "Unknown")] += 1

    # 统计关系类型分布
    for rel in relations:
        stats["relation_types"][rel.get("relation", "Unknown")] += 1

    # 检查孤立节点
    connected = set()
    for rel in relations:
        connected.add(rel["source"])
        connected.add(rel["target"])

    orphans = set(entities.keys()) - connected
    stats["orphan_entities"] = len(orphans)
    stats["orphan_list"] = list(orphans)[:20]

    # 转换 defaultdict 为 dict（方便 JSON 序列化）
    stats["entity_types"] = dict(stats["entity_types"])
    stats["relation_types"] = dict(stats["relation_types"])

    logger.info("质量检查结果:")
    logger.info("  实体总数: %d", stats["total_entities"])
    logger.info("  关系总数: %d", stats["total_relations"])
    logger.info("  实体类型分布: %s", stats["entity_types"])
    logger.info("  关系类型分布: %s", stats["relation_types"])
    logger.info("  孤立节点: %d", stats["orphan_entities"])

    return stats


# ============================================================
# 主流程
# ============================================================


def fuse_all() -> dict:
    """执行完整的知识融合流程"""
    logger.info("========== 知识融合流程开始 ==========")

    # 加载两个数据源
    wikidata_path = DATA_PROCESSED_DIR / "wikidata_triples.json"
    extracted_path = DATA_PROCESSED_DIR / "extracted_triples.json"

    with open(wikidata_path, "r", encoding="utf-8") as f:
        wikidata_data = json.load(f)

    with open(extracted_path, "r", encoding="utf-8") as f:
        extracted_data = json.load(f)

    wikidata_entities = wikidata_data.get("entities", {})
    wikidata_relations = wikidata_data.get("relations", [])
    extracted_entities = extracted_data.get("entities", {})
    extracted_relations = extracted_data.get("relations", [])

    # 对两个数据源应用统一的黑名单过滤（防止 wikipedia 元数据/atheism 等脏条进入图谱）
    def _filter_blacklist(entities: dict, relations: list, source_name: str):
        bad_ids = {
            eid for eid, e in entities.items()
            if _is_blacklisted(e.get("name", ""), e.get("type", ""))
        }
        if bad_ids:
            logger.info("[%s] 黑名单过滤: 删除 %d 个实体", source_name, len(bad_ids))
        clean_entities = {k: v for k, v in entities.items() if k not in bad_ids}
        clean_relations = [
            r for r in relations
            if r.get("source") not in bad_ids and r.get("target") not in bad_ids
        ]
        return clean_entities, clean_relations

    wikidata_entities, wikidata_relations = _filter_blacklist(
        wikidata_entities, wikidata_relations, "Wikidata"
    )
    extracted_entities, extracted_relations = _filter_blacklist(
        extracted_entities, extracted_relations, "LLM"
    )

    # Step 1: 实体对齐
    merged_entities, id_mapping = align_entities(wikidata_entities, extracted_entities)

    # Step 2: 关系融合
    merged_relations = merge_relations(
        wikidata_relations, extracted_relations, id_mapping, merged_entities
    )

    # Step 3: 数据清洗
    cleaned_entities = clean_entities(merged_entities)

    # 清洗后重新过滤关系（确保两端实体都存在）
    valid_relations = [
        r for r in merged_relations
        if r["source"] in cleaned_entities and r["target"] in cleaned_entities
    ]

    # Step 4: 质量检查
    stats = quality_check(cleaned_entities, valid_relations)

    # 保存最终结果
    result = {
        "entities": cleaned_entities,
        "relations": valid_relations,
        "stats": stats,
    }

    output_path = DATA_PROCESSED_DIR / "final_triples.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    logger.info("最终数据已保存至 %s", output_path)
    logger.info("========== 知识融合流程完成 ==========")

    return result
