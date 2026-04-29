# 图灵知识图谱：方法、数据来源与数据形式

> 本文档系统说明项目每一阶段所采用的**方法**、**数据来源**、**数据形式**与**关键产物**，配合 [README.md](../README.md) 阅读。

---

## 0. 总览

```
Wikidata SPARQL ──┐                                        ┌─► Neo4j 5 (属性图)
                  ├─► 知识抽取 ─► 知识融合 ─► 持久化 ──────┤
Wikipedia REST ───┘                                        └─► JSON 三元组
                                                                  │
                                                                  ▼
                                                         Pyvis 交互式 HTML
```

| 阶段 | 输入 | 输出 | 核心方法 |
|------|------|------|---------|
| 数据采集 | API | `data/raw/*.json` | SPARQL + REST |
| 知识抽取 | 原始 JSON / 章节文本 | `data/processed/*_triples.json` | 属性映射 + LLM JSON 抽取 |
| 知识融合 | 双源三元组 | `final_triples.json` | 四级优先级实体对齐 |
| 图存储 | `final_triples.json` | Neo4j 数据库 | UNWIND + MERGE |
| 知识推理 | Neo4j 图 | 新增 `inferred=true` 边 + `inferred_triples.json` | Cypher 规则推理 |
| 可视化 | Neo4j 或 JSON | `output/turing_kg.html` | Pyvis 力导向布局 |

---

## 1. 数据采集 (`src/data_acquisition.py`)

### 1.1 数据来源

| 来源 | 接入方式 | 用途 | 合规要求 |
|------|----------|------|----------|
| **Wikidata** | SPARQL Endpoint `https://query.wikidata.org/sparql` | 结构化属性、关联人物/机构/概念 | `User-Agent: TuringKG/1.0`，请求间隔 ≥ 1s |
| **Wikipedia (英文)** | MediaWiki Action API (`?action=parse` + `?action=query&prop=extracts`) | 非结构化章节文本 | 同上；逐章节抓取避免单次响应过大 |

### 1.2 方法

- **Wikidata 通道**：8 条预定义 SPARQL 查询，覆盖：
  1. 基本属性（出生/死亡/国籍 …）
  2. 关联人物（导师、学生、合作者、亲属）
  3. 教育/工作经历
  4. 学术成就
  5. 荣誉奖项
  6. 相关学术概念
  7. 关联机构
  8. 关联事件
  - 使用 `SERVICE wikibase:label` 一次性取回中英文标签。
- **Wikipedia 通道**：先 `parse` 取章节目录，再用 `extracts` 接口逐章取纯文本，本次共 **11 个章节、约 60K 字**。

### 1.3 数据形式（产物）

- `data/raw/wikidata_turing.json`
  ```jsonc
  {
    "basic_info": [{"property": "...", "value": "...", "valueLabel": "..."}],
    "related_people": [...],
    "education": [...], "work": [...],
    "achievements": [...], "awards": [...],
    "concepts": [...], "institutions": [...], "events": [...]
  }
  ```
- `data/raw/wikipedia_turing.json`
  ```jsonc
  {
    "title": "Alan Turing",
    "sections": [
      {"title": "Early life and education", "text": "..."},
      ...
    ]
  }
  ```

---

## 2. 知识抽取 (`src/knowledge_extraction.py`)

### 2.1 结构化解析（Wikidata → 三元组）

- **方法**：`WIKIDATA_PROPERTY_MAP` 把 21 个 PID 映射到本体关系类型。
  | Wikidata PID | 本体关系 |
  |---|---|
  | P19 出生地 | BORN_IN |
  | P20 去世地 | DIED_IN |
  | P69 教育机构 | EDUCATED_AT |
  | P108 任职机构 | WORKED_AT |
  | P184 博导 | ADVISED_BY |
  | P166 获奖 | RECEIVED |
  | P22/P25/P40 父/母/子女 | RELATED_TO（带 `relationship` 子类型） |
  | … | …（共 21 项） |
- **产物**：`data/processed/wikidata_triples.json`
  ```jsonc
  {
    "entities": [
      {"id": "person_alan_turing", "type": "Person", "name": "Alan Turing",
       "wikidata_id": "Q7251", "properties": {...}}
    ],
    "relations": [
      {"subject": "person_alan_turing", "predicate": "BORN_IN",
       "object": "place_london", "properties": {}}
    ]
  }
  ```

