"""可视化模块 - 使用 Pyvis 生成交互式知识图谱可视化"""

import json
import logging

import networkx as nx
from pyvis.network import Network

from src.config import DATA_PROCESSED_DIR, NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER, OUTPUT_DIR

logger = logging.getLogger(__name__)

# 实体类型颜色映射
TYPE_COLORS = {
    "Person": "#4A90D9",        # 蓝色
    "Institution": "#2ECC71",   # 绿色
    "Publication": "#9B59B6",   # 紫色
    "Concept": "#E67E22",       # 橙色
    "Event": "#E74C3C",         # 红色
    "Place": "#1ABC9C",         # 青色
    "Award": "#F1C40F",         # 金色
    "Field": "#95A5A6",         # 灰色
}

# 实体类型中文标签
TYPE_LABELS_ZH = {
    "Person": "人物",
    "Institution": "机构",
    "Publication": "出版物",
    "Concept": "概念",
    "Event": "事件",
    "Place": "地点",
    "Award": "奖项",
    "Field": "学科领域",
}

# 关系类型颜色
RELATION_COLORS = {
    "BORN_IN": "#888888",
    "DIED_IN": "#888888",
    "EDUCATED_AT": "#3498DB",
    "WORKED_AT": "#2ECC71",
    "ADVISED_BY": "#E74C3C",
    "COLLABORATED_WITH": "#F39C12",
    "AUTHORED": "#9B59B6",
    "CONTRIBUTED_TO": "#E67E22",
    "RECEIVED": "#F1C40F",
    "PARTICIPATED_IN": "#E74C3C",
    "LOCATED_IN": "#1ABC9C",
    "RELATED_TO": "#E91E63",
    "INFLUENCED": "#FF5722",
    "KNOWN_FOR": "#FF9800",
    "PART_OF": "#607D8B",
    "FIELD_OF_WORK": "#795548",
    "ABOUT": "#9C27B0",
    "WORKED_IN": "#66BB6A",
    "STUDIED_IN": "#42A5F5",
}

# 关系类型中文标签
RELATION_LABELS_ZH = {
    "BORN_IN": "出生于",
    "DIED_IN": "去世于",
    "EDUCATED_AT": "就读于",
    "WORKED_AT": "工作于",
    "ADVISED_BY": "师从",
    "ADVISED": "指导",
    "COLLABORATED_WITH": "合作",
    "AUTHORED": "撰写",
    "CONTRIBUTED_TO": "贡献于",
    "RECEIVED": "获得",
    "PARTICIPATED_IN": "参与",
    "LOCATED_IN": "位于",
    "RELATED_TO": "关联",
    "INFLUENCED": "影响",
    "INFLUENCED_BY": "受影响于",
    "KNOWN_FOR": "以...著名",
    "PART_OF": "隶属于",
    "FIELD_OF_WORK": "研究领域",
    "ABOUT": "关于",
    "WORKED_IN": "工作地点",
    "STUDIED_IN": "求学地点",
}


def _load_graph_data() -> dict:
    """从 Neo4j 或 JSON 文件加载图数据"""
    # 优先尝试 Neo4j
    try:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        with driver.session() as session:
            session.run("RETURN 1").single()

        # Neo4j 可用，从中导出
        logger.info("从 Neo4j 加载图数据")
        from src.knowledge_storage import Neo4jStorage

        storage = Neo4jStorage()
        try:
            data = storage.export_all()
        finally:
            storage.close()
        return data
    except Exception as e:
        logger.info("Neo4j 不可用 (%s)，从 JSON 文件加载", e)

    # 回退到 JSON 文件
    json_path = DATA_PROCESSED_DIR / "final_triples.json"
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    nodes = []
    for entity in data.get("entities", {}).values():
        node = dict(entity)
        node["_labels"] = [entity.get("type", "Concept")]
        nodes.append(node)

    edges = []
    for rel in data.get("relations", []):
        edges.append({
            "source": rel["source"],
            "relation": rel["relation"],
            "target": rel["target"],
            "properties": rel.get("properties", {}),
        })

    return {"nodes": nodes, "edges": edges}


def build_networkx_graph(data: dict) -> nx.DiGraph:
    """构建 NetworkX 有向图"""
    G = nx.DiGraph()

    for node in data["nodes"]:
        nid = node.get("id", "")
        labels = node.get("_labels", ["Unknown"])
        G.add_node(nid, **{
            "name": node.get("name", nid),
            "type": labels[0] if labels else "Unknown",
            "name_zh": node.get("name_zh", ""),
            "description": node.get("description", ""),
            **{k: v for k, v in node.items() if k not in ("_labels", "_eid", "id")},
        })

    for edge in data["edges"]:
        G.add_edge(
            edge["source"],
            edge["target"],
            relation=edge["relation"],
            **edge.get("properties", {}),
        )

    logger.info("NetworkX 图构建完成: %d 节点, %d 边", G.number_of_nodes(), G.number_of_edges())
    return G


