"""知识存储模块 - 将知识图谱数据导入 Neo4j 图数据库"""

import json
import logging

from neo4j import GraphDatabase

from src.config import DATA_PROCESSED_DIR, NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER

logger = logging.getLogger(__name__)


class Neo4jStorage:
    """Neo4j 图数据库存储管理"""

    def __init__(self):
        self.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        logger.info("Neo4j 连接已建立: %s", NEO4J_URI)

    def close(self):
        self.driver.close()
        logger.info("Neo4j 连接已关闭")

    def verify_connection(self) -> bool:
        """验证 Neo4j 连接"""
        try:
            with self.driver.session() as session:
                result = session.run("RETURN 1 AS test")
                result.single()
            logger.info("Neo4j 连接验证成功")
            return True
        except Exception as e:
            logger.error("Neo4j 连接失败: %s", e)
            return False

    def clear_database(self):
        """清空数据库（谨慎使用）"""
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
        logger.info("数据库已清空")

    def create_constraints_and_indexes(self):
        """创建唯一性约束和索引"""
        logger.info("=== 创建 Schema 约束和索引 ===")

        entity_types = ["Person", "Institution", "Publication", "Concept",
                        "Event", "Place", "Award", "Field"]

        with self.driver.session() as session:
            for label in entity_types:
                try:
                    session.run(
                        f"CREATE CONSTRAINT IF NOT EXISTS "
                        f"FOR (n:{label}) REQUIRE n.id IS UNIQUE"
                    )
                    logger.info("  创建约束: %s.id UNIQUE", label)
                except Exception as e:
                    logger.warning("  约束创建跳过 %s: %s", label, e)

                try:
                    session.run(
                        f"CREATE INDEX IF NOT EXISTS "
                        f"FOR (n:{label}) ON (n.name)"
                    )
                    logger.info("  创建索引: %s.name", label)
                except Exception as e:
                    logger.warning("  索引创建跳过 %s: %s", label, e)

    def import_entities(self, entities: dict):
        """批量导入实体节点"""
        logger.info("=== 开始导入实体节点 ===")

        # 按类型分组
        by_type = {}
        for entity in entities.values():
            etype = entity.get("type", "Concept")
            by_type.setdefault(etype, []).append(entity)

        with self.driver.session() as session:
            for label, entity_list in by_type.items():
                # 使用 UNWIND + MERGE 批量导入
                query = f"""
                UNWIND $entities AS e
                MERGE (n:{label} {{id: e.id}})
                SET n += e
                """
                session.run(query, entities=entity_list)
                logger.info("  导入 %s: %d 个节点", label, len(entity_list))

        total = sum(len(v) for v in by_type.values())
        logger.info("实体导入完成: 共 %d 个节点", total)

    def import_relations(self, relations: list):
        """批量导入关系"""
        logger.info("=== 开始导入关系 ===")

        # 按关系类型分组
        by_type = {}
        for rel in relations:
            rtype = rel.get("relation", "")
            if rtype:
                by_type.setdefault(rtype, []).append(rel)

        with self.driver.session() as session:
            for rel_type, rel_list in by_type.items():
                # 构建带属性的导入查询
                query = f"""
                UNWIND $relations AS r
                MATCH (source {{id: r.source}})
                MATCH (target {{id: r.target}})
                MERGE (source)-[rel:{rel_type}]->(target)
                SET rel += CASE WHEN r.properties IS NOT NULL THEN r.properties ELSE {{}} END
                """
                session.run(query, relations=rel_list)
                logger.info("  导入关系 %s: %d 条", rel_type, len(rel_list))

        total = sum(len(v) for v in by_type.values())
        logger.info("关系导入完成: 共 %d 条关系", total)

    def get_statistics(self) -> dict:
        """获取数据库统计信息"""
        with self.driver.session() as session:
            node_count = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
            rel_count = session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
            label_counts = {}
            result = session.run(
                "MATCH (n) RETURN labels(n)[0] AS label, count(n) AS c ORDER BY c DESC"
            )
            for record in result:
                label_counts[record["label"]] = record["c"]

            rel_type_counts = {}
            result = session.run(
                "MATCH ()-[r]->() RETURN type(r) AS t, count(r) AS c ORDER BY c DESC"
            )
            for record in result:
                rel_type_counts[record["t"]] = record["c"]

        stats = {
            "total_nodes": node_count,
            "total_relationships": rel_count,
            "node_labels": label_counts,
            "relationship_types": rel_type_counts,
        }
        logger.info("Neo4j 统计: %d 节点, %d 关系", node_count, rel_count)
        return stats

    def export_all(self) -> dict:
        """导出所有节点和关系（用于可视化）"""
        nodes = []
        edges = []

        with self.driver.session() as session:
            # 导出节点
            result = session.run(
                "MATCH (n) RETURN n, labels(n) AS labels, elementId(n) AS eid"
            )
            for record in result:
                node = dict(record["n"])
                node["_labels"] = record["labels"]
                node["_eid"] = record["eid"]
                nodes.append(node)

            # 导出关系
            result = session.run(
                "MATCH (s)-[r]->(t) "
                "RETURN s.id AS source, type(r) AS relation, t.id AS target, properties(r) AS props"
            )
            for record in result:
                edges.append({
                    "source": record["source"],
                    "relation": record["relation"],
                    "target": record["target"],
                    "properties": dict(record["props"]) if record["props"] else {},
                })

        logger.info("导出完成: %d 节点, %d 关系", len(nodes), len(edges))
        return {"nodes": nodes, "edges": edges}


def store_all():
    """执行完整的知识存储流程"""
    logger.info("========== 知识存储流程开始 ==========")

    # 加载融合后的数据
    data_path = DATA_PROCESSED_DIR / "final_triples.json"
    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    entities = data.get("entities", {})
    relations = data.get("relations", [])

    storage = Neo4jStorage()

    try:
        # 验证连接
        if not storage.verify_connection():
            raise ConnectionError("无法连接到 Neo4j，请确保 Docker 容器已启动")

        # 清空并重建
        storage.clear_database()
        storage.create_constraints_and_indexes()

        # 导入数据
        storage.import_entities(entities)
        storage.import_relations(relations)

        # 统计
        stats = storage.get_statistics()
        logger.info("========== 知识存储流程完成 ==========")
        return stats

    finally:
        storage.close()
