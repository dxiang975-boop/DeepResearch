"""本地文件结构化摘要。

这个模块解决一个 RAG 常见问题：表格、日志、论文 PDF 被切成 chunk 后，
top-k 检索只能召回局部片段，无法保证模型看到完整实验结果或文献结构。

这里会直接读取 RAG_INPUT_PATH 下的 CSV、log、PDF，先生成紧凑的结构化摘要，
再交给 local_rag_node 作为本地证据使用。
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)

LOWER_IS_BETTER_HINTS = ("loss", "error", "rmse", "mae", "mape", "mse", "wer", "perplexity")
HIGHER_IS_BETTER_HINTS = ("acc", "accuracy", "precision", "recall", "f1", "auc", "auroc", "score", "r2")


def _resolve_input_path() -> Path:
    raw = os.getenv("RAG_INPUT_PATH", "knowledge_base").strip() or "knowledge_base"
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (PROJECT_ROOT / path).resolve()


def _collect_paths(root: Path, suffixes: Iterable[str]) -> list[Path]:
    if not root.exists():
        return []
    allowed = {suffix.lower() for suffix in suffixes}
    if root.is_file():
        return [root] if root.suffix.lower() in allowed else []
    paths: list[Path] = []
    for suffix in allowed:
        paths.extend(root.rglob(f"*{suffix}"))
    return sorted(set(paths))


def _compact(value: str, limit: int = 1500) -> str:
    text = re.sub(r"\s+", " ", value).strip()
    return text[:limit] + ("..." if len(text) > limit else "")


def _is_lower_better(name: str) -> bool:
    lower = name.lower()
    return any(hint in lower for hint in LOWER_IS_BETTER_HINTS)


def _is_higher_better(name: str) -> bool:
    lower = name.lower()
    return any(hint in lower for hint in HIGHER_IS_BETTER_HINTS)


def _important_numeric_columns(columns: list[str]) -> list[str]:
    scored: list[tuple[int, str]] = []
    for column in columns:
        lower = column.lower()
        score = 0
        if _is_lower_better(lower) or _is_higher_better(lower):
            score += 3
        if any(word in lower for word in ("val", "test", "eval", "best", "final")):
            score += 2
        if any(word in lower for word in ("epoch", "step", "iter")):
            score += 1
        scored.append((score, column))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [column for _, column in scored[:16]]


def _summarize_csv(path: Path) -> list[dict]:
    try:
        import pandas as pd
    except ImportError:
        return [_error_record(path, "读取 CSV 需要 pandas")]

    try:
        df = pd.read_csv(path)
    except Exception as exc:
        return [_error_record(path, f"CSV 读取失败：{exc}")]

    numeric_df = df.select_dtypes(include="number")
    numeric_columns = _important_numeric_columns(list(numeric_df.columns))
    lines = [
        f"实验结果表：{path.name}",
        f"行数={len(df)}，列数={len(df.columns)}",
        f"列名={', '.join(map(str, df.columns[:30]))}",
    ]
    if not df.empty:
        final_row = df.iloc[-1].to_dict()
        final_pairs = []
        for key in numeric_columns[:10]:
            value = final_row.get(key)
            final_pairs.append(f"{key}={value}")
        if final_pairs:
            lines.append("最后一行指标：" + "; ".join(final_pairs))

    metric_lines = []
    for column in numeric_columns:
        series = numeric_df[column].dropna()
        if series.empty:
            continue
        best_index = series.idxmin() if _is_lower_better(column) else series.idxmax()
        best_value = series.loc[best_index]
        direction = "越低越好" if _is_lower_better(column) else "越高越好"
        metric_lines.append(
            f"{column}: mean={series.mean():.6g}, min={series.min():.6g}, max={series.max():.6g}, "
            f"best={best_value:.6g}@row{best_index}({direction})"
        )
    if metric_lines:
        lines.append("核心数值统计：" + " | ".join(metric_lines[:12]))

    best_rows = []
    for column in numeric_columns[:8]:
        series = numeric_df[column].dropna()
        if series.empty:
            continue
        best_index = series.idxmin() if _is_lower_better(column) else series.idxmax()
        row = df.loc[best_index].to_dict()
        row_summary = []
        for key in list(df.columns)[:8]:
            row_summary.append(f"{key}={row.get(key)}")
        best_rows.append(f"{column}最佳行(row{best_index}): " + ", ".join(row_summary))
    if best_rows:
        lines.append("最佳行摘要：" + " | ".join(best_rows[:6]))

    return [
        {
            "title": f"结构化实验结果摘要：{path.stem}",
            "doc_id": str(path),
            "snippet": _compact("\n".join(lines), 2200),
            "source_type": "local",
            "source_category": "structured_experiment_summary",
            "reliability_hint": "internal",
            "doc_type": "experiment_table",
            "metadata": {"file_name": path.name, "file_suffix": path.suffix.lower(), "row_count": len(df), "column_count": len(df.columns)},
        }
    ]


def _summarize_log(path: Path) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:
        return [_error_record(path, f"log 读取失败：{exc}")]

    metric_values: dict[str, list[float]] = {}
    metric_pattern = re.compile(r"([A-Za-z_][A-Za-z0-9_./-]{1,40})\s*[:=]\s*(-?\d+(?:\.\d+)?(?:e[-+]?\d+)?)", re.I)
    for key, value in metric_pattern.findall(text):
        lowered = key.lower()
        if any(skip in lowered for skip in ("time", "date", "port", "pid", "seed")):
            continue
        metric_values.setdefault(key, []).append(float(value))

    lines = [f"实验日志：{path.name}", f"字符数={len(text)}，行数={text.count(chr(10)) + 1}"]
    metric_lines = []
    for key, values in sorted(metric_values.items())[:30]:
        best = min(values) if _is_lower_better(key) else max(values)
        direction = "越低越好" if _is_lower_better(key) else "越高越好"
        metric_lines.append(f"{key}: count={len(values)}, first={values[0]:.6g}, last={values[-1]:.6g}, best={best:.6g}({direction})")
    if metric_lines:
        lines.append("日志指标统计：" + " | ".join(metric_lines[:18]))

    warning_lines = []
    for raw_line in text.splitlines():
        lower = raw_line.lower()
        if any(word in lower for word in ("error", "warning", "exception", "nan", "overflow", "failed")):
            warning_lines.append(raw_line.strip())
    if warning_lines:
        lines.append("异常/警告线索：" + " | ".join(warning_lines[:8]))

    tail = "\n".join(text.splitlines()[-20:])
    if tail.strip():
        lines.append("日志末尾片段：" + _compact(tail, 700))

    return [
        {
            "title": f"结构化实验日志摘要：{path.stem}",
            "doc_id": str(path),
            "snippet": _compact("\n".join(lines), 2200),
            "source_type": "local",
            "source_category": "structured_experiment_summary",
            "reliability_hint": "internal",
            "doc_type": "experiment_log",
            "metadata": {"file_name": path.name, "file_suffix": path.suffix.lower(), "metric_count": len(metric_values)},
        }
    ]


def _extract_section(text: str, names: tuple[str, ...], limit: int = 1200) -> str:
    lower = text.lower()
    positions = []
    for name in names:
        index = lower.find(name.lower())
        if index >= 0:
            positions.append(index)
    if not positions:
        return ""
    start = min(positions)
    return _compact(text[start : start + limit], limit)


def _summarize_pdf(path: Path) -> list[dict]:
    try:
        from pypdf import PdfReader
    except ImportError:
        return [_error_record(path, "读取 PDF 需要安装 pypdf：python -m pip install pypdf")]

    try:
        reader = PdfReader(str(path))
        page_texts = [(page.extract_text() or "") for page in reader.pages]
    except Exception as exc:
        return [_error_record(path, f"PDF 读取失败：{exc}")]

    full_text = "\n".join(page_texts)
    headings = []
    for line in full_text.splitlines():
        cleaned = line.strip()
        if 4 <= len(cleaned) <= 90 and re.match(r"^(\d+(\.\d+)*\s+|[A-Z][A-Za-z ]{3,}$)", cleaned):
            headings.append(cleaned)
        if len(headings) >= 20:
            break

    abstract = _extract_section(full_text, ("abstract", "摘要"), 1400)
    conclusion = _extract_section(full_text, ("conclusion", "结论", "总结"), 1400)
    method = _extract_section(full_text, ("method", "approach", "方法"), 1000)
    experiment = _extract_section(full_text, ("experiment", "evaluation", "实验", "结果"), 1000)

    lines = [
        f"PDF 文献：{path.name}",
        f"页数={len(page_texts)}，可提取字符数={len(full_text)}",
    ]
    if headings:
        lines.append("疑似章节标题：" + " | ".join(headings[:16]))
    if abstract:
        lines.append("摘要片段：" + abstract)
    if method:
        lines.append("方法片段：" + method)
    if experiment:
        lines.append("实验/评估片段：" + experiment)
    if conclusion:
        lines.append("结论片段：" + conclusion)
    if not any((abstract, method, experiment, conclusion)):
        lines.append("正文开头片段：" + _compact(full_text[:1800], 1800))

    return [
        {
            "title": f"结构化文献摘要：{path.stem}",
            "doc_id": str(path),
            "snippet": _compact("\n".join(lines), 3000),
            "source_type": "local",
            "source_category": "structured_literature_summary",
            "reliability_hint": "internal",
            "doc_type": "paper_or_document",
            "metadata": {"file_name": path.name, "file_suffix": path.suffix.lower(), "page_count": len(page_texts), "char_count": len(full_text)},
        }
    ]


def _summarize_python(path: Path) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:
        return [_error_record(path, f"Python 文件读取失败：{exc}")]

    imports = re.findall(r"^\s*(?:import\s+[\w.]+|from\s+[\w.]+\s+import\s+.+)$", text, flags=re.M)
    functions = re.findall(r"^\s*def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", text, flags=re.M)
    classes = re.findall(r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)\s*[\(:]", text, flags=re.M)
    interesting_lines = []
    keywords = (
        "loss",
        "criterion",
        "optimizer",
        "scheduler",
        "dataloader",
        "dataset",
        "epoch",
        "batch_size",
        "learning_rate",
        "lr",
        "forward",
        "train",
        "eval",
        "contrastive",
        "rank",
        "mse",
        "mae",
        "rmse",
        "pearson",
        "spearman",
        "r2",
    )
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        lower = stripped.lower()
        if stripped and any(keyword in lower for keyword in keywords):
            interesting_lines.append(stripped)
        if len(interesting_lines) >= 80:
            break

    lines = [
        f"Python 模型/训练代码：{path.name}",
        f"字符数={len(text)}，行数={text.count(chr(10)) + 1}",
    ]
    if imports:
        lines.append("主要依赖：" + " | ".join(imports[:20]))
    if classes:
        lines.append("类定义：" + ", ".join(classes[:30]))
    if functions:
        lines.append("函数定义：" + ", ".join(functions[:40]))
    if interesting_lines:
        lines.append("训练/模型/指标相关代码线索：" + " | ".join(interesting_lines[:40]))
    lines.append("文件开头片段：" + _compact(text[:1200], 1200))

    return [
        {
            "title": f"结构化代码摘要：{path.stem}",
            "doc_id": str(path),
            "snippet": _compact("\n".join(lines), 3000),
            "source_type": "local",
            "source_category": "structured_code_summary",
            "reliability_hint": "internal",
            "doc_type": "python_code",
            "metadata": {"file_name": path.name, "file_suffix": path.suffix.lower(), "class_count": len(classes), "function_count": len(functions)},
        }
    ]


def _error_record(path: Path, reason: str) -> dict:
    return {
        "title": f"本地文件结构化摘要失败：{path.name}",
        "doc_id": str(path),
        "snippet": f"文件 {path.name} 未能生成结构化摘要。原因：{reason}",
        "source_type": "local",
        "source_category": "structured_summary_error",
        "reliability_hint": "internal",
        "doc_type": path.suffix.lower().lstrip(".") or "unknown",
        "metadata": {"file_name": path.name, "file_suffix": path.suffix.lower(), "error": reason},
    }


def collect_structured_local_records(query: str, max_files: int = 20) -> list[dict]:
    """根据当前问题读取本地 CSV/log/PDF，并生成结构化证据记录。"""
    root = _resolve_input_path()
    query_lower = query.lower()
    wants_experiment = any(word in query_lower for word in ("实验", "模型", "csv", ".log", "log", "版本", "指标", "baseline", "sota", "accuracy", "loss"))
    wants_literature = any(word in query_lower for word in ("论文", "文献", "pdf", "综述", "paper", "literature", "sota"))
    wants_code = wants_experiment or any(word in query_lower for word in ("代码", ".py", "python", "训练脚本", "模型文件", "train.py", "model.py"))

    suffixes: list[str] = []
    if wants_experiment:
        suffixes.extend([".csv", ".log"])
    if wants_literature:
        suffixes.append(".pdf")
    if wants_code:
        suffixes.append(".py")
    if not suffixes:
        suffixes = [".csv", ".log", ".pdf", ".py"]

    records: list[dict] = []
    for path in _collect_paths(root, suffixes)[:max_files]:
        suffix = path.suffix.lower()
        if suffix == ".csv":
            records.extend(_summarize_csv(path))
        elif suffix == ".log":
            records.extend(_summarize_log(path))
        elif suffix == ".pdf":
            records.extend(_summarize_pdf(path))
        elif suffix == ".py":
            records.extend(_summarize_python(path))
    return records
