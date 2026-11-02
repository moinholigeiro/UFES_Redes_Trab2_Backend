"""Semantic domain and task-complexity routing with a fixed, auditable split."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix
from sklearn.pipeline import Pipeline

from .config import DomainConfig, RouterConfig


class RoutingDataError(ValueError):
    pass


class RouteUncertain(Exception):
    def __init__(self, candidates: list[tuple[str, float]]) -> None:
        self.candidates = candidates
        super().__init__("confiança insuficiente para classificar o domínio")


@dataclass(frozen=True)
class RouteDecision:
    requested_domain: str
    domain: str
    domain_confidence: float
    domain_candidates: tuple[tuple[str, float], ...]
    complexity: str
    complexity_confidence: float
    complexity_fallback: bool
    model: str


def _pipeline(seed: int) -> Pipeline:
    return Pipeline(
        [
            (
                "tfidf",
                TfidfVectorizer(
                    lowercase=True,
                    strip_accents="unicode",
                    ngram_range=(1, 2),
                    sublinear_tf=True,
                    max_features=6000,
                ),
            ),
            (
                "classifier",
                LogisticRegression(
                    C=4.0,
                    class_weight="balanced",
                    max_iter=1000,
                    random_state=seed,
                ),
            ),
        ]
    )


def load_examples(path: Path, known_domains: set[str]) -> list[dict[str, str]]:
    examples: list[dict[str, str]] = []
    seen: set[str] = set()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise RoutingDataError(f"conjunto de roteamento não encontrado: {path}") from exc
    for line_number, line in enumerate(lines, 1):
        try:
            raw: dict[str, Any] = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RoutingDataError(f"JSON inválido na linha {line_number}") from exc
        identifier = raw.get("id")
        text = raw.get("text")
        domain = raw.get("domain")
        complexity = raw.get("complexity")
        group = raw.get("group")
        if not isinstance(identifier, str) or not identifier or identifier in seen:
            raise RoutingDataError(f"id ausente ou duplicado na linha {line_number}")
        if not isinstance(text, str) or not text.strip():
            raise RoutingDataError(f"texto ausente na linha {line_number}")
        if domain not in known_domains:
            raise RoutingDataError(f"domínio desconhecido na linha {line_number}: {domain!r}")
        if complexity not in {"simple", "complex"}:
            raise RoutingDataError(f"complexidade inválida na linha {line_number}")
        if raw.get("synthetic") is not True:
            raise RoutingDataError(f"exemplo não marcado como sintético na linha {line_number}")
        if not isinstance(group, str) or not group:
            raise RoutingDataError(f"grupo de split ausente na linha {line_number}")
        seen.add(identifier)
        examples.append(
            {"id": identifier, "text": text, "domain": domain, "complexity": complexity, "group": group}
        )
    if len(examples) < 20:
        raise RoutingDataError("conjunto de roteamento precisa ter pelo menos 20 exemplos")
    counts: dict[str, int] = {}
    for item in examples:
        key = f"{item['domain']}:{item['complexity']}"
        counts[key] = counts.get(key, 0) + 1
    if len(counts) != len(known_domains) * 2 or any(count < 2 for count in counts.values()):
        raise RoutingDataError(
            "cada domínio precisa ter exemplos suficientes nas duas classes de complexidade"
        )
    group_labels: dict[str, set[tuple[str, str]]] = {}
    for item in examples:
        group_labels.setdefault(item["group"], set()).add((item["domain"], item["complexity"]))
    if any(
        len(labels) != 2 or {complexity for _, complexity in labels} != {"simple", "complex"}
        for labels in group_labels.values()
    ):
        raise RoutingDataError("cada grupo deve conter o mesmo tópico com rótulo simple e complex")
    return examples


class SemanticRouter:
    """TF-IDF + regressão logística, treinado somente no conjunto declarado.

    O split estratificado fica congelado pelos parâmetros de config. Qualidade
    nunca é inferida de exemplos fora desse conjunto nem de prontuários do AnonyMED-BR.
    """

    def __init__(
        self,
        examples_file: Path,
        domains: dict[str, DomainConfig],
        config: RouterConfig,
    ) -> None:
        self.domains = domains
        self.config = config
        self.examples = load_examples(examples_file, set(domains))
        texts = np.asarray([item["text"] for item in self.examples], dtype=object)
        domain_labels = np.asarray([item["domain"] for item in self.examples], dtype=object)
        complexity_labels = np.asarray([item["complexity"] for item in self.examples], dtype=object)
        groups = np.asarray([item["group"] for item in self.examples], dtype=object)
        rng = np.random.default_rng(config.random_seed)
        test_groups: set[str] = set()
        for domain in sorted(set(domain_labels.tolist())):
            domain_groups = sorted(set(groups[domain_labels == domain].tolist()))
            rng.shuffle(domain_groups)
            count = max(1, round(len(domain_groups) * config.test_fraction))
            test_groups.update(domain_groups[:count])
        self.test_indices = np.flatnonzero(np.isin(groups, list(test_groups)))
        self.train_indices = np.flatnonzero(~np.isin(groups, list(test_groups)))
        self.domain_model = _pipeline(config.random_seed)
        self.complexity_model = _pipeline(config.random_seed + 1)
        self.domain_model.fit(texts[self.train_indices], domain_labels[self.train_indices])
        self.complexity_model.fit(texts[self.train_indices], complexity_labels[self.train_indices])
        self._evaluation = self._evaluate(texts, domain_labels, complexity_labels)

    def _evaluate(
        self, texts: np.ndarray, domain_labels: np.ndarray, complexity_labels: np.ndarray
    ) -> dict[str, Any]:
        expected_domain = domain_labels[self.test_indices]
        predicted_domain = self.domain_model.predict(texts[self.test_indices])
        expected_complexity = complexity_labels[self.test_indices]
        predicted_complexity = self.complexity_model.predict(texts[self.test_indices])
        domain_classes = sorted(set(domain_labels.tolist()))
        complexity_classes = sorted(set(complexity_labels.tolist()))
        return {
            "examples": len(self.examples),
            "train_examples": len(self.train_indices),
            "test_examples": len(self.test_indices),
            "seed": self.config.random_seed,
            "test_fraction": self.config.test_fraction,
            "domain_accuracy": round(float(accuracy_score(expected_domain, predicted_domain)), 4),
            "domain_labels": domain_classes,
            "domain_confusion_matrix": confusion_matrix(
                expected_domain, predicted_domain, labels=domain_classes
            ).tolist(),
            "complexity_accuracy": round(float(accuracy_score(expected_complexity, predicted_complexity)), 4),
            "complexity_labels": complexity_classes,
            "complexity_confusion_matrix": confusion_matrix(
                expected_complexity, predicted_complexity, labels=complexity_classes
            ).tolist(),
        }

    def evaluation(self) -> dict[str, Any]:
        return dict(self._evaluation)

    @staticmethod
    def _top(probabilities: np.ndarray, classes: np.ndarray, limit: int = 2) -> tuple[tuple[str, float], ...]:
        order = np.argsort(probabilities)[::-1][:limit]
        return tuple((str(classes[i]), round(float(probabilities[i]), 4)) for i in order)

    def route(self, requested_domain: str, text: str) -> RouteDecision:
        if requested_domain == "auto":
            probabilities = self.domain_model.predict_proba([text])[0]
            domain_classes = self.domain_model.named_steps["classifier"].classes_
            candidates = self._top(probabilities, domain_classes)
            domain, confidence = candidates[0]
            if confidence < self.config.confidence_threshold:
                raise RouteUncertain(list(candidates))
        else:
            domain = requested_domain
            if domain not in self.domains:
                raise KeyError(domain)
            confidence = 1.0
            candidates = ((domain, 1.0),)

        complexity_probabilities = self.complexity_model.predict_proba([text])[0]
        complexity_classes = self.complexity_model.named_steps["classifier"].classes_
        complexity_candidates = self._top(complexity_probabilities, complexity_classes, limit=1)
        predicted_complexity, complexity_confidence = complexity_candidates[0]
        fallback = complexity_confidence < self.config.complexity_confidence_threshold
        complexity = "complex" if fallback else predicted_complexity

        domain_config = self.domains[domain]
        model = domain_config.model_by_complexity.get(
            complexity, domain_config.default_model or domain_config.models[0]
        )
        return RouteDecision(
            requested_domain=requested_domain,
            domain=domain,
            domain_confidence=confidence,
            domain_candidates=candidates,
            complexity=complexity,
            complexity_confidence=complexity_confidence,
            complexity_fallback=fallback,
            model=model,
        )
