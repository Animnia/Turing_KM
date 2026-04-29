# 图灵知识图谱 (Turing Knowledge Graph)

> 2026 年知识工程个人作业

基于**工程级知识图谱构建范式**，围绕计算机科学之父 **Alan Turing（艾伦·图灵）** 构建完整知识图谱。项目覆盖从数据采集、知识抽取、知识融合、图数据库存储、知识推理到交互式可视化的全流程，最终生成包含 **221 个实体**、**202 条原始关系** 与 **11 条推理关系** 的知识图谱。

> 📘 想直接看每一阶段的**方法、数据来源、数据形式**？请阅读 [docs/methodology.md](docs/methodology.md)。

---

## 技术栈总览

| 层级 | 组件 | 技术 | 说明 |
|------|------|------|------|
| 环境管理 | 包管理器 | **uv** (Astral) | 高性能 Python 包管理与虚拟环境工具 |
| 运行时 | 语言 | **Python 3.13** | 利用最新语言特性 (type hints, match-case 等) |
| 数据采集 | 结构化数据 | **Wikidata SPARQL API** | 通过 8 条 SPARQL 查询获取图灵相关结构化知识 |
| 数据采集 | 非结构化数据 | **Wikipedia REST API** | 获取图灵词条的全部章节文本 |
| 知识抽取 | LLM 抽取 | **DeepSeek API** (OpenAI 兼容) | 从非结构化文本中以 JSON 格式抽取实体和关系，输出后走 Schema 校验 + 黑名单过滤 |
| 知识融合 | 实体对齐 | 自研融合算法 | 四级优先级：ID → QID → (归一名,类型) 精确 → SequenceMatcher 近似（0.88）|
| 图存储 | 图数据库 | **Neo4j 5** (Docker) | 属性图模型，Cypher 查询语言 |
| 知识推理 | 推理引擎 | **Cypher 推理规则** | 传递性推理 + 对称性推理 |
| 可视化 | 前端渲染 | **Pyvis** (基于 vis-network.js) | 生成交互式 HTML 力导向图 |
| 图分析 | 图计算 | **NetworkX** | 节点度数计算、图结构分析 |
| HTTP 客户端 | 网络请求 | **Requests** | Wikidata/Wikipedia API 调用 |
| 配置管理 | 环境变量 | **python-dotenv** | 从 `.env` 文件加载敏感配置 |

---

## 项目结构

```
Turing_KM/
├── main.py                       # 主流程控制 (支持 --step 分步执行)
├── scripts/test_e2e.py           # 端到端验证脚本 (22 项检查)
├── pyproject.toml                # 项目配置与依赖声明
├── .env                          # API Key 和数据库配置 (不提交到 Git)
├── .gitignore
├── pipeline.log                  # 流水线执行日志
├── src/
│   ├── config.py                 # 集中配置管理 (加载 .env)
│   ├── ontology.py               # 本体/模式定义 (8 类实体 + 17 种关系)
│   ├── data_acquisition.py       # 数据采集 (Wikidata SPARQL + Wikipedia)
│   ├── knowledge_extraction.py   # 知识抽取 (结构化解析 + LLM 文本抽取)
│   ├── knowledge_fusion.py       # 知识融合 (实体对齐 + 清洗 + 去重)
│   ├── knowledge_storage.py      # Neo4j 图数据库存储
│   ├── knowledge_reasoning.py    # 知识推理 (Cypher 推理规则 + 查询)
│   └── visualization.py          # Pyvis 交互式可视化生成
├── data/
│   ├── raw/                      # Wikidata/Wikipedia 原始 JSON 数据
│   └── processed/                # 融合后的实体-关系三元组 JSON
├── output/
│   └── turing_kg.html            # 交互式可视化 HTML 输出
└── scripts/
    ├── start_neo4j.bat           # Neo4j Docker 一键启动 (Windows)
    └── start_neo4j.sh            # Neo4j Docker 一键启动 (Linux/Mac)
```

---

## 构建流程

项目采用 **8 阶段流水线** 架构，每个阶段可独立执行，中间数据以 JSON 文件持久化，支持断点续跑：

