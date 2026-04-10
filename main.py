"""图灵知识图谱 - 主流程控制脚本

支持分步执行:
    uv run python main.py                    # 执行全部流程
    uv run python main.py --step acquisition # 仅执行数据采集
    uv run python main.py --step extraction  # 仅执行知识抽取
    uv run python main.py --step fusion      # 仅执行知识融合
    uv run python main.py --step storage     # 仅执行知识存储
    uv run python main.py --step reasoning   # 仅执行知识推理
    uv run python main.py --step visualize   # 仅执行可视化
"""

import argparse
import json
import logging
import sys
import time

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("pipeline.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("main")

STEPS = ["acquisition", "extraction", "fusion", "storage", "reasoning", "visualize"]


def run_acquisition():
    """Phase 3: 数据采集"""
    logger.info("=" * 60)
    logger.info("Phase 3: 数据采集 (Data Acquisition)")
    logger.info("=" * 60)

    from src.data_acquisition import fetch_all

    result = fetch_all()
    wiki_sections = result["wikipedia"]["section_count"]
    logger.info("数据采集完成 - Wikipedia: %d 个章节", wiki_sections)
    return result


def run_extraction():
    """Phase 4: 知识抽取"""
    logger.info("=" * 60)
    logger.info("Phase 4: 知识抽取 (Knowledge Extraction)")
    logger.info("=" * 60)

    from src.knowledge_extraction import extract_all

    result = extract_all()
    wd_entities = len(result["wikidata"]["entities"])
    wd_relations = len(result["wikidata"]["relations"])
    ex_entities = len(result["extracted"]["entities"])
    ex_relations = len(result["extracted"]["relations"])
    logger.info(
        "知识抽取完成 - Wikidata: %d实体/%d关系, DeepSeek: %d实体/%d关系",
        wd_entities, wd_relations, ex_entities, ex_relations,
    )
    return result


def run_fusion():
    """Phase 5: 知识融合"""
    logger.info("=" * 60)
    logger.info("Phase 5: 知识融合 (Knowledge Fusion)")
    logger.info("=" * 60)

    from src.knowledge_fusion import fuse_all

    result = fuse_all()
    stats = result["stats"]
    logger.info(
        "知识融合完成 - 实体: %d, 关系: %d, 孤立节点: %d",
        stats["total_entities"], stats["total_relations"], stats["orphan_entities"],
    )
    return result


def run_storage():
    """Phase 6: 知识存储"""
    logger.info("=" * 60)
    logger.info("Phase 6: 知识存储 (Knowledge Storage → Neo4j)")
    logger.info("=" * 60)

    from src.knowledge_storage import store_all

    stats = store_all()
    logger.info(
        "知识存储完成 - Neo4j: %d 节点, %d 关系",
        stats["total_nodes"], stats["total_relationships"],
    )
    return stats


def run_reasoning():
    """Phase 7: 知识推理"""
    logger.info("=" * 60)
    logger.info("Phase 7: 知识推理 (Knowledge Reasoning)")
    logger.info("=" * 60)

    from src.knowledge_reasoning import reason_all

    result = reason_all()
    inferences = result["inferences"]
    total_inferred = sum(inferences.values())
    logger.info("知识推理完成 - 新增推理关系: %d", total_inferred)

    # 打印部分查询结果
    queries = result.get("queries", {})
    direct = queries.get("direct_relations", [])
    logger.info("图灵直接关系示例 (前10):")
    for r in direct[:10]:
        logger.info("  %s → %s (%s)", r.get("relation"), r.get("target_name"), r.get("target_type"))

    return result


def run_visualize():
    """Phase 8: 可视化"""
    logger.info("=" * 60)
    logger.info("Phase 8: 可视化 (Visualization)")
    logger.info("=" * 60)

    from src.visualization import visualize_all

    path = visualize_all()
    logger.info("可视化完成 - 文件: %s", path)
    return path


def run_pipeline(step: str = None):
    """运行知识图谱构建流程"""
    start_time = time.time()

    logger.info("╔════════════════════════════════════════════════════════╗")
    logger.info("║      图灵知识图谱构建流程 (Turing Knowledge Graph)     ║")
    logger.info("╚════════════════════════════════════════════════════════╝")

    if step:
        logger.info("执行单步: %s", step)
    else:
        logger.info("执行完整流程")

    step_functions = {
        "acquisition": run_acquisition,
        "extraction": run_extraction,
        "fusion": run_fusion,
        "storage": run_storage,
        "reasoning": run_reasoning,
        "visualize": run_visualize,
    }

    if step:
        if step not in step_functions:
            logger.error("未知步骤: %s (可选: %s)", step, ", ".join(STEPS))
            sys.exit(1)
        step_functions[step]()
    else:
        for s in STEPS:
            try:
                step_functions[s]()
            except Exception as e:
                logger.error("步骤 '%s' 执行失败: %s", s, e, exc_info=True)
                if s in ("acquisition", "extraction", "fusion"):
                    logger.error("关键步骤失败，终止流程")
                    sys.exit(1)
                else:
                    logger.warning("非关键步骤失败，继续执行...")

    elapsed = time.time() - start_time
    logger.info("=" * 60)
    logger.info("流程完成! 总耗时: %.1f 秒", elapsed)
    logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="图灵知识图谱构建流程",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
步骤说明:
  acquisition  数据采集 (Wikidata SPARQL + Wikipedia API)
  extraction   知识抽取 (Wikidata 解析 + DeepSeek API)
  fusion       知识融合 (实体对齐 + 去重 + 清洗)
  storage      知识存储 (导入 Neo4j)
  reasoning    知识推理 (Cypher 推理规则 + 示例查询)
  visualize    可视化   (Pyvis 交互式 HTML)

示例:
  uv run python main.py                    # 全流程
  uv run python main.py --step acquisition # 仅采集
  uv run python main.py --step visualize   # 仅可视化
        """,
    )
    parser.add_argument(
        "--step",
        choices=STEPS,
        default=None,
        help="指定执行的步骤 (默认: 全部)",
    )

    args = parser.parse_args()
    run_pipeline(args.step)


if __name__ == "__main__":
    main()
