"""本体/模式定义 - 定义知识图谱的实体类型、关系类型和属性"""

# ============================================================
# 实体类型定义 (Node Labels)
# ============================================================

ENTITY_TYPES = {
    "Person": {
        "description": "人物实体",
        "properties": {
            "id": {"type": "string", "required": True, "description": "唯一标识符"},
            "name": {"type": "string", "required": True, "description": "英文名"},
            "name_zh": {"type": "string", "required": False, "description": "中文名"},
            "birth_date": {"type": "string", "required": False, "description": "出生日期 (ISO 8601)"},
            "death_date": {"type": "string", "required": False, "description": "去世日期 (ISO 8601)"},
            "nationality": {"type": "string", "required": False, "description": "国籍"},
            "description": {"type": "string", "required": False, "description": "简要描述"},
            "occupation": {"type": "string", "required": False, "description": "职业"},
            "wikidata_id": {"type": "string", "required": False, "description": "Wikidata QID"},
        },
    },
    "Institution": {
        "description": "机构/组织实体",
        "properties": {
            "id": {"type": "string", "required": True},
            "name": {"type": "string", "required": True},
            "name_zh": {"type": "string", "required": False},
            "institution_type": {"type": "string", "required": False, "description": "机构类型 (大学/政府/军事/研究所等)"},
            "location": {"type": "string", "required": False, "description": "所在地"},
            "founded_date": {"type": "string", "required": False},
            "description": {"type": "string", "required": False},
            "wikidata_id": {"type": "string", "required": False},
        },
    },
    "Publication": {
        "description": "论文/著作/出版物",
        "properties": {
            "id": {"type": "string", "required": True},
            "name": {"type": "string", "required": True, "description": "标题"},
            "name_zh": {"type": "string", "required": False},
            "year": {"type": "string", "required": False, "description": "发表年份"},
            "publication_type": {"type": "string", "required": False, "description": "论文/书籍/报告"},
            "abstract": {"type": "string", "required": False},
            "description": {"type": "string", "required": False},
            "wikidata_id": {"type": "string", "required": False},
        },
    },
    "Concept": {
        "description": "学术概念/理论/方法",
        "properties": {
            "id": {"type": "string", "required": True},
            "name": {"type": "string", "required": True},
            "name_zh": {"type": "string", "required": False},
            "field": {"type": "string", "required": False, "description": "所属领域"},
            "description": {"type": "string", "required": False},
            "wikidata_id": {"type": "string", "required": False},
        },
    },
    "Event": {
        "description": "历史事件",
        "properties": {
            "id": {"type": "string", "required": True},
            "name": {"type": "string", "required": True},
            "name_zh": {"type": "string", "required": False},
            "start_date": {"type": "string", "required": False},
            "end_date": {"type": "string", "required": False},
            "location": {"type": "string", "required": False},
            "description": {"type": "string", "required": False},
            "wikidata_id": {"type": "string", "required": False},
        },
    },
    "Place": {
        "description": "地点/地理位置",
        "properties": {
            "id": {"type": "string", "required": True},
            "name": {"type": "string", "required": True},
            "name_zh": {"type": "string", "required": False},
            "country": {"type": "string", "required": False},
            "place_type": {"type": "string", "required": False, "description": "城市/国家/建筑等"},
            "description": {"type": "string", "required": False},
            "wikidata_id": {"type": "string", "required": False},
        },
    },
    "Award": {
        "description": "荣誉/奖项",
        "properties": {
            "id": {"type": "string", "required": True},
            "name": {"type": "string", "required": True},
            "name_zh": {"type": "string", "required": False},
            "year": {"type": "string", "required": False, "description": "颁发年份"},
            "awarded_by": {"type": "string", "required": False},
            "description": {"type": "string", "required": False},
            "wikidata_id": {"type": "string", "required": False},
        },
    },
    "Field": {
        "description": "学科领域",
        "properties": {
            "id": {"type": "string", "required": True},
            "name": {"type": "string", "required": True},
            "name_zh": {"type": "string", "required": False},
            "description": {"type": "string", "required": False},
            "wikidata_id": {"type": "string", "required": False},
        },
    },
}