```
┌──────────────────────────────────────────────────────────┐
│  Phase 1-2: 环境搭建 + 本体设计 (schema-first)          │
│    · uv init + uv add 自动管理依赖和虚拟环境             │
│    · 定义 8 种实体类型 + 17 种关系类型 + 属性约束         │
└────────────────────────┬─────────────────────────────────┘
                         ▼
┌──────────────────────────────────────────────────────────┐
│  Phase 3: 数据采集 (Data Acquisition)                    │
│    · Wikidata: 8 条 SPARQL 查询 → 264 条属性 +          │
│      22 人物 + 19 机构 + 57 概念                         │
│    · Wikipedia: Parse + Extracts API → 11 章节 / 60K字   │
└────────────────────────┬─────────────────────────────────┘
                         ▼
┌──────────────────────────────────────────────────────────┐
│  Phase 4: 知识抽取 (Knowledge Extraction)                │
│    · Wikidata → 属性映射表 (21 个 PID → 关系类型)        │
│      自动解析为 92 实体 + 97 关系                        │
│    · Wikipedia → DeepSeek LLM 逐章抽取                   │
│      Prompt 注入本体约束 + Schema 校验 + 黑名单过滤    │
│      → 153 实体 + 134 关系                                │
└──────────────────────┬─────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────┐
│  Phase 5: 知识融合 (Knowledge Fusion)                    │
│    · 名称归一化 (去括号/标点/大小写统一)                  │
│    · 实体对齐四级优先级: ID → QID → 名+类型 → 近似·
│      本轮对齐: ID 12 / 精确名 5 / 近似 1 / 新增 135        │
│    · 日期标准化 + 嵌套属性展平 (Neo4j 原语型)         │
│    · 质量检查: 类型覆盖率 + 孤立节点检测                  │
│    · 输出: 221 实体 / 202 关系                           │
└────────────────────────┬─────────────────────────────────┘
                         ▼
┌──────────────────────────────────────────────────────────┐
│  Phase 6: 知识存储 (Knowledge Storage)                   │
│    · Neo4j: UNWIND + MERGE 批量导入                      │
│    · 自动创建唯一性约束 + 全文索引                        │
│    · 8 种节点标签 + 17 种关系类型                         │
└────────────────────────┬─────────────────────────────────┘
                         ▼
┌──────────────────────────────────────────────────────────┐
│  Phase 7: 知识推理 (Knowledge Reasoning)                 │
│    · 4 条 Cypher 推理规则:                               │
│      ① WORKED_AT + LOCATED_IN → WORKED_IN (传递)        │
│      ② EDUCATED_AT + LOCATED_IN → STUDIED_IN (传递)     │
│      ③ COLLABORATED_WITH 双向补全 (对称)                 │
│      ④ AUTHORED + ABOUT → FIELD_OF_WORK (推导)          │
│    · 5 条示例查询 (最短路径/社交网络/影响力链等)          │
└────────────────────────┬─────────────────────────────────┘
                         ▼
┌──────────────────────────────────────────────────────────┐
│  Phase 8: 可视化 (Visualization)                         │
│    · Pyvis 力导向图 (Barnes-Hut 算法)                    │
│    · 8 种颜色区分实体类型 + 节点大小映射度数              │
│    · 图灵节点居中高亮，推理关系用虚线表示                 │
│    · 交互: 拖拽/缩放/悬停 Tooltip/点击高亮               │
└──────────────────────────────────────────────────────────┘
```

---

## 核心技术详解

### 1. 数据采集 (`src/data_acquisition.py`)

采用**结构化 + 非结构化双通道采集**策略：

**Wikidata SPARQL 通道：**
- 通过 Wikidata Query Service (`https://query.wikidata.org/sparql`) 执行预定义 SPARQL 查询
- 8 条查询覆盖：基本属性、关联人物、教育/工作经历、学术成就、荣誉奖项、相关概念、关联机构、关联事件
- 使用 `SERVICE wikibase:label` 自动获取中英文标签
- 添加合规的 `User-Agent` 和请求间隔避免限流

**Wikipedia REST API 通道：**
- 调用 MediaWiki Action API 的 `parse` 接口获取词条结构
- 再通过 `extracts` 接口逐章节提取纯文本
- 合规 User-Agent (`TuringKG/1.0`) 避免 403 封禁
- 数据持久化为 `data/raw/wikidata_turing.json` 和 `data/raw/wikipedia_turing.json`

### 2. 知识抽取 (`src/knowledge_extraction.py`)

**结构化解析引擎：**
- 定义 `WIKIDATA_PROPERTY_MAP`：21 个 Wikidata 属性 ID (P19, P20, P69 等) 到本体关系类型的映射表
- 自动将 Wikidata JSON 解析为 `(subject, predicate, object)` 三元组
- 家族关系 (P22 父亲、P25 母亲等) 携带 `relationship` 附加属性

