"""知识推理与查询模块 - 基于 Cypher 的推理规则和查询示例"""

import json
import logging

from neo4j import GraphDatabase

from src.config import DATA_PROCESSED_DIR, NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER

logger = logging.getLogger(__name__)


class KnowledgeReasoner:
    """知识推理引擎"""

    def __init__(self):
        self.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    def close(self):
        self.driver.close()

    def _run_query(self, query: str, params: dict = None) -> list:
        """执行 Cypher 查询并返回结果"""
        with self.driver.session() as session:
            result = session.run(query, params or {})
            return [dict(record) for record in result]

    # ============================================================
    # 推理规则
    # ============================================================

    def infer_worked_in_location(self) -> int:
        """传递性推理: Person WORKED_AT Institution LOCATED_IN Place → Person WORKED_IN Place"""
        query = """
        MATCH (p:Person)-[:WORKED_AT]->(i:Institution)-[:LOCATED_IN]->(pl:Place)
        WHERE NOT (p)-[:WORKED_IN]->(pl)
        MERGE (p)-[r:WORKED_IN {inferred: true}]->(pl)
        RETURN count(r) AS created
        """
        result = self._run_query(query)
        count = result[0]["created"] if result else 0
        logger.info("推理 WORKED_IN (传递): 新增 %d 条关系", count)
        return count

    def infer_educated_in_location(self) -> int:
        """传递性推理: Person EDUCATED_AT Institution LOCATED_IN Place → Person STUDIED_IN Place"""
        query = """
        MATCH (p:Person)-[:EDUCATED_AT]->(i:Institution)-[:LOCATED_IN]->(pl:Place)
        WHERE NOT (p)-[:STUDIED_IN]->(pl)
        MERGE (p)-[r:STUDIED_IN {inferred: true}]->(pl)
        RETURN count(r) AS created
        """
        result = self._run_query(query)
        count = result[0]["created"] if result else 0
        logger.info("推理 STUDIED_IN (传递): 新增 %d 条关系", count)
        return count

    def infer_symmetric_collaboration(self) -> int:
        """对称性推理: A COLLABORATED_WITH B → B COLLABORATED_WITH A"""
        query = """
        MATCH (a:Person)-[:COLLABORATED_WITH]->(b:Person)
        WHERE NOT (b)-[:COLLABORATED_WITH]->(a)
        MERGE (b)-[r:COLLABORATED_WITH {inferred: true}]->(a)
        RETURN count(r) AS created
        """
        result = self._run_query(query)
        count = result[0]["created"] if result else 0
        logger.info("推理 COLLABORATED_WITH (对称): 新增 %d 条关系", count)
        return count

    def infer_field_from_publications(self) -> int:
        """推理: Person AUTHORED Publication ABOUT Field → Person FIELD_OF_WORK Field"""
        query = """
        MATCH (p:Person)-[:AUTHORED]->(pub:Publication)-[:ABOUT]->(f:Field)
        WHERE NOT (p)-[:FIELD_OF_WORK]->(f)
        MERGE (p)-[r:FIELD_OF_WORK {inferred: true}]->(f)
        RETURN count(r) AS created
        """
        result = self._run_query(query)
        count = result[0]["created"] if result else 0
        logger.info("推理 FIELD_OF_WORK (经出版物): 新增 %d 条关系", count)
        return count

    def run_all_inferences(self) -> dict:
        """执行所有推理规则"""
        logger.info("=== 开始知识推理 ===")
        results = {
            "worked_in": self.infer_worked_in_location(),
            "studied_in": self.infer_educated_in_location(),
            "collaboration_symmetric": self.infer_symmetric_collaboration(),
            "field_from_publications": self.infer_field_from_publications(),
        }
        total = sum(results.values())
        logger.info("推理完成: 共新增 %d 条推理关系", total)
        return results

    def export_inferred_relations(self) -> list:
        """导出所有推理生成的关系到列表（properties.inferred=true）"""
        query = """
        MATCH (s)-[r]->(t)
        WHERE r.inferred = true
        RETURN s.id AS source, type(r) AS relation, t.id AS target
        """
        rels = self._run_query(query)
        out = [
            {
                "source": r["source"],
                "relation": r["relation"],
                "target": r["target"],
                "properties": {"inferred": True},
            }
            for r in rels
            if r["source"] and r["target"]
        ]
        logger.info("导出推理关系: %d 条", len(out))
        return out

    # ============================================================
    # 查询示例
    # ============================================================

    def query_turing_direct_relations(self) -> list:
        """查询图灵的所有直接关系"""
        query = """
        MATCH (t:Person {name: "Alan Turing"})-[r]->(n)
        RETURN type(r) AS relation, labels(n)[0] AS target_type, n.name AS target_name
        ORDER BY type(r), n.name
        """
        results = self._run_query(query)
        logger.info("图灵直接关系: %d 条", len(results))
        return results

    def query_academic_lineage(self) -> list:
        """查询学术传承链（师生关系路径）"""
        query = """
        MATCH path = (s:Person)-[:ADVISED_BY|ADVISED*1..5]->(t:Person)
        WHERE s.name = "Alan Turing" OR t.name = "Alan Turing"
        RETURN [n IN nodes(path) | n.name] AS lineage,
               length(path) AS depth
        ORDER BY depth
        """
        results = self._run_query(query)
        logger.info("学术传承链: %d 条路径", len(results))
        return results

    def query_collaborators(self) -> list:
        """查询与图灵合作过的所有人物"""
        query = """
        MATCH (t:Person {name: "Alan Turing"})-[:COLLABORATED_WITH|WORKED_AT]->()<-[:COLLABORATED_WITH|WORKED_AT]-(p:Person)
        WHERE p <> t
        RETURN DISTINCT p.name AS collaborator, p.description AS description
        ORDER BY p.name
        """
        results = self._run_query(query)
        logger.info("合作者: %d 人", len(results))
        return results

    def query_wwii_connections(self) -> list:
        """查询二战期间的所有关联"""
        query = """
        MATCH (t:Person {name: "Alan Turing"})-[r]-(n)
        WHERE n.name CONTAINS "Bletchley" OR n.name CONTAINS "war"
           OR n.name CONTAINS "Enigma" OR n.name CONTAINS "crypt"
           OR n.description CONTAINS "war" OR n.description CONTAINS "crypt"
        RETURN type(r) AS relation, labels(n)[0] AS type, n.name AS name, n.description AS description
        """
        results = self._run_query(query)
        logger.info("二战关联: %d 条", len(results))
        return results

    def query_cs_concepts(self) -> list:
        """查询图灵贡献的计算机科学概念"""
        query = """
        MATCH (t:Person {name: "Alan Turing"})-[:KNOWN_FOR|CONTRIBUTED_TO|INFLUENCED]->(c)
        WHERE c:Concept OR c:Field
        RETURN labels(c)[0] AS type, c.name AS concept, c.description AS description
        ORDER BY c.name
        """
        results = self._run_query(query)
        logger.info("计算科学概念: %d 个", len(results))
        return results

    def query_shortest_path(self, from_name: str, to_name: str) -> list:
        """查询两个实体间的最短路径"""
        query = """
        MATCH path = shortestPath((a {name: $from_name})-[*..6]-(b {name: $to_name}))
        RETURN [n IN nodes(path) | n.name] AS path_nodes,
               [r IN relationships(path) | type(r)] AS path_relations,
               length(path) AS distance
        """
        results = self._run_query(query, {"from_name": from_name, "to_name": to_name})
        logger.info("最短路径 %s → %s: %d 条", from_name, to_name, len(results))
        return results

    def run_sample_queries(self) -> dict:
        """运行所有示例查询"""
        logger.info("=== 运行示例查询 ===")
        return {
            "direct_relations": self.query_turing_direct_relations(),
            "academic_lineage": self.query_academic_lineage(),
            "collaborators": self.query_collaborators(),
            "wwii_connections": self.query_wwii_connections(),
            "cs_concepts": self.query_cs_concepts(),
        }


def reason_all() -> dict:
    """执行完整的知识推理和查询流程"""
    logger.info("========== 知识推理流程开始 ==========")

    reasoner = KnowledgeReasoner()
    try:
        # 执行推理
        inference_results = reasoner.run_all_inferences()

        # 导出推理关系到 JSON（供可视化在无 Neo4j 时使用）
        inferred = reasoner.export_inferred_relations()
        out_path = DATA_PROCESSED_DIR / "inferred_triples.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({"relations": inferred}, f, ensure_ascii=False, indent=2)
        logger.info("推理关系已写入 %s", out_path)

        # 运行示例查询
        query_results = reasoner.run_sample_queries()

        logger.info("========== 知识推理流程完成 ==========")
        return {
            "inferences": inference_results,
            "queries": query_results,
        }
    finally:
        reasoner.close()
