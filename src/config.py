"""配置管理模块 - 从 .env 加载项目配置"""

import os
from pathlib import Path
from dotenv import load_dotenv

# 项目根目录
ROOT_DIR = Path(__file__).resolve().parent.parent

# 加载 .env
load_dotenv(ROOT_DIR / ".env")

# DeepSeek API 配置
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = "deepseek-chat"

# Neo4j 配置
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "turing2026")

# 数据路径
DATA_RAW_DIR = ROOT_DIR / "data" / "raw"
DATA_PROCESSED_DIR = ROOT_DIR / "data" / "processed"
OUTPUT_DIR = ROOT_DIR / "output"

# 确保目录存在
for d in [DATA_RAW_DIR, DATA_PROCESSED_DIR, OUTPUT_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Wikidata
WIKIDATA_SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
TURING_WIKIDATA_QID = "Q7251"

# Wikipedia
WIKIPEDIA_API_URL = "https://en.wikipedia.org/w/api.php"
TURING_WIKIPEDIA_TITLE = "Alan_Turing"