**LLM 文本抽取引擎：**
- 使用 **DeepSeek Chat API** (兼容 OpenAI SDK)，模型 `deepseek-chat`
- Prompt 工程设计：
  - System Prompt：注入完整本体定义 (实体类型 + 关系类型 + 示例)，约束 LLM 仅在本体框架内抽取
  - User Prompt：每次喂入一个 Wikipedia 章节（截断至 4000 字符避免 token 溢出）
  - 输出格式：严格 JSON Schema (`{"entities": [...], "relations": [...]}`)
- 容错机制：
  - `max_tokens=8192` 确保长输出不截断
  - `_repair_truncated_json()` 函数修复 LLM 输出的残缺 JSON（补全缺失的括号/引号）
  - 异常章节自动跳过，不影响整体流程

**Schema 校验与脱仓清洗（`_validate_extracted`）：**
- 实体类型必须在本体 `ENTITY_TYPES` (8 种) 中；关系类型必须在 `RELATION_TYPES` (17 种) 中，否则丢弃
- 名称黑名单正则：`wikipedia` / `wikiproject` / `category:` / `talk:` / `template:` / `disambiguation` 等 → 丢弃
- 类型化黑名单：`(atheism, Institution)`、`(turing, Concept)` 等常见脱仓误抽丢弃
- 参考完整性全面检查：丢弃引用了不存在实体的关系、自环关系
- 同一黑名单在融合阶段对 Wikidata 与 LLM 双源实体都会再过一道，避免 Wikidata 原始数据中的维基元数据页被当作机构实体


**实体对齐算法（四级优先级，高 → 低）：**
1. **ID 完全相同**：LLM Prompt 中固定的规范 ID（如 `person_alan_turing`）与 Wikidata 已有实体同 ID → 直接合并
2. **`wikidata_id` (QID) 相同** → 合并，依靠全球唯一标识避免同名不同实体误合
3. **(归一化名称, 实体类型)** 同时一致 → 合并；`_normalize_name()` 转小写、去括号、去标点、合并空白
4. **同类型内 `difflib.SequenceMatcher` 近似度 ≥ 0.88** → 合并（处理缩写/多体变体）
5. 均未命中 → 作为新实体加入；**已移除原有过于宽松的子串匹配**以避免 Place vs Person 之类的跨类型误合

对齐后取非空属性的并集，不覆盖已有高质量字段。

**清洗与质量保障：**
- 日期标准化：所有日期转换为 ISO 8601 (`YYYY-MM-DD`)
- **嵌套属性展平** (`_flatten_for_neo4j`)：LLM 可能输出嵌套的 `properties: {...}` 字典；在清洗阶段将其提升到顶层并过滤为 Neo4j 只支持的原语类型（string/int/float/bool 及其数组），以免导入时报 `CypherTypeError`
- 类型验证：实体/关系类型必须在本体定义范围内
- 孤立节点检测：标记无任何边连接的节点
- 统计报告：输出各类型实体/关系的分布统计

### 4. 图数据库存储 (`src/knowledge_storage.py`)

基于 **Neo4j 5** 属性图数据库：

**Schema 设计：**
- 8 种节点标签 (Person, Institution, Publication, Concept, Event, Place, Award, Field)
- 每种标签创建 `id` 字段的唯一性约束 (`CREATE CONSTRAINT ... REQUIRE n.id IS UNIQUE`)
- 为 `name` 字段创建全文索引加速查询

**数据导入策略：**
- 使用 Cypher `UNWIND + MERGE` 实现幂等批量导入（重复运行不产生脏数据）
- 节点：按实体类型分批导入，动态设置节点标签
- 关系：使用 `APOC` 或原生 Cypher 创建有向边并附加属性
- 通过 Neo4j Python Driver (`neo4j>=6.1.0`) 管理连接池和事务

**部署方式：**
- Docker 一键启动：`docker run -d --name turing-neo4j -p 7474:7474 -p 7687:7687 neo4j:5`
- 环境变量配置认证：`NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`

### 5. 知识推理 (`src/knowledge_reasoning.py`)

基于 **Cypher 查询语言**实现的规则推理引擎：

**推理规则（4 条）：**