# ============================================================
# 关系类型定义 (Relationship Types)
# ============================================================

RELATION_TYPES = {
    "BORN_IN": {
        "description": "出生于",
        "source_types": ["Person"],
        "target_types": ["Place"],
    },
    "DIED_IN": {
        "description": "去世于",
        "source_types": ["Person"],
        "target_types": ["Place"],
    },
    "EDUCATED_AT": {
        "description": "受教育于",
        "source_types": ["Person"],
        "target_types": ["Institution"],
        "properties": {"degree": "学位", "year_start": "入学年份", "year_end": "毕业年份"},
    },
    "WORKED_AT": {
        "description": "工作于",
        "source_types": ["Person"],
        "target_types": ["Institution"],
        "properties": {"role": "职位", "year_start": "开始年份", "year_end": "结束年份"},
    },
    "ADVISED_BY": {
        "description": "师从/导师为",
        "source_types": ["Person"],
        "target_types": ["Person"],
    },
    "COLLABORATED_WITH": {
        "description": "合作关系",
        "source_types": ["Person"],
        "target_types": ["Person"],
        "symmetric": True,
    },
    "AUTHORED": {
        "description": "撰写/发表",
        "source_types": ["Person"],
        "target_types": ["Publication"],
    },
    "CONTRIBUTED_TO": {
        "description": "贡献于（概念/领域）",
        "source_types": ["Person"],
        "target_types": ["Concept", "Field"],
    },
    "RECEIVED": {
        "description": "获得（奖项/荣誉）",
        "source_types": ["Person"],
        "target_types": ["Award"],
        "properties": {"year": "获奖年份"},
    },
    "PARTICIPATED_IN": {
        "description": "参与事件",
        "source_types": ["Person", "Institution"],
        "target_types": ["Event"],
        "properties": {"role": "角色"},
    },
    "LOCATED_IN": {
        "description": "位于",
        "source_types": ["Institution", "Place", "Event"],
        "target_types": ["Place"],
    },
    "RELATED_TO": {
        "description": "亲属/家庭关系",
        "source_types": ["Person"],
        "target_types": ["Person"],
        "properties": {"relationship": "关系类型（父/母/兄弟/未婚妻等）"},
    },
    "INFLUENCED": {
        "description": "影响了",
        "source_types": ["Person", "Concept"],
        "target_types": ["Person", "Concept", "Field"],
    },
    "INFLUENCED_BY": {
        "description": "受到影响",
        "source_types": ["Person", "Concept"],
        "target_types": ["Person", "Concept"],
    },
    "KNOWN_FOR": {
        "description": "以...著名",
        "source_types": ["Person"],
        "target_types": ["Concept", "Publication", "Event"],
    },
    "PART_OF": {
        "description": "隶属于/是...的一部分",
        "source_types": ["Institution", "Place", "Concept"],
        "target_types": ["Institution", "Place", "Field"],
    },
    "FIELD_OF_WORK": {
        "description": "研究领域",
        "source_types": ["Person"],
        "target_types": ["Field"],
    },
    "ABOUT": {
        "description": "关于/涉及（论文涉及的概念）",
        "source_types": ["Publication"],
        "target_types": ["Concept", "Field"],
    },
}


def get_entity_type_names() -> list[str]:
    """获取所有实体类型名称"""
    return list(ENTITY_TYPES.keys())


def get_relation_type_names() -> list[str]:
    """获取所有关系类型名称"""
    return list(RELATION_TYPES.keys())


def get_ontology_prompt_description() -> str:
    """生成用于 LLM prompt 的本体描述文本"""
    lines = ["## 知识图谱本体定义\n"]

    lines.append("### 实体类型:")
    for etype, info in ENTITY_TYPES.items():
        props = ", ".join(info["properties"].keys())
        lines.append(f"- **{etype}** ({info['description']}): 属性=[{props}]")

    lines.append("\n### 关系类型:")
    for rtype, info in RELATION_TYPES.items():
        src = "/".join(info["source_types"])
        tgt = "/".join(info["target_types"])
        lines.append(f"- **{rtype}** ({info['description']}): {src} → {tgt}")

    return "\n".join(lines)
