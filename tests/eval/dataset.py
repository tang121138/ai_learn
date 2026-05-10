"""评测数据集加载 + 校验"""
import json
import os
from dataclasses import dataclass, field
from tests.eval.config import DATASETS_DIR


@dataclass
class EvalCase:
    id: str
    category: str
    input: str
    expected_tool: str | None = None
    expected_args: dict = field(default_factory=dict)
    expected_keywords: list[str] = field(default_factory=list)
    forbidden_keywords: list[str] = field(default_factory=list)
    min_response_length: int = 10
    max_latency_ms: int = 15000

    @classmethod
    def from_dict(cls, d: dict) -> "EvalCase":
        return cls(
            id=d.get("id", "?"),
            category=d.get("category", "general"),
            input=d.get("input", ""),
            expected_tool=d.get("expected_tool"),
            expected_args=d.get("expected_args", {}),
            expected_keywords=d.get("expected_keywords", []),
            forbidden_keywords=d.get("forbidden_keywords", []),
            min_response_length=d.get("min_response_length", 10),
            max_latency_ms=d.get("max_latency_ms", 15000),
        )


@dataclass
class EvalDataset:
    name: str
    version: str
    cases: list[EvalCase]

    @classmethod
    def load(cls, path: str) -> "EvalDataset":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        cases = [EvalCase.from_dict(c) for c in data.get("cases", [])]
        return cls(
            name=data.get("name", os.path.basename(path)),
            version=data.get("version", "unknown"),
            cases=cases,
        )

    def validate(self) -> list[str]:
        errors = []
        ids = set()
        for c in self.cases:
            if not c.id:
                errors.append("存在空 ID 的用例")
            elif c.id in ids:
                errors.append(f"ID 重复: {c.id}")
            ids.add(c.id)
            if not c.input.strip():
                errors.append(f"[{c.id}] input 为空")
            if c.min_response_length < 0:
                errors.append(f"[{c.id}] min_response_length 为负")
        return errors

    def __len__(self) -> int:
        return len(self.cases)


def list_datasets() -> list[str]:
    return sorted(
        f for f in os.listdir(DATASETS_DIR)
        if f.endswith(".json")
    )


def load_dataset(name: str) -> EvalDataset:
    if not name.endswith(".json"):
        name = name + ".json"
    path = os.path.join(DATASETS_DIR, name)
    if not os.path.exists(path):
        raise FileNotFoundError(f"数据集不存在: {path}")
    return EvalDataset.load(path)


def load_all_datasets() -> list[EvalDataset]:
    return [load_dataset(f) for f in list_datasets()]