| # | 规则名称 | 类型 | 模式 | 推导关系 |
|---|---------|------|------|---------|
| 1 | 工作地推理 | 传递性 | `Person─WORKED_AT→Institution─LOCATED_IN→Place` | `Person─WORKED_IN→Place` |
| 2 | 求学地推理 | 传递性 | `Person─EDUCATED_AT→Institution─LOCATED_IN→Place` | `Person─STUDIED_IN→Place` |
| 3 | 合作对称 | 对称性 | `A─COLLABORATED_WITH→B` | `B─COLLABORATED_WITH→A` |
| 4 | 研究领域推导 | 组合 | `Person─AUTHORED→Pub─ABOUT→Field` | `Person─FIELD_OF_WORK→Field` |

- 推理关系使用 `{inferred: true}` 属性标记，可视化中以虚线区分
- 使用 `MERGE` 语义避免重复推理
- **推理结果双路持久化**：推理完成后调用 `export_inferred_relations()` 将所有 `inferred=true` 边导出到 `data/processed/inferred_triples.json`；可视化在 Neo4j 不可用时从该文件加载，仍能在 HTML 中渲染虚线推理边

**示例查询（5 条）：**
- 最短路径查询：图灵 ↔ 任意实体间的最短关系链
- 协作网络：N 跳内的协作者社交图
- 影响力排名：按入度排序的高影响力实体
- 时间线查询：按年份排列的事件/成果序列
- 领域聚合：按学科领域的实体分组统计

### 6. 可视化 (`src/visualization.py`)

基于 **Pyvis**（封装 vis-network.js）生成交互式 HTML：

**布局算法：**
- 物理引擎：**Barnes-Hut** N-body 近似算法
  - 重力强度：-3000 | 中心引力：0.5 | 弹簧长度：120 | 阻尼系数：0.3
- 初始稳定化：300+ 轮迭代自动收敛，完成后关闭物理引擎 → 静态布局

**视觉编码：**

| 实体类型 | 颜色 | 中文标签 |
|----------|------|---------|
| Person | 🔵 `#4A90D9` | 人物 |
| Institution | 🟢 `#2ECC71` | 机构 |
| Publication | 🟣 `#9B59B6` | 出版物 |
| Concept | 🟠 `#E67E22` | 概念 |
| Event | 🔴 `#E74C3C` | 事件 |
| Place | 🌊 `#1ABC9C` | 地点 |
| Award | 🟡 `#F1C40F` | 奖项 |
| Field | ⚪ `#95A5A6` | 学科领域 |

- **节点大小**：基于度数映射 (10–50px)，图灵节点固定 50px 最大
- **关系样式**：每种关系独立配色，推理关系以虚线表示
- **标签**：优先展示中文名，超过 20 字符自动截断

**交互功能：**
- 鼠标悬停：显示 Tooltip（名称 / 中文名 / 类型 / 描述 / 连接数）
- 点击节点：高亮关联子图
- 滚轮缩放 + 拖拽平移
- 左上角固定图例面板（实体类型统计 + 操作提示）

---

## 本体设计

### 实体类型 (8 种)

| 类型 | 说明 | 核心属性 |
|------|------|---------|
| **Person** | 人物 | name, name_zh, birth_date, death_date, nationality, occupation |
| **Institution** | 机构/组织 | name, name_zh, institution_type, location, founded_date |
| **Publication** | 论文/著作 | name, name_zh, year, publication_type, abstract |
| **Concept** | 学术概念/理论 | name, name_zh, field, description |
| **Event** | 历史事件 | name, name_zh, start_date, end_date, location |
| **Place** | 地点 | name, name_zh, country, place_type |
| **Award** | 荣誉/奖项 | name, name_zh, year, awarded_by |
| **Field** | 学科领域 | name, name_zh, description |

所有实体共享：`id` (唯一标识)、`wikidata_id` (Wikidata QID 链接)、`description` (简要描述)

### 关系类型 (17 种)

| 关系 | 说明 | 源→目标 | 附加属性 |
|------|------|---------|---------|
| BORN_IN | 出生于 | Person → Place | — |
| DIED_IN | 去世于 | Person → Place | — |
| EDUCATED_AT | 受教育于 | Person → Institution | degree, year_start, year_end |
| WORKED_AT | 工作于 | Person → Institution | role, year_start, year_end |
| ADVISED_BY | 师从 | Person → Person | — |
| COLLABORATED_WITH | 合作 | Person ↔ Person | 对称关系 |
| AUTHORED | 撰写 | Person → Publication | — |
| CONTRIBUTED_TO | 贡献于 | Person → Concept/Field | — |
| RECEIVED | 获得奖项 | Person → Award | year |
| PARTICIPATED_IN | 参与事件 | Person/Inst → Event | role |
| LOCATED_IN | 位于 | Inst/Place/Event → Place | — |
| RELATED_TO | 亲属关系 | Person → Person | relationship (父/母/兄弟等) |
| INFLUENCED | 影响了 | Person/Concept → Person/Concept/Field | — |
| INFLUENCED_BY | 受影响 | Person/Concept → Person/Concept | — |
| KNOWN_FOR | 以…著名 | Person → Concept/Pub/Event | — |
| PART_OF | 隶属于 | Inst/Place/Concept → Inst/Place/Field | — |
| FIELD_OF_WORK | 研究领域 | Person → Field | — |
| ABOUT | 涉及 | Publication → Concept/Field | — |

