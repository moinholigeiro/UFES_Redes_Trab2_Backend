#!/usr/bin/env python3
"""Build the small, fully synthetic and reproducible routing example set."""

from __future__ import annotations

import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "routing_examples.jsonl"

NETWORK_TOPICS = [
    "TCP",
    "UDP",
    "IP",
    "DNS",
    "DHCP",
    "ARP",
    "NAT",
    "máscara de sub-rede",
    "roteamento",
    "OSPF",
    "BGP",
    "Ethernet",
    "Wi-Fi",
    "CSMA/CD",
    "CSMA/CA",
    "controle de congestionamento",
    "slow start",
    "three-way handshake",
    "TLS",
    "HTTP",
    "cache DNS",
    "RTT",
    "MTU",
    "fragmentação IP",
    "ICMP",
    "janela TCP",
    "QUIC",
    "VLAN",
    "switch e roteador",
    "CDN",
]

CLINICAL_TOPICS = [
    "idade do paciente",
    "sexo explicitamente informado",
    "queixa principal",
    "diagnóstico confirmado ou hipótese",
    "negações clínicas",
    "medicamento em uso",
    "dose de medicamento",
    "via de administração",
    "frequência de uso",
    "alergias conhecidas",
    "alergias não documentadas",
    "pressão arterial",
    "frequência cardíaca",
    "temperatura corporal",
    "saturação de oxigênio",
    "unidade de um sinal vital",
    "histórico clínico",
    "sintoma relatado",
    "plano futuro versus tratamento atual",
    "resultado de exame",
    "dado clínico ausente",
    "negação de febre",
    "hipótese de bronquite",
    "medicamentos distintos no mesmo texto",
    "dose e via de administração",
    "frequência de medicação",
    "alergia a dipirona",
    "alergia desconhecida",
    "sinais vitais preservando unidades",
    "extração JSON de prontuário",
]

NETWORK_SIMPLE = [
    "Em uma frase, explique {topic} e sua função em redes de computadores.",
    "Defina {topic} para um estudante iniciante e dê um exemplo curto.",
    "O que significa {topic}? Responda de modo direto para a disciplina de Redes.",
]
NETWORK_COMPLEX = [
    "Analise um cenário de rede que use {topic}. Compare alternativas, explique os trade-offs em latência, confiabilidade e vazão, e proponha métricas para avaliar a solução.",
    "Resolva passo a passo um problema envolvendo {topic}: explicite as hipóteses, os mecanismos de protocolo, os casos de falha e como verificar a resposta com uma captura de pacotes.",
    "Projete uma solução para uma rede congestionada envolvendo {topic}. Compare pelo menos duas abordagens, estime o efeito na fila e justifique os compromissos de desempenho.",
]
CLINICAL_SIMPLE = [
    "Extraia {topic} deste prontuário sintético; use null se não estiver explícito: paciente relata tosse há dois dias e nega febre.",
    "Identifique apenas {topic}, sem inferir dados ausentes, neste texto clínico sintético: uso atual de losartana 50 mg por via oral uma vez ao dia.",
    "Como representar {topic} na extração estruturada? Responda com base neste caso sintético: alergia a dipirona relatada.",
]
CLINICAL_COMPLEX = [
    "Revise uma extração clínica envolvendo {topic}. Preserve negações, hipótese versus confirmação, dose, via, frequência e unidades; explique ambiguidades sem completar lacunas com conhecimento externo.",
    "Compare duas extrações de um prontuário sintético sobre {topic}, detecte associações incorretas entre medicamentos e atributos e proponha validações JSON sem alterar o texto-fonte.",
    "Analise cuidadosamente {topic} em um prontuário sintético longo. Separe informação atual, histórico e plano futuro, preserve incerteza e detalhe como evitar inventar valores ausentes.",
]


def build() -> list[dict[str, str | bool]]:
    rows: list[dict[str, str | bool]] = []
    for domain, topics, simple_templates, complex_templates in (
        ("redes", NETWORK_TOPICS, NETWORK_SIMPLE, NETWORK_COMPLEX),
        ("prontuario", CLINICAL_TOPICS, CLINICAL_SIMPLE, CLINICAL_COMPLEX),
    ):
        for complexity, templates in (("simple", simple_templates), ("complex", complex_templates)):
            for index, topic in enumerate(topics):
                text = templates[index % len(templates)].format(topic=topic)
                rows.append(
                    {
                        "id": f"{domain}-{complexity}-{index + 1:02d}",
                        "text": text,
                        "domain": domain,
                        "complexity": complexity,
                        "synthetic": True,
                        "group": f"{domain}-{index + 1:02d}",
                    }
                )
    random.Random(2026).shuffle(rows)
    return rows


if __name__ == "__main__":
    records = build()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records), encoding="utf-8")
    print(f"wrote {len(records)} synthetic examples to {OUTPUT.relative_to(ROOT)}")