def generate_pyvis_visualization(G: nx.DiGraph, output_file: str = "turing_kg.html"):
    """生成 Pyvis 交互式可视化 HTML"""
    logger.info("=== 生成 Pyvis 可视化 ===")

    net = Network(
        height="900px",
        width="100%",
        bgcolor="#1a1a2e",
        font_color="white",
        directed=True,
        notebook=False,
        cdn_resources="remote",
    )

    # 计算节点度数（用于确定节点大小）
    degrees = dict(G.degree())
    max_degree = max(degrees.values()) if degrees else 1

    # 添加节点
    for nid, attrs in G.nodes(data=True):
        name = attrs.get("name", nid)
        node_type = attrs.get("type", "Unknown")
        name_zh = attrs.get("name_zh", "")
        description = attrs.get("description", "")

        color = TYPE_COLORS.get(node_type, "#CCCCCC")
        type_zh = TYPE_LABELS_ZH.get(node_type, node_type)

        # 节点大小：基于度数，图灵最大
        degree = degrees.get(nid, 1)
        if name == "Alan Turing":
            size = 50
        else:
            size = max(10, int(10 + 30 * (degree / max_degree)))

        # 构建 tooltip
        tooltip_parts = [f"<b>{name}</b>"]
        if name_zh:
            tooltip_parts.append(f"({name_zh})")
        tooltip_parts.append(f"<br>类型: {type_zh}")
        if description:
            tooltip_parts.append(f"<br>{description[:200]}")
        tooltip_parts.append(f"<br>连接数: {degree}")
        tooltip = " ".join(tooltip_parts)

        # 显示标签
        label = name_zh if name_zh else name
        if len(label) > 20:
            label = label[:18] + "..."

        net.add_node(
            nid,
            label=label,
            title=tooltip,
            color=color,
            size=size,
            font={"size": max(10, min(16, size // 2)), "color": "white"},
            borderWidth=2,
            borderWidthSelected=4,
        )

    # 添加边
    for source, target, attrs in G.edges(data=True):
        relation = attrs.get("relation", "")
        rel_label = RELATION_LABELS_ZH.get(relation, relation)
        color = RELATION_COLORS.get(relation, "#666666")
        is_inferred = attrs.get("inferred", False)

        net.add_edge(
            source,
            target,
            title=rel_label,
            label=rel_label,
            color=color,
            width=1.5,
            arrows="to",
            dashes=is_inferred,  # 推理关系用虚线
            font={"size": 9, "color": "#AAAAAA", "strokeWidth": 0},
        )

    # 配置物理引擎
    net.barnes_hut(
        gravity=-3000,
        central_gravity=0.5,
        spring_length=120,
        spring_strength=0.04,
        damping=0.3,
        overlap=0.5,
    )

    # 保存
    output_path = OUTPUT_DIR / output_file
    net.save_graph(str(output_path))

    # 后处理 HTML：启用 stabilization + 收敛后关闭物理 + 移除 loadingBar
    with open(output_path, "r", encoding="utf-8", errors="replace") as f:
        html = f.read()

    # 1) 将 stabilization "enabled": false 改为 true
    html = html.replace(
        '"stabilization": {\n            "enabled": false,',
        '"stabilization": {\n            "enabled": true,',
    )

    # 2) 移除 loadingBar div
    import re
    html = re.sub(
        r'<div id="loadingBar">.*?</div>\s*</div>\s*</div>',
        '', html, flags=re.DOTALL,
    )

    # 3) 替换 loadingBar JS 监听器为：收敛后关闭物理引擎
    html = re.sub(
        r'network\.on\("stabilizationProgress".*?network\.once\("stabilizationIterationsDone".*?\}\);',
        'network.once("stabilizationIterationsDone", function() {\n'
        '                          network.setOptions({ physics: false });\n'
        '                      });',
        html, flags=re.DOTALL,
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    # 注入自定义 HTML（图例 + 统计）
    _inject_legend_and_stats(output_path, G)

    logger.info("可视化已保存至: %s", output_path)
    return str(output_path)


def _inject_legend_and_stats(html_path, G: nx.DiGraph):
    """向 HTML 中注入图例和统计信息"""
    # 统计信息
    type_counts = {}
    for _, attrs in G.nodes(data=True):
        t = attrs.get("type", "Unknown")
        type_counts[t] = type_counts.get(t, 0) + 1

    # 构建图例 HTML
    legend_items = ""
    for etype, color in TYPE_COLORS.items():
        count = type_counts.get(etype, 0)
        if count > 0:
            zh = TYPE_LABELS_ZH.get(etype, etype)
            legend_items += (
                f'<div style="display:flex;align-items:center;margin:4px 0;">'
                f'<span style="width:14px;height:14px;border-radius:50%;background:{color};'
                f'display:inline-block;margin-right:8px;"></span>'
                f'{zh} ({count})</div>'
            )

    legend_html = f"""
    <div id="kg-legend" style="position:fixed;top:10px;left:10px;background:rgba(26,26,46,0.92);
        color:white;padding:15px 20px;border-radius:10px;font-family:sans-serif;font-size:13px;
        z-index:9999;box-shadow:0 4px 15px rgba(0,0,0,0.3);max-width:220px;">
        <div style="font-size:16px;font-weight:bold;margin-bottom:10px;
            border-bottom:1px solid #444;padding-bottom:8px;">
            🧠 图灵知识图谱
        </div>
        <div style="margin-bottom:8px;color:#aaa;">
            节点: {G.number_of_nodes()} | 关系: {G.number_of_edges()}
        </div>
        {legend_items}
        <div style="margin-top:10px;padding-top:8px;border-top:1px solid #444;color:#aaa;font-size:11px;">
            虚线 = 推理关系<br>
            点击节点查看详情<br>
            滚轮缩放 | 拖拽移动
        </div>
    </div>
    """

    with open(html_path, "r", encoding="utf-8", errors="replace") as f:
        html = f.read()

    # 注入到 body 标签后
    html = html.replace("<body>", f"<body>\n{legend_html}")

    # 更新标题
    html = html.replace("<title>", "<title>图灵知识图谱 | Turing Knowledge Graph - ")

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)


def visualize_all(output_file: str = "turing_kg.html") -> str:
    """执行完整的可视化流程"""
    logger.info("========== 可视化流程开始 ==========")

    # 加载数据
    data = _load_graph_data()

    # 构建 NetworkX 图
    G = build_networkx_graph(data)

    # 生成可视化
    path = generate_pyvis_visualization(G, output_file)

    logger.info("========== 可视化流程完成 ==========")
    return path