---

## 使用方法

### 环境要求

- **Python** ≥ 3.13
- **uv** ([安装指南](https://docs.astral.sh/uv/getting-started/installation/))
- **Docker Desktop**（用于运行 Neo4j，可选——不启动 Neo4j 时可视化仍可从 JSON 加载数据）

### 快速开始

```bash
# 1. 克隆并进入项目
git clone https://github.com/Animnia/Turing_KM.git
cd Turing_KM

# 2. 安装依赖（自动创建虚拟环境）
uv sync

# 3. 配置环境变量
# 编辑 .env 文件，填入 DeepSeek API Key 和 Neo4j 密码

# 4. (可选) 启动 Neo4j 图数据库
scripts\start_neo4j.bat          # Windows
# bash scripts/start_neo4j.sh    # Linux/Mac

# 5. 运行完整流水线
uv run python main.py

# 6. 查看可视化
# 浏览器打开 output/turing_kg.html
```

### 分步执行

```bash
uv run python main.py --step acquisition   # Phase 3: 数据采集
uv run python main.py --step extraction    # Phase 4: 知识抽取
uv run python main.py --step fusion        # Phase 5: 知识融合
uv run python main.py --step storage       # Phase 6: Neo4j 存储 (需 Docker)
uv run python main.py --step reasoning     # Phase 7: 知识推理 (需 Docker)
uv run python main.py --step visualize     # Phase 8: 可视化
```

### 端到端验证

全流程跑完后可运行附带的验证脚本，对 22 项指标（文件/黑名单/对齐/Neo4j/示例查询/HTML）进行端到端检查：

```bash
uv run python scripts/test_e2e.py
```

每个阶段的输出 JSON 保存在 `data/` 目录下，后续阶段自动读取前一阶段的输出。即使跳过 Neo4j 相关步骤，可视化也能直接从 `data/processed/final_triples.json` 加载数据。

### .env 配置示例

```env
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx
DEEPSEEK_BASE_URL=https://api.deepseek.com
NEO4J_URI=neo4j://127.0.0.1:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_neo4j_password
```

---

## 依赖清单

| 包 | 版本 | 用途 |
|----|------|------|
| `neo4j` | ≥ 6.1.0 | Neo4j Python Driver，Bolt 协议连接图数据库 |
| `requests` | ≥ 2.33.1 | HTTP 客户端，调用 Wikidata/Wikipedia API |
| `openai` | ≥ 2.31.0 | OpenAI 兼容 SDK，调用 DeepSeek Chat API |
| `pyvis` | ≥ 0.3.2 | vis-network.js Python 封装，生成交互式 HTML 图谱 |
| `networkx` | ≥ 3.6.1 | 图论计算库，节点度数分析 |
| `python-dotenv` | ≥ 1.2.2 | 从 `.env` 文件加载环境变量 |
| `pandas` | ≥ 3.0.2 | 数据分析（辅助统计） |

---

## 构建产物

| 文件 | 说明 |
|------|------|
| `data/raw/wikidata_turing.json` | Wikidata 原始 SPARQL 查询结果 |
| `data/raw/wikipedia_turing.json` | Wikipedia 章节文本 |
| `data/processed/wikidata_triples.json` | Wikidata 解析后的实体-关系三元组 |
| `data/processed/extracted_triples.json` | DeepSeek LLM 抽取的实体-关系三元组 |
| `data/processed/final_triples.json` | 融合后的最终知识图谱数据 (221 实体 / 202 关系) |
| `data/processed/inferred_triples.json` | 导出的推理关系 (`inferred=true`)，供可视化虚线渲染 |
| `output/turing_kg.html` | 交互式可视化 HTML (可直接用浏览器打开) |
| `pipeline.log` | 完整流水线执行日志 |
