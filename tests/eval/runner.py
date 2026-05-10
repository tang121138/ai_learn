"""评测引擎: 批量运行测试用例 → 收集结果 → 生成报告"""
import time
import sys
import os

# 确保项目根在 path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tests.eval.dataset import EvalDataset, load_dataset, load_all_datasets, list_datasets
from tests.eval.metrics import (
    EvalResult, score_tool_accuracy, score_relevance,
    score_hallucination, score_latency, score_format,
)
from tests.eval.judge import judge_response
from tests.eval.reporter import (
    EvalReport, generate_terminal_report, generate_markdown_report,
    save_snapshot, compare_with_last,
)
from tests.eval.config import SNAPSHOTS_DIR


def run_eval_case(case, agent_service, model_id: str, user_id: str = "eval_user",
                  session_id: str = "eval_session", use_judge: bool = False) -> EvalResult:
    """运行单个评测用例"""
    result = EvalResult(case_id=case.id, category=case.category)
    t0 = time.time()

    try:
        # 调用 Agent (非流式)
        output = agent_service.process_non_streaming(
            session_id, user_id, model_id, case.input,
        )
        # process_non_streaming 是 async，这里同步调用
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            output = loop.run_until_complete(
                agent_service.process_non_streaming(session_id, user_id, model_id, case.input)
            )
        finally:
            loop.close()

        result.latency_ms = (time.time() - t0) * 1000
        result.response = output.get("content", "")
        result.tool_calls = output.get("tool_calls", [])

        # 各维度打分
        result.tool_accuracy = score_tool_accuracy(
            case.expected_tool, case.expected_args, result.tool_calls)
        result.response_relevance = score_relevance(result.response, case.expected_keywords)
        result.no_hallucination = score_hallucination(result.response, case.forbidden_keywords)
        result.latency_score = score_latency(result.latency_ms, case.max_latency_ms)
        result.format_valid = score_format(result.response)

        # LLM-as-Judge (可选)
        if use_judge:
            expectation = ", ".join(case.expected_keywords) if case.expected_keywords else "准确回答"
            judge_result = judge_response(case.input, result.response, expectation)
            result.response_relevance = (result.response_relevance + judge_result["score"]) / 2
            result.judge_notes = judge_result.get("reasoning", "")

        # 汇总错误
        if result.tool_accuracy < 0.5:
            result.errors.append(f"工具准确率低 ({result.tool_accuracy:.0%})")
        if result.response_relevance < 0.5:
            result.errors.append(f"相关性低 ({result.response_relevance:.0%})")
        if result.no_hallucination < 0.5:
            result.errors.append(f"疑似幻觉 ({result.no_hallucination:.0%})")

        result.passed = result.weighted_score >= 0.6

    except Exception as e:
        result.latency_ms = (time.time() - t0) * 1000
        result.errors.append(f"异常: {str(e)}")
        result.passed = False

    return result


def run_standalone(dataset_name: str, model_id: str = "Qwen/Qwen3-30B-A3B",
                   use_judge: bool = False, output_md: str | None = None,
                   compare_last: bool = False):
    """
    独立评测入口 — 不依赖 FastAPI TestClient。
    直接构造 AgentService，用固定的 user_id/session_id 跑评测。
    适合快速验证，不需要真实数据库和用户。
    """
    from backend.services.agent_service import AgentService

    agent = AgentService()
    dataset = load_dataset(dataset_name)
    errors = dataset.validate()
    if errors:
        print("数据集校验失败:")
        for e in errors:
            print(f"  - {e}")
        return

    print(f"评测数据集: {dataset.name} ({len(dataset)} 条, 模型: {model_id})")
    print(f"{'─' * 50}")

    report = EvalReport(dataset_name=dataset.name, model_id=model_id)

    import asyncio
    for i, case in enumerate(dataset.cases):
        print(f"[{i+1}/{len(dataset)}] {case.id} ", end="", flush=True)

        result = EvalResult(case_id=case.id, category=case.category)
        t0 = time.time()

        try:
            loop = asyncio.new_event_loop()
            try:
                output = loop.run_until_complete(
                    agent.process_non_streaming(
                        "eval_session", "eval_user", model_id, case.input
                    )
                )
            finally:
                loop.close()

            result.latency_ms = (time.time() - t0) * 1000
            result.response = output.get("content", "")
            result.tool_calls = output.get("tool_calls", [])

            result.tool_accuracy = score_tool_accuracy(
                case.expected_tool, case.expected_args, result.tool_calls)
            result.response_relevance = score_relevance(result.response, case.expected_keywords)
            result.no_hallucination = score_hallucination(result.response, case.forbidden_keywords)
            result.latency_score = score_latency(result.latency_ms, case.max_latency_ms)
            result.format_valid = score_format(result.response)

            if use_judge:
                expectation = ", ".join(case.expected_keywords) if case.expected_keywords else "准确回答"
                judge_result = judge_response(case.input, result.response, expectation)
                result.response_relevance = (result.response_relevance + judge_result["score"]) / 2
                result.judge_notes = judge_result.get("reasoning", "")

            if result.tool_accuracy < 0.5:
                result.errors.append(f"工具准确率低 ({result.tool_accuracy:.0%})")
            if result.response_relevance < 0.5:
                result.errors.append(f"相关性低 ({result.response_relevance:.0%})")
            if result.no_hallucination < 0.5:
                result.errors.append(f"疑似幻觉 ({result.no_hallucination:.0%})")

            result.passed = result.weighted_score >= 0.6
            status = "✓" if result.passed else "✗"
            print(f"{status} score={result.weighted_score:.2f} latency={result.latency_ms:.0f}ms")

        except Exception as e:
            result.latency_ms = (time.time() - t0) * 1000
            result.errors.append(f"异常: {str(e)}")
            print(f"✗ ERROR: {e}")

        report.results.append(result)
        time.sleep(0.5)  # 避免 API 限流

    report.compute()

    # 输出报告
    term_report = generate_terminal_report(report)
    print(term_report)

    # 保存快照
    snapshot_path = save_snapshot(report)
    print(f"快照已保存: {snapshot_path}")

    # 回归检测
    if compare_last:
        compare_result = compare_with_last(report)
        print(compare_result)

    # Markdown 输出
    if output_md:
        md = generate_markdown_report(report)
        with open(output_md, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"Markdown 报告: {output_md}")

    return report


# ── CLI 入口 ──

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Agent 评测管线")
    parser.add_argument("--dataset", default="all",
                        help="数据集名称 (tool_calling, safety, multimodal, all)")
    parser.add_argument("--model", default="Qwen/Qwen3-30B-A3B", help="被评测模型 ID")
    parser.add_argument("--judge", action="store_true", help="启用 LLM-as-Judge")
    parser.add_argument("--output", help="Markdown 报告输出路径")
    parser.add_argument("--compare-last", action="store_true", help="与上次快照对比")
    args = parser.parse_args()

    if args.dataset == "all":
        for name in list_datasets():
            run_standalone(name.replace(".json", ""), args.model, args.judge, args.output, args.compare_last)
    else:
        run_standalone(args.dataset, args.model, args.judge, args.output, args.compare_last)


if __name__ == "__main__":
    main()