### 2.2 LLM 文本抽取（Wikipedia → 三元组）

- **模型**：DeepSeek `deepseek-chat`，OpenAI 兼容 SDK。
- **Prompt 设计**：
  - System：注入 8 类实体 + 17 种关系本体定义、命名规范、JSON Schema。
  - User：单章节文本（≤ 4000 字符）+ 输出格式约束。
- **容错**：
  - `max_tokens=8192`；
  - `_repair_truncated_json()` 修复尾部截断（补 `]` `}` `"`）；
  - 单章节失败自动跳过。
- **Schema 校验与脱仓清洗（`_validate_extracted`）**：
  - 实体类型 ∉ `ENTITY_TYPES` → 丢弃；关系类型 ∉ `RELATION_TYPES` → 丢弃；
  - 名称黑名单正则：`wikipedia` / `wikiproject` / `category:` / `talk:` / `template:` / `disambiguation` / `main page` / `wiki99`；
  - 类型化黑名单：`(atheism, Institution)`、`(turing, Concept)` 等；
  - 引用了不存在实体的关系、自环关系一并丢弃。
  - 同一黑名单在融合阶段对 Wikidata 与 LLM 双源都会再过一遍，避免 Wikidata 维基元数据页混入。
- **产物**：`data/processed/extracted_triples.json`（结构同上）。

---

## 3. 知识融合 (`src/knowledge_fusion.py`)

### 3.1 实体对齐（四级优先级，高 → 低）

| 优先级 | 触发条件 | 设计动机 |
|---|---|---|
| 0 | **ID 完全相同** | LLM 输出的规范 ID（如 `person_alan_turing`）与 Wikidata 同 ID 直接合并，避免后续因名称差异（"Alan Turing" vs "Alan Mathison Turing"）相似度低于阈值而漏合 |
| 1 | **`wikidata_id` (QID) 相同** | QID 是全球唯一标识，避免同名不同实体误合 |
| 2 | **(归一化名称, 实体类型) 一致** | `_normalize_name()` 转小写、去括号、去标点、合并空白 |
| 3 | **同类型 `SequenceMatcher` ≥ 0.88** | 处理缩写、多体变体（如 "ACE" / "Automatic Computing Engine"） |
| — | 均未命中 → 新实体 | **已移除原本过于宽松的子串匹配**，避免 Place ⟂ Person 跨类型误合 |

合并时取非空属性的并集，不覆盖已有高质量字段。

### 3.2 清洗与脱敏

- **日期标准化**：所有日期转 ISO 8601 (`YYYY-MM-DD`)。
- **嵌套属性展平**（`_flatten_for_neo4j`）：
  - 把 LLM 偶发输出的 `properties: {...}` 字典提升到顶层；
  - 过滤为 Neo4j 仅支持的原语类型（string/int/float/bool 及其数组），避免 `CypherTypeError: Property values can only be of primitive types`。
- **类型验证**：实体/关系类型必须在本体定义内。
- **孤立节点检测**：标记无任何边的节点。
- **黑名单二次过滤**：覆盖 Wikidata 来源的维基元数据。

### 3.3 数据形式（产物）

- `data/processed/final_triples.json`：**221 实体 / 202 关系**，结构与 2.1 相同，所有属性已扁平化。

---

## 4. 图存储 (`src/knowledge_storage.py`)

- **数据库**：Neo4j 5（Docker，镜像 `neo4j:5`，URI `neo4j://127.0.0.1:7687`）。
- **方法**：
  - 8 类标签每类 1 条 `CREATE CONSTRAINT n.id IS UNIQUE` → 共 **8 条约束**；
  - 为常用字段建索引 → 共 **18 条索引**（含 8 条唯一性派生索引）；
  - 节点与关系导入采用 `UNWIND $rows AS row MERGE …`，幂等。
- **产物**：Neo4j 实例内的图，节点 221 / 关系 202（推理后 213）。

---

## 5. 知识推理 (`src/knowledge_reasoning.py`)

### 5.1 推理规则（4 条 Cypher）

