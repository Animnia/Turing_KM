"""知识融合与清洗模块 - 合并多源数据、实体对齐、去重、质量检查"""

import json
import logging
import re
from collections import defaultdict

from src.config import DATA_PROCESSED_DIR
from src.ontology import ENTITY_TYPES, RELATION_TYPES

logger = logging.getLogger(__name__)


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
    """对齐 Wikidata 和 DeepSeek 抽取的实体"""
    logger.info("=== 开始实体对齐 ===")

    # Wikidata 数据作为基准
    merged = {}
    for eid, entity in wikidata_entities.items():
        merged[eid] = {**entity}

    # 构建 Wikidata 实体名称索引
    name_index = _build_name_index(merged)

    # 逐个处理 DeepSeek 抽取的实体
    id_mapping = {}  # old_id → new_id (对齐映射)
    new_count = 0
    aligned_count = 0

    for eid, entity in extracted_entities.items():
        name = entity.get("name", "")
        norm_name = _normalize_name(name)

        # 尝试匹配
        matched_id = None

        # 精确匹配
        if norm_name in name_index:
            matched_id = name_index[norm_name][0]

        # 子串匹配
        if not matched_id:
            for existing_name, existing_ids in name_index.items():
                if norm_name and existing_name and (
                    norm_name in existing_name or existing_name in norm_name
                ):
                    matched_id = existing_ids[0]
                    break

        if matched_id:
            # 对齐成功 - 合并属性（不覆盖已有的非空属性）
            id_mapping[eid] = matched_id
            existing = merged[matched_id]
            for k, v in entity.items():
                if k == "id":
                    continue
                if v and (k not in existing or not existing.get(k)):
                    existing[k] = v
            aligned_count += 1
        else:
            # 无匹配 - 作为新实体加入
            entity_type = entity.get("type", "Concept")
            new_id = _generate_entity_id(entity_type, name)
            # 避免 ID 冲突
            if new_id in merged:
                new_id = f"{new_id}_{new_count}"
            entity["id"] = new_id
            merged[new_id] = entity
            id_mapping[eid] = new_id
            new_count += 1
            # 更新名称索引
            if norm_name:
                name_index.setdefault(norm_name, []).append(new_id)

    logger.info("实体对齐完成: 对齐 %d 个, 新增 %d 个, 合并后共 %d 个实体",
                aligned_count, new_count, len(merged))

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
