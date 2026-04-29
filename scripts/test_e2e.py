"""端到端综合测试脚本"""
import json
from pathlib import Path
from neo4j import GraphDatabase

from src.config import (
    DATA_PROCESSED_DIR, OUTPUT_DIR,
    NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD,
)

print("=" * 60)
print("综合测试 (Comprehensive Test)")
print("=" * 60)

ok = True

def check(label, cond, detail=""):
    global ok
    status = "PASS" if cond else "FAIL"
    if not cond:
        ok = False
    print(f"  [{status}] {label}{(' — ' + detail) if detail else ''}")

# 1. JSON 文件
print("\n[1] 数据文件")
final_path = DATA_PROCESSED_DIR / "final_triples.json"
inferred_path = DATA_PROCESSED_DIR / "inferred_triples.json"
viz_path = OUTPUT_DIR / "turing_kg.html"

data = json.load(open(final_path, "r", encoding="utf-8"))
inferred = json.load(open(inferred_path, "r", encoding="utf-8"))

check(f"final_triples.json 存在", final_path.exists())
check(f"inferred_triples.json 存在", inferred_path.exists())
check(f"turing_kg.html 存在", viz_path.exists(), f"size={viz_path.stat().st_size if viz_path.exists() else 0}")

ent_count = len(data["entities"])
rel_count = len(data["relations"])
inf_count = len(inferred["relations"])
check(f"实体数 ≥ 200", ent_count >= 200, f"实际 {ent_count}")
check(f"关系数 ≥ 150", rel_count >= 150, f"实际 {rel_count}")
check(f"推理关系数 > 0", inf_count > 0, f"实际 {inf_count}")

# 2. 脏数据过滤生效
print("\n[2] Schema 校验 / 黑名单")
ent_ids = set(data["entities"].keys())
ent_names = [e.get("name", "").lower() for e in data["entities"].values()]

bad_ids_in_data = [k for k in ent_ids if "wikipedia" in k.lower() or "wikiproject" in k.lower()]
check("无 wikipedia/wikiproject 元数据实体", len(bad_ids_in_data) == 0, str(bad_ids_in_data))

inst_atheism = [e for e in data["entities"].values() if e.get("type") == "Institution" and e.get("name", "").lower().strip() == "atheism"]
check("无 'atheism' 作为机构", len(inst_atheism) == 0)

# 类型合法性
from src.ontology import ENTITY_TYPES, RELATION_TYPES
illegal_types = [(k, e.get("type")) for k, e in data["entities"].items() if e.get("type") not in ENTITY_TYPES]
check("所有实体类型合法", len(illegal_types) == 0, str(illegal_types[:3]))

illegal_rels = [r for r in data["relations"] if r["relation"] not in RELATION_TYPES]
check("所有关系类型合法", len(illegal_rels) == 0)

# 3. 实体对齐效果
print("\n[3] 实体对齐")
# 仅检查是否存在重复的 Person 节点表示图灵本人
turing_person_dups = [
    k for k, e in data["entities"].items()
    if e.get("type") == "Person"
    and "alan" in e.get("name", "").lower()
    and "turing" in e.get("name", "").lower()
    and k != "person_alan_turing"
]
check("无 Alan Turing Person 重复节点", len(turing_person_dups) == 0, str(turing_person_dups))

turing = data["entities"].get("person_alan_turing", {})
check("person_alan_turing 节点存在", bool(turing))
check("person_alan_turing 类型为 Person", turing.get("type") == "Person")

turing_out_rels = [r for r in data["relations"] if r["source"] == "person_alan_turing"]
check("person_alan_turing 出向关系 ≥ 50", len(turing_out_rels) >= 50, f"实际 {len(turing_out_rels)}")

# 4. Neo4j 数据
print("\n[4] Neo4j 数据库")
d = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
with d.session() as s:
    nc = s.run("MATCH (n) RETURN count(n) AS c").single()["c"]
    rc = s.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
    inferred_neo = s.run("MATCH ()-[r]->() WHERE r.inferred=true RETURN count(r) AS c").single()["c"]
    turing_node = s.run("MATCH (n {id:'person_alan_turing'}) RETURN n.name AS name").single()
    turing_out = s.run("MATCH (t {id:'person_alan_turing'})-[r]->() RETURN count(r) AS c").single()["c"]
    constraints = list(s.run("SHOW CONSTRAINTS"))
    indexes = list(s.run("SHOW INDEXES"))

    # 示例查询
    direct = list(s.run("MATCH (t:Person {id:'person_alan_turing'})-[r]->(n) RETURN type(r) AS rel, n.name AS name LIMIT 5"))
    wwii = list(s.run("MATCH (t:Person {id:'person_alan_turing'})-[]-(n) WHERE n.name CONTAINS 'Bletchley' OR n.name CONTAINS 'Enigma' RETURN n.name AS name"))

check(f"节点数 ≥ 200", nc >= 200, f"实际 {nc}")
check(f"关系数 ≥ 150", rc >= 150, f"实际 {rc}")
check(f"推理关系 inferred=true 数 = JSON 中数", inferred_neo == inf_count, f"Neo4j={inferred_neo}, JSON={inf_count}")
check(f"Alan Turing 节点存在于 Neo4j", turing_node and turing_node["name"] == "Alan Turing")
check(f"Alan Turing 在 Neo4j 中出向关系 ≥ 50", turing_out >= 50, f"实际 {turing_out}")
check(f"约束 ≥ 1", len(constraints) >= 1, f"实际 {len(constraints)}")
check(f"索引 ≥ 1", len(indexes) >= 1, f"实际 {len(indexes)}")
check(f"图灵直接关系 Cypher 查询有结果", len(direct) > 0, f"返回 {len(direct)} 条")
check(f"二战关联 (Bletchley/Enigma) 查询有结果", len(wwii) > 0, f"返回 {len(wwii)} 条")

d.close()

# 5. 可视化 HTML
print("\n[5] 可视化")
html = viz_path.read_text(encoding="utf-8")
check("HTML 含 vis-network", "vis-network" in html.lower() or "vis.js" in html.lower())
check("HTML 含 Alan Turing 节点", "Alan Turing" in html)
check("HTML 体积 ≥ 100KB", len(html) >= 100_000, f"实际 {len(html)} bytes")
check("HTML 含虚线推理边 (dashes)", '"dashes": true' in html or "'dashes': true" in html)

print("\n" + "=" * 60)
print("RESULT:", "ALL PASSED" if ok else "SOME FAILED")
print("=" * 60)