| # | 规则 | 类型 | 模式 → 推导 |
|---|---|---|---|
| 1 | 工作地 | 传递 | `(p)-[:WORKED_AT]->(i)-[:LOCATED_IN]->(pl)` ⇒ `(p)-[:WORKED_IN {inferred:true}]->(pl)` |
| 2 | 求学地 | 传递 | `(p)-[:EDUCATED_AT]->(i)-[:LOCATED_IN]->(pl)` ⇒ `(p)-[:STUDIED_IN {inferred:true}]->(pl)` |
| 3 | 合作对称 | 对称 | `(a)-[:COLLABORATED_WITH]->(b)` ⇒ `(b)-[:COLLABORATED_WITH {inferred:true}]->(a)` |
| 4 | 研究领域 | 组合 | `(p)-[:AUTHORED]->(pub)-[:ABOUT]->(f)` ⇒ `(p)-[:FIELD_OF_WORK {inferred:true}]->(f)` |

本轮推理共新增 **11 条 `inferred=true` 边**。

### 5.2 双路持久化

- 推理直接写回 Neo4j；
- 同步导出 `data/processed/inferred_triples.json`，供可视化在 Neo4j 不可用时仍能渲染虚线推理边。

### 5.3 示例查询（5 条）

最短路径 / 协作网络 / 影响力排名 / 时间线 / 领域聚合，详见 `src/knowledge_reasoning.py::run_sample_queries()`。

---

## 6. 可视化 (`src/visualization.py`)

- **库**：Pyvis（封装 vis-network.js）。
- **数据源优先级**：Neo4j → 失败回退到 `final_triples.json` + `inferred_triples.json` 合并加载。
- **布局**：Barnes-Hut（重力 -3000，中心引力 0.5，弹簧 120，阻尼 0.3）；300 轮稳定化后关物理引擎。
- **视觉编码**：
  - 节点颜色按 8 类实体；
  - 节点大小映射度数（10–50px），图灵节点固定 50px；
  - 推理边 `dashes: true`；
  - Tooltip：英文名 / 中文名 / 类型 / 描述 / 度数。
- **产物**：`output/turing_kg.html`（约 160 KB，单文件可独立分发）。

---

## 7. 端到端验证 (`scripts/test_e2e.py`)

22 项断言分 5 段：

| 段 | 项数 | 检查内容 |
|---|---|---|
| [1] 数据文件 | 3 | 实体数 ≥ 200、关系数 ≥ 150、推理关系 > 0 |
| [2] Schema / 黑名单 | 4 | 无 wikipedia/wikiproject 元数据、无 atheism 机构、所有类型合法 |
| [3] 实体对齐 | 4 | Alan Turing 节点唯一、ID 正确、出向 ≥ 50 |
| [4] Neo4j | 9 | 节点 ≥ 200、关系 ≥ 150、约束 ≥ 1、索引 ≥ 1、示例查询有结果 |
| [5] 可视化 | 4 | HTML 含 vis-network、含图灵节点、体积 ≥ 100 KB、含虚线 |

当前实测：**22 / 22 PASS**。

---

## 8. 关键决策与教训

| 问题 | 现象 | 根因 | 解法 |
|---|---|---|---|
| Neo4j 导入报 `CypherTypeError` | 部分节点写入失败 | LLM 偶发输出嵌套 `properties` | `_flatten_for_neo4j()` 展平 + 原语过滤 |
| 图灵示例查询返回 0 行 | Alan Turing 出向关系为 0 | LLM 用 `id=person_alan_turing`、Wikidata 用规范全名，名称相似度 < 0.88 | 对齐新增**优先级 0：ID 完全相同直接合并** |
| 出现 `wikiproject_mathematics` 等机构 | 维基元数据页污染图谱 | 黑名单只在 LLM 阶段生效 | 融合阶段再过一遍黑名单 |
| 旧版 Place ↔ Person 误合 | 跨类型实体合并 | 子串匹配过宽 | 移除子串匹配，仅保留同类型相似度判定 |

---

## 9. 复现命令清单

```powershell
# 全流程
uv run python main.py

# 分步
uv run python main.py --step acquisition
uv run python main.py --step extraction
uv run python main.py --step fusion
uv run python main.py --step storage
uv run python main.py --step reasoning
uv run python main.py --step visualize

# 验证
$env:PYTHONPATH="." ; uv run python scripts/test_e2e.py

# 展示
start output/turing_kg.html        # 浏览器打开 HTML
start http://localhost:7474        # Neo4j Browser
```
