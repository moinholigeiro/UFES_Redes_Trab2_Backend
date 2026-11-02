# Projeto 1 — Plano completo e instruções para implementação

## 1. Leia isto primeiro

Este documento consolida as decisões do usuário, a situação dos arquivos existentes e um plano executável. Foi escrito para permitir que outro agente trabalhe sem precisar recuperar a conversa inteira. **É uma especificação de trabalho, não evidência de funcionalidades implementadas.**

- Disciplina: **Redes de Computadores**, UFES, professor Magnos Martinello.
- Fonte normativa: `Propostas de Trabalho.md`, especialmente Projeto 1, funcionamento dos projetos e avaliação. Em conflito, prevalecem o enunciado e esclarecimentos do professor.
- Trabalho: gateway distribuído de LLMs de pesos abertos, com inferência local e streaming.
- Grupo: **três integrantes**. O usuário informou que o professor autorizou o trio para este trabalho mais elaborado. Não pedir novamente essa decisão; registrar a autorização no contexto da entrega, pois o texto original menciona individual/dupla.
- Incrementos escolhidos: **um em cada trilha** — Desempenho, Segurança e Inteligência.
- Linguagem preferida: **Python**. O runtime `llama.cpp` pode ser uma dependência externa em C++; não reimplementar inferência.
- Hardware-alvo conhecido: **Ubuntu, aproximadamente 8 GB de RAM e 4 núcleos, sem GPU**. Não exigir detalhes adicionais para começar. Quantidades de máquinas adicionais são desconhecidas.
- Preparar migração por configuração para GPU com aproximadamente 16 GB de VRAM, sem depender dela para entregar.
- Carga experimental: **modo fechado**, confirmado pelo usuário; cada cliente espera a resposta antes da próxima requisição.
- Uso acadêmico/não comercial. Isso não dispensa licenças, atribuição e restrições de redistribuição.
- Não há cronograma com datas: organizar por dependências e marcos M1/M2/M3.

**Prioridade:** serviço de rede, filas, transporte, concorrência, medidas e experimentos. A extração clínica é o caso de uso, não um projeto de treinamento de IA nem um sistema de diagnóstico.

## 2. Estado atual e preservação de arquivos

Existem `README.md`, o enunciado e dados em `data/anonymedbr/`. O README informa que gateway, nós e experimentos ainda não foram implementados. Antes de editar, confira o estado real: outro agente pode ter acrescentado código depois deste documento.

### Dados canônicos disponíveis

Diretório: `data/anonymedbr/processed/reviewed/`.

| Arquivo | Função |
| --- | --- |
| `source_records.jsonl` | 500 textos-fonte sintéticos; chaves `id`, `text`, `labels`, `synthetic` |
| `records.jsonl` | 500 anotações clínicas preliminares produzidas/revisadas por LLM |
| `manifest.json` | Convenções, revisão da fonte e checksums |
| `provenance.json` | Associação entre IDs, lotes e arquivos de revisão |
| `README.md` | Limitações e regras de interpretação |

- Fonte: `Venturus/AnonyMED-BR`, revisão `dbebda9cd1812e66a97e41e34394410d227e87ef`.
- IDs-fonte da consolidação: **875–1374**, do split de treino da fonte, sintéticos.
- Parear **por ID**, validando `annotation.source.source_record_id == source.id`; a ordem coincide, mas não depender apenas dela.
- Anotações possuem idade, sexo, queixa principal, diagnósticos, medicamentos, alergias, sinais vitais, evidências e metadados.
- Sinais vitais são **strings ou null**, preservando unidades, intervalos e detalhes como PAM.
- `alergias: null` significa desconhecido/não documentado. `[]` nos dados não deve ser interpretado automaticamente como negação de alergias.
- `evidencias` contém `{campo, localizacao, resumo}`; são paráfrases, não spans exatos.
- Relatórios em `audits/` registram problemas e correções. Arquivos `wrong-source` e `audits/archived/` **não são versões canônicas** e não devem ser misturados ao conjunto consolidado.
- Não apagar, reanotar nem sobrescrever esses arquivos como efeito colateral da implementação. Produzir splits, transformações e previsões em novos caminhos.

### Estatísticas observadas nesta revisão

Foram lidos os JSONLs com Python, sem modificar arquivos:

- 500 fontes e 500 anotações; todas as anotações têm status `independently_reviewed_against_source`.
- Textos: mínimo 537, média aproximada 1.954 e máximo 4.170 caracteres. **Caracteres não são tokens.**
- Idade não nula: 499; sexo não nulo: 44; queixa não nula: 468.
- Diagnósticos não vazios: 377; medicamentos não vazios: 395.
- PA presente: 190; FC: 233; temperatura: 87; SpO2: 130.
- Estas estatísticas descrevem **anotações**, não comprovam correção clínica nem representatividade.

### Limites de licença e avaliação

A licença verificável de reutilização/redistribuição do dataset continua pendente nos metadados locais. Não afirmar que basta dar créditos. Não publicar fontes, anotações ou derivados até esclarecer permissões. Não enviar novos dados para APIs externas sem decisão explícita do usuário e verificação dos termos.

As anotações e as revisões foram feitas por GPT-6 Luna; revisão por outro agente do mesmo modelo não constitui adjudicação humana independente. Usar o conjunto como **referência preliminar gerada por LLM**. A avaliação principal de extração deve usar uma amostra revisada por pessoas contra o texto. Não avaliar veracidade médica dos cenários: avaliar fidelidade da extração.

## 3. Requisitos que não podem desaparecer do plano

### Núcleo obrigatório — M1

1. Cliente → gateway → nós por protocolo documentado, com saída progressiva de tokens/deltas, não resposta integral acumulada.
2. Pelo menos **dois domínios**, com **modelos distintos**, prompts de sistema e parâmetros próprios, selecionados pelo domínio declarado na requisição. A interpretação conservadora evita depender de aceitação de um único modelo compartilhado.
3. Fila por nó com limite de concorrência e vários clientes atendidos simultaneamente.
4. TTFT, tokens/s, latência fim a fim e vazão instrumentados.

### Incrementos — M2

- **Desempenho:** balanceamento entre pelo menos dois nós elegíveis para o mesmo domínio/modelo; comparar round-robin, menor fila e menor latência observada. Demonstrar a queda de nó durante streaming e documentar o destino das requisições.
- **Segurança:** autenticação por token **mais autorização por domínio, rate limiting por usuário e TLS**. Os quatro integram o incremento escolhido.
- **Inteligência:** roteamento semântico de domínio e escolha entre modelo pequeno/maior para solicitações simples/difíceis. Não reduzir silenciosamente à escolha manual de domínio.

### Experimento e entrega — M3

- Clientes simultâneos **1, 2, 4, 8, 16**; TTFT e vazão agregada em tokens/s.
- Hipótese e previsão do comportamento da fila **antes** da medição principal.
- Repetições, gráficos e comparação previsão × medição.
- Responder com dados próprios: importância de TTFT versus tokens/s e efeito de FIFO versus prioridade para respostas curtas na saturação.
- Relatório até **6 páginas**, README reproduzível, código organizado e demonstração. M1 tem demo de cinco minutos; M2 inclui roteiro experimental.
- Pesos: núcleo 30%, incrementos 25%, experimento 25%, pergunta-desafio 10%, código/README/apresentação 10%. Integração com outros projetos é bônus opcional.

## 4. Reutilização open source: o que adotar e o que evitar

Fontes consultadas diretamente nos READMEs dos repositórios:

### KatherLab/LLMAIx

https://github.com/KatherLab/LLMAIx — AGPL-3.0.

Extrai JSON de documentos médicos usando modelos locais, JSON Schema/gramática GBNF, ajuda na revisão de anotações e oferece avaliação/exportação tabular. É a referência mais próxima do caso de uso. Possui execução CPU/CUDA e usa `llama-server`.

**Uso planejado:** estudar geração restrita, esquemas e revisão/avaliação; opcionalmente executar uma comparação offline. Não colocar a aplicação inteira no caminho obrigatório: OCR, interface e processamento em lote não são necessários para textos já existentes. Sua configuração padrão consultada usa Gemma 4 E4B, download de aproximadamente 5 GB e contexto grande; não copiar essa configuração para 8 GB de RAM.

### KatherLab/llmaixweb

https://github.com/KatherLab/llmaixweb — AGPL-3.0.

Fluxo documento → schema/prompt → extração → avaliação por campo, via APIs compatíveis com OpenAI. Usa FastAPI, Pydantic, banco de dados, Celery e frontend Vue.

**Uso planejado:** referência de contrato/evaluation, não plataforma-base. Banco, frontend e Celery acrescentariam infraestrutura desnecessária.

### google/langextract

https://github.com/google/langextract — Apache-2.0; README também aponta termos Health AI para aplicações de saúde, a verificar para uso efetivo.

Biblioteca Python com extração de entidades e associação ao texto-fonte, exemplos de medicamentos, Ollama e outros provedores. O README consultado alerta que a integração Ollama da biblioteca não oferece o mesmo suporte ao `output_schema` arbitrário. Não confundir isso com incapacidade geral da API Ollama.

**Uso planejado:** considerar como baseline offline opcional de extração rastreável. Não presumir que `lx.extract()` entrega SSE token a token nem que produz diretamente nosso schema. Múltiplas passagens/chunks podem multiplicar o custo em CPU.

### Decisão de arquitetura

Implementar um extrator pequeno em Python com Pydantic/JSON Schema e uma chamada local de inferência, inspirado nas abordagens acima. **Não há necessidade de integrar três frameworks.** Usar llama.cpp como motor; gateway, filas, segurança, cliente e avaliação são trabalho do grupo.

Se copiar/adaptar código AGPL, preservar avisos e avaliar obrigações da licença, inclusive disponibilização de código em serviço de rede. Citação do artigo não substitui licença. Registrar claramente biblioteca usada, código adaptado e referência apenas conceitual.

## 5. Modelos e orçamento de recursos

### Candidatos, não escolhas validadas

O usuário aceitou considerar Qwen3.5 4B, Gemma 4 E4B, Qwen3 1.7B e Qwen3.5 9B para GPU. Não há benchmark local que justifique tratá-los como vencedores.

1. **Modelo pequeno inicial:** Qwen3 1.7B, GGUF Q4, sem raciocínio quando suportado.
2. **Modelo maior candidato:** Qwen3.5 4B Q4, condicionado a suporte real do runtime, memória e qualidade. Fallback: Qwen3 4B ou Qwen2.5 3B Instruct, conforme teste.
3. **Gemma 4 E4B:** comparação opcional; não tratar como arquivo de 3 GB. O repositório LLMAIx consultado menciona aproximadamente 5 GB para seu modelo padrão.
4. **Qwen3.5 9B:** opção futura em GPU, sem obrigação de testar agora.

Para cada modelo usado registrar ID oficial, licença/model card, origem do GGUF, nome/hash do arquivo, quantização, template e revisão do runtime. Verificar fontes primárias antes de repetir alegações de licença ou arquitetura das conversas anteriores.

### Configuração inicial CPU

- Um processo do runtime por réplica e **um slot ativo por nó** inicialmente.
- Contexto inicial 2.048 ou 4.096 tokens, decidido após tokenizar prompt + documento + reserva de saída.
- Threads configuráveis, começar com até quatro para um único runtime; reduzir por processo quando compartilhar máquina.
- Não carregar modelos dentro de múltiplos workers Uvicorn: isso duplica memória.
- Medir RAM real do sistema, RSS/PSS quando útil, swap, tokens/s e tempo de prefill. Tamanho do GGUF não é consumo total.
- Priorizar estabilidade sem swap; se o conjunto de modelos não couber, usar candidatos menores antes de reduzir quantização indiscriminadamente.
- Não prometer latência mínima nem vazão antes de medir. CPU lenta é um resultado válido para filas.

### Topologia e limite do que podemos demonstrar

**Perfil mínimo:** gateway e dois endpoints locais, um com modelo pequeno de Redes e outro com modelo maior de prontuários. Essa topologia cumpre dois domínios, mas **não basta para comparar balanceamento no mesmo domínio**.

**Perfil de desempenho:** pelo menos duas réplicas com a mesma configuração de domínio/modelo. Preferência: nós em hosts diferentes, se disponíveis. Alternativa: dois runtimes pequenos no mesmo Ubuntu, em portas distintas e com recursos controlados; o domínio médico pode apontar para esse modelo pequeno durante o experimento, mantendo o segundo domínio/modelo disponível.

Nesse perfil, não afirmar ganho de capacidade física ou distribuição entre computadores: réplicas compartilham CPU/RAM. O sistema deve aceitar URLs remotas para migrar sem refatoração. Se nem o perfil de réplicas pequenas couber, comunicar bloqueio do incremento; não apresentar nó fictício como inferência real.

**Testes:** um backend simulado leve permite testar SSE, filas e falhas sem pesos, mas seus resultados não substituem medições obrigatórias com LLM real.

## 6. Arquitetura proposta

```text
Cliente Python / curl / carga fechada
          | HTTPS + POST + SSE
          v
Gateway FastAPI (async, processo único inicial)
  autenticação -> rate limit -> autorização -> resolução de domínio/modelo
  -> seleção de nó -> fila limitada por nó -> HTTP streaming
          | HTTP/SSE na rede interna controlada
          v
Nós de inferência locais/remotos (llama-server)
          |
          v
GGUF quantizado + schema de geração do domínio médico
```

TLS interno também deve ser configurável se os nós estiverem em rede não confiável. Não expor APIs de inferência sem controle na Internet. O gateway nunca envia prontuários a serviços externos para completar solicitações.

### Fila e concorrência

- **Um único proprietário lógico da fila:** o gateway mantém uma fila explícita, limitada, para cada nó.
- Dispatcher por nó respeita `max_inflight`; começa em 1, configurável. Configuração do runtime deve ser compatível para evitar fila oculta adicional.
- Semáforo sozinho não é uma fila FIFO/prioritária auditável. Usar estrutura de jobs, contador de ordem e dispatcher.
- Job guarda request ID, domínio, configuração, deadline, estado, instante de entrada e estimativa de custo.
- Reservar capacidade/posição atomicamente ao selecionar o nó. Balancear usando jobs pendentes **e ativos**, evitando corrida entre requisições.
- Em nó indisponível, retirar da elegibilidade; limitar retries e não aguardar para sempre.
- Fila cheia retorna 503, distinguindo sobrecarga de rate limit 429.
- Cancelamento do cliente remove job pendente ou cancela a chamada ativa quando possível, libera capacidade e registra trabalho desperdiçado.
- Buffer de saída por cliente é limitado; backpressure não pode acumular tokens ilimitados na RAM. Definir timeout de cliente lento.
- Manter o gateway com um worker enquanto filas e rate limit forem em memória; múltiplos workers exigiriam estado compartilhado e não são escopo inicial.

## 7. Protocolo e semântica de streaming

Endpoint proposto: `POST /v1/generate`, `Authorization: Bearer <token>` e `Accept: text/event-stream`.

Requisição clínica mínima:

```json
{"domain":"prontuario","input":"texto do prontuário","max_output_tokens":768}
```

O valor 768 é ilustrativo/configurável, não um tamanho garantido. Endpoints de chat podem aceitar `messages`; o primeiro contrato deve escolher e documentar uma forma única por domínio. Não permitir que cliente sobrescreva o prompt de sistema, modelo arbitrário ou schema obrigatório.

- `domain=prontuario` e `domain=redes`: roteamento explícito obrigatório.
- `domain=auto`: incremento opcional, sem mudar a semântica dos domínios explícitos.
- IDs, modelo resolvido, hash do prompt, schema e política aparecem nos metadados, não nos dados clínicos gerados.

Eventos:

| Evento | Conteúdo / interpretação |
| --- | --- |
| `meta` | request ID, domínio/modelo/nó e versão do schema |
| `delta` | sequência e trecho textual gerado, encaminhado imediatamente |
| `result` | somente para extração: JSON completo validado ao fim |
| `done` | finish reason e contagem de tokens quando fornecida pelo backend |
| `error` | código, se houve saída parcial e possibilidade de repetir |

Heartbeats SSE são comentários, não tokens. `meta`, heartbeat ou abertura da conexão **não contam como primeiro token**.

Um delta não é necessariamente um token do tokenizer: bytes UTF-8 e implementação do runtime podem agrupar/separar trechos. Nunca usar quantidade de eventos SSE como quantidade de tokens. Preservar fluxo de decodificação, não fazer buffer para formar palavras ou JSON completo.

### JSON progressivo

Durante geração, fragmentos do JSON podem ser inválidos/incompletos. Cliente mostra preview como não validado; só exporta após `result` e conclusão válida. Geração restrita reduz erros estruturais, mas limite de tokens, timeout e falha ainda podem deixar JSON truncado.

Não adicionar correção automática silenciosa por uma segunda chamada: muda serviço, custos e TTFT. Se houver modo de reparo futuro, identificá-lo e medi-lo separadamente.

### Failover seguro

- Antes do primeiro delta: até um retry em outra réplica **compatível**, preservando request ID e registrando tentativa; TTFT cliente inclui todo o atraso.
- Depois do primeiro delta: emitir `error` com `partial=true` e encerrar; não emitir `result` válido nem concatenar geração de outro nó.
- Retry do cliente inicia **nova resposta**. Não garantir retomada a partir do prefixo, nem equivalência mesmo com temperatura zero.
- Demonstrar falha mid-stream é parte da entrega: erro explícito e estado parcial são comportamento escolhido, não omissão do teste.
- Distinguir EOF sem `done` de término bem-sucedido; health check e timeout não autorizam duplicação concorrente de uma requisição ainda ativa.

## 8. Extração clínica e exportação

### Contrato de dados v1

Schema simples inspirado na consolidação, com `additionalProperties=false` onde suportado pelo runtime:

- `idade`: inteiro ou null, apenas quando explicitamente informado para o paciente.
- `sexo`: categoria documentada ou null; não inferir por nome/pronomes.
- `queixa_principal`: texto curto ou null; explicitar que acompanhamento pode não ser uma queixa.
- `diagnosticos`: lista de textos; preservar negação, hipótese e histórico em vez de converter em diagnóstico confirmado.
- `medicamentos`: lista de objetos com `nome`, `dose`, `via`, `frequencia`, strings/null; não atribuir dose de um medicamento a outro nem converter plano em uso atual sem qualificação.
- `alergias`: lista ou null, com regra explícita de desconhecido versus negação documentada. A referência antiga precisa de adjudicação para resolver ambiguidades.
- `sinais_vitais`: `pa`, `fc`, `temp_c`, `spo2`, strings/null, sem alterações silenciosas de unidade.

Metadados `id`, `source`, versão do modelo e métricas são montados pelo Python, não alucinados pelo LLM. Não exigir que o modelo gere `review_status`.

Evidências completas ficam como saída opcional para revisão offline; não obrigar longas paráfrases em cada resposta de carga. Se usar spans posteriormente, acrescentar versão de schema: as evidências atuais não têm offsets precisos.

### Regras de prompt

- Extração, não diagnóstico, recomendação ou preenchimento por conhecimento externo.
- Documento delimitado e tratado como dados não confiáveis, não como instruções de sistema.
- Não adicionar nomes, telefones, endereços ou identificadores pessoais ao schema solicitado.
- Informação não mencionada é desconhecida. Distinguir negação de ausência.
- Exemplos few-shot apenas do conjunto de desenvolvimento, no máximo um ou dois curtos inicialmente.
- Validar JSON e fidelidade são coisas distintas. Não anunciar 100% de correção por usar gramática.

### Exportação

1. **JSON** por prontuário e **JSONL** para lote são formatos canônicos.
2. CSV por tabela: pacientes, diagnósticos, medicamentos e sinais vitais, relacionados por request/source ID. Não juntar arrays com vírgulas de forma ambígua.
3. Python faz exportação determinística após validar; o LLM não gera CSV nem FHIR diretamente.
4. FHIR, CID, SNOMED, OCR/PDF, diagnósticos automáticos e integração hospitalar ficam fora do MVP. Se houver FHIR futuro, usar mapeamento e validação explícitos, não afirmar conformidade com simples JSON.
5. Lote de 500 é cliente offline que usa a mesma API do gateway, com retomada por ID, checkpoint e limites de concorrência; não criar um caminho que bypassa filas para medir o serviço.

## 9. Inteligência: domínio e complexidade

- Classificador inicial leve: TF-IDF + regressão logística/scikit-learn para domínio, treinado com exemplos de Redes e textos/solicitações clínicas.
- Preparar conjunto misto separado de treino e teste; 60 exemplos total é pequeno. Objetivo inicial: aproximadamente 120 exemplos, com teste reservado e classes equilibradas; reduzir se necessário, reportando incerteza.
- Exemplos de Redes não existem nos 500 prontuários; devem ser preparados à parte.
- `auto` calcula domínio e confiança; abaixo de limiar solicita domínio explícito, sem enviar para qualquer modelo ao acaso.
- Autorização verifica o domínio **resolvido**, impedindo que `auto` burle restrições. Texto do documento não concede permissão.
- Segundo estágio escolhe pequeno/maior por complexidade prevista. Começar com critérios transparentes (tamanho tokenizado, tipo de tarefa e rótulos de complexidade), e validar a associação em exemplos com gabarito/rubrica.
- O modelo pequeno deve poder atender ambos os domínios; nó/capabilidade declara combinações modelo+domínio. Para extração, o schema segue obrigatório mesmo no modelo pequeno.
- Em teste: acurácia de domínio, matriz de confusão, fallback, overhead do classificador, qualidade/custo de pequeno versus maior e política de escolha. Não apresentar regra de tamanho isolada como classificador semântico completo.
- Experimento obrigatório principal desliga `auto` para não misturar distribuição de serviço variável; avaliação do incremento acontece em rodada separada.

## 10. Segurança mínima completa

- Tokens opacos de alta entropia, provisionados por comando local; hash armazenado e comparação apropriada, sem logar segredo. JWT/SSO não são necessários.
- Cada usuário possui domínios permitidos e limites; não autenticar apenas no nó.
- Token bucket por usuário com parâmetros documentados; 429 + Retry-After; contas de carga autorizadas com limite alto para não contaminar experimento de filas.
- Limites de corpo, saída, fila, deadline e cliente lento, além de rate limit de requisições.
- TLS no gateway com Uvicorn ou proxy simples; CA local com SAN correto e confiança instalada no cliente. Nunca usar `verify=False` como evidência de TLS correto.
- Credenciais fora do versionamento; logs e métricas não contêm corpo do prontuário, token ou prompt integral.
- `/health` sem dados sensíveis; `/metrics` e endpoints administrativos protegidos/restritos.
- Testes: 401 sem/errado token, 403 sem domínio, 429 excesso, sucesso autorizado, recusa de certificado não confiável, conexão com CA válida e captura de tráfego cifrado.
- Prompt injection não é o incremento selecionado, mas limites de saída, schema e separação de papéis são higiene básica. Não prometer imunidade.

## 11. Métricas: definições antes da implementação

Usar relógio monotônico dentro de cada processo. Não subtrair timestamps absolutos de máquinas diferentes como se fossem sincronizados.

| Métrica | Definição |
| --- | --- |
| TTFT cliente | Do envio da solicitação até primeiro delta não vazio recebido |
| TTFT gateway | Recepção da requisição até primeiro delta observado do backend |
| Espera em fila | Enqueue → dispatch, no gateway |
| Serviço | Dispatch → conclusão/cancelamento, no gateway |
| Latência fim a fim | Envio do cliente → conclusão final validada ou erro |
| Velocidade por solicitação | Tokens gerados divididos pelo intervalo de geração; documentar convenção e usar timings do backend quando disponíveis |
| Vazão agregada | Tokens recebidos no intervalo global de medição / duração do intervalo |
| Vazão de requisições | Requisições concluídas / intervalo, complementar |
| Tempo até resultado utilizável | Envio → `result` válido no domínio médico |

Para taxa após primeiro token, se usar `(n-1)/(t_last-t_first)`, tratar n<2 e denominador zero como indefinido. Não misturar com taxa `n/tempo_decode` de backend sem indicar definições.

Preferir contagem e timings do runtime. Se faltarem, tokenizar saída completa com tokenizer do mesmo modelo e rotular como estimativa; fronteiras de eventos não são tokens. Para vazão em janela, contar apenas tokens/deltas recebidos na janela segundo método registrado, incluindo trabalho parcial separado do trabalho útil.

Log JSONL por request/tentativa: IDs, usuário pseudonimizado, domínio/modelo/nó, configuração/hash, política, instantes locais, comprimentos, tokens, estado final, queue depth, retries, erro e `finish_reason`. Métricas por nó incluem ativos, pendentes, CPU/RAM e EWMA de serviço.

Não calcular menor-latência comparando TTFT de domínios/tamanhos incomparáveis. Usar EWMA por configuração elegível, com warm-up/rodízio para nós sem observação e regra de desempate estável.

## 12. Avaliação clínica sem vazamento

1. Conferir JSON, IDs, synthetic e checksums; produzir relatório estrutural sem tocar fontes.
2. Detectar textos idênticos/quase duplicados e famílias de templates antes dos splits. Os 500 IDs contíguos não são amostra aleatória; não afirmar representatividade populacional.
3. Proposta: **100 desenvolvimento e 400 avaliação preliminar**, separando grupos semelhantes quando possível. Registrar IDs e seed em arquivo pequeno; o split de origem `train` não impede usar parte como nosso teste, desde que não a usemos para ajustar prompts.
4. Dentro da avaliação, selecionar **60 registros para revisão humana** estratificada por presença de campos, negações e tamanho. Os integrantes revisam a fidelidade ao texto; preferir dois revisores e adjudicação de divergências, sem fingir que são profissionais de saúde.
5. Não exigir 500 revisões humanas nem novas chamadas a APIs para desbloquear M1.
6. Comparar candidatos primeiro em pequeno desenvolvimento; congelar prompt/modelo; só então avaliar teste. Não ajustar após olhar os erros de teste sem registrar nova rodada.

Métricas: taxa JSON/schema válido, truncamentos, acerto exato de idade/sexo explícitos, precisão/recall/F1 de entidades e atributos com regras de normalização pré-definidas, erro em campos ausentes e fidelidade de unidades. Manter dose/via/frequência: não removê-las só para aumentar F1. Para texto livre/queixa, rubrica humana ou métrica de correspondência limitada, nunca igualdade literal como único critério.

Não aceitar tolerância de ±1 ano ou ±10 mmHg automaticamente: extração deve preservar o valor escrito; conversões/tolerâncias só com justificativa explícita. Reportar resultados completos e por campo presente/ausente; sexo quase sempre null pode inflar acurácia.

Separar resultados contra referência LLM e contra subconjunto humano. Avaliação médica é complementar; não substituir gráficos de Redes por qualidade do modelo.

## 13. Experimento principal: modo fechado e previsão de fila

### Hipóteses propostas

H1: com capacidade fixa de inferência, aumentar N aumenta espera/TTFT e a vazão se aproxima de um teto; em população fechada a fila não diverge infinitamente.

H2: prioridade não preemptiva para respostas previstas curtas reduz TTFT/conclusão dos jobs curtos, podendo prejudicar longos; aging limita starvation.

H3: em réplicas no mesmo host, balanceamento redistribui trabalho mas não cria núcleos/RAM, podendo não aumentar a vazão.

### Calibração anterior à rodada principal

- Fixar modelo, domínio, schema, runtime, threads/slots, TLS, política e workload.
- Medir distribuição de prefill P, serviço S e tokens em 10–20 prompts de calibração fora do teste de qualidade, com uma solicitação ativa.
- Escolher budget de saída suficiente para JSON completo. **128 tokens não é um limite adequado presumido para todo prontuário.** `max_output_tokens` é teto, não garante mesmo tamanho final.
- Não carregar/descarregar modelos em cada request. Aquecer os modelos; testar custo cold-start separadamente.

### Previsão simples compatível com carga fechada

No baseline de **um nó, um slot, FIFO, think time zero**, usando média de serviço E[S] e prefill E[P], aproximação inicial:

```text
X_requests(N) ≈ 1 / E[S], sob ocupação contínua
TTFT(N) ≈ (N - 1) * E[S] + E[P] + transporte
R(N) ≈ N * E[S] + transporte
```

São aproximações de regime fechado serial, não Erlang-C aberto. Serviço inclui prefill e decodificação; fila espera a conclusão do job anterior. Variabilidade, startup e limites do servidor causam desvio.

Para múltiplos nós/classes/prioridade, usar **simulação discreta curta em Python**, alimentada somente com calibração prévia, mesma população fechada e política. Modelo analítico mais elaborado/MVA é opcional, não bloqueio. Não estimar parâmetros usando o próprio resultado que se pretende prever.

Salvar previsão, configuração e hashes **antes** da carga principal, com timestamp; commit se houver repositório Git, arquivo datado/hash caso contrário. Determinar previamente um limiar operacional de aumento de TTFT, sem procurar um "ponto de disparo" inexistente: em modo fechado pode haver crescimento gradual desde N=2.

### Matriz executável

**A — Obrigatória:** N=1/2/4/8/16, um nó/slot, domínio explícito/modelo fixo, FIFO, no mínimo cinco repetições independentes.

**B — Pergunta-desafio:** mesma população, mistura fixa de tarefas com saídas curtas/longas, FIFO versus prioridade estimada. Usar budget de saída/classe de tarefa e estimativa calibrada, não tamanho real conhecido após concluir. Sem preempção; aging. Comparar métricas por classe e totais.

**C — Desempenho:** duas ou mais réplicas equivalentes, RR versus menor fila versus menor latência, carga e recursos fixos, cinco repetições nos níveis representativos (todos os cinco níveis se orçamento permitir). Não misturar essa matriz com comparações de modelos diferentes.

**D — Falha:** nó morto antes do primeiro token e durante geração; registrar recuperação, trabalho perdido, erros, sucesso após retry e validade da saída. Algumas repetições por cenário com procedimento reproduzível, não um único screenshot.

**E — Incrementos restantes:** testes de segurança e avaliação do roteador separados da matriz principal. TLS permanece ligado na principal; tokens de carga têm rate limit alto e autorizado.

### Duração e coleta

- Não fixar 10 s de aquecimento/60 s de execução antes da calibração: uma resposta em CPU pode levar mais que isso.
- Aquecer por solicitações completas. Definir duração ou número de ciclos que permita, como alvo, cerca de dez conclusões por cliente/repetição; registrar qualquer redução e efeito nos percentis.
- Fixar o critério após piloto, antes da medição principal. Automatizar matriz para sessões longas; oferecer perfil rápido de smoke test separado.
- Repetições em ordem aleatória; reset de métricas/filas entre rodadas, pesos residentes e condições térmicas registradas.
- Preferir load generator em outro host; se estiver no mesmo, informar limitação e medir seu consumo. Python assíncrono leve não precisa de um núcleo por cliente.
- Monitorar memória/swap, carga externa e throttling. Regras de invalidação antes de medir; **não descartar rodadas lentas causadas pela própria saturação**.
- Timeouts/rejeições não desaparecem do relatório: TTFT de sucessos tem viés se ignorar censura. Reportar taxa de erro, piores esperas observadas e thresholds.
- Cache de respostas desligado. Controlar/documentar prefix cache/KV reutilizado do runtime; repetir prompts pode acelerar prefill.
- P50/p95 por request, agregados por repetição, dispersão e IC95% entre repetições. P95 com poucas amostras deve vir com ressalva; não tratar mil tokens de uma única rodada como mil repetições.

### Figuras e resposta ao desafio

1. TTFT versus N, previsão × observado, dispersão e erros.
2. Vazão tokens/s agregada versus N.
3. Fila/serviço/geração para explicar gargalo; tokens/s individuais.
4. FIFO × prioridade: TTFT e tempo de conclusão por classe, espera dos longos/aging.
5. Políticas de balanceamento e distribuição de jobs por réplica; falha em tabela/linha do tempo.

Para conversa, avaliar início percebido e fluidez. Para extração JSON, TTFT pode ser só `{` e não significar informação utilizável: discutir **tempo até resultado validado**, sem deixar de medir TTFT exigido. Não declarar uma métrica universalmente superior nem concluir a preferência humana só de um gráfico técnico.

## 14. Estrutura de código sugerida

```text
PLANO_COMPLETO_PROJETO_1.md       # este handoff
README.md                       # atualizado conforme funcionalidades reais
pyproject.toml                  # dependências/entrada CLI/testes
src/llm_gateway/
  api.py                        # FastAPI e endpoints
  config.py                     # configuração validada
  protocol.py                   # DTOs/eventos SSE
  scheduler.py                  # filas/dispatch/cancelamento
  balancing.py                  # políticas de seleção
  backends/                     # HTTP llama.cpp; simulado só para testes
  security.py                   # token, domínio, rate limit
  routing.py                    # auto domínio/complexidade
  metrics.py                    # tempos/logs/exportação
  clinical/                     # schema/prompt/validação/exportação
clients/                        # CLI e cliente de lote
configs/                        # cpu mínimo, réplicas, GPU futura
experiments/                    # carga, previsão, runner, gráficos
tests/                          # unitários/integração/falha/SSE
scripts/                        # setup/runtime/checksums/auditoria
data/anonymedbr/                 # preservar dados existentes
artifacts/                      # previsões e resultados novos; não versionar segredos
```

Adaptar nomes à estrutura que existir no momento da implementação. Evitar diretório genérico "increments" que separa artificialmente lógica integrada ao gateway.

## 15. Fases, dependências e definição de pronto

### F0 — Inventário e contratos (esforço pequeno)

Ler README/enunciado/dados canônicos; conferir trabalho existente; fixar esquema, API, métricas, políticas e arquivos de configuração. Registrar fontes/licenças e limitações.

**Pronto:** decisões coerentes, sem apagar dados, contratos testáveis e lista de pendências de licença.

### F1 — Backend e teste de viabilidade (médio)

Fixar build do llama.cpp, testar candidatos um por vez em 10–20 prompts de desenvolvimento, medir RAM/CPU/JSON completo. Selecionar pequeno e maior que caibam. Construir backend simulado para integração.

**Pronto:** dois modelos distintos viáveis ou bloqueio claramente comunicado, parâmetros/hash registrados, um stream real e um resultado clínico completo. Não benchmarkar todas as variantes antes de implementar gateway.

### F2 — Núcleo ponta a ponta (grande, caminho crítico de M1)

Implementar SSE, dois domínios, filas explícitas/limites, cancelamento, erros e métricas. Cliente CLI e testes com backend simulado + validação real.

**Pronto/M1:** dois modelos/prompts/parâmetros próprios, vários clientes, queue depth auditável, quatro métricas, demo de cinco minutos. Gabarito humano não bloqueia M1.

### F3 — Extração e exportação robustas (médio; paralela à F2)

Adapter dos 500 pares sem modificá-los, splits, amostra humana, geração restrita e exportação JSON/JSONL/CSV. Auditoria de ausências/unidades/negações.

**Pronto:** resultados separados das fontes, avaliação por campo documentada, truncamento não exportado como válido e lote retomável.

### F4 — Incrementos e políticas de fila (grande)

Réplicas, três balanceadores, failover antes/depois de delta; segurança completa; classificador e escolha de tamanho; FIFO/prioridade com aging.

**Pronto:** evidências de cada incremento, testes negativos e falha real, recursos medidos. Se réplicas no mesmo host, limitação explícita.

### F5 — Piloto, previsão e roteiro (médio; M2)

Implementar carga fechada, calibrar tempos, escolher duração e budgets, gerar previsão analítica serial/simulação, congelar matriz.

**Pronto/M2:** incrementos demonstráveis, previsão prévia salva e experimento executável sem ajustes manuais por rodada.

### F6 — Medição e análise (grande em tempo de máquina; M3)

Rodar matrizes, preservar CSV/JSONL, explicar erros e desvios, gerar gráficos automaticamente e responder desafio com dados.

**Pronto:** todos os cinco N, repetições, gráficos, comparação previsão e resultados de filas; não confundir mock com LLM real.

### F7 — Reprodução e entrega (médio)

README com comandos exatos, arquivos necessários, permissões/licenças, configuração CPU/GPU e limitações; relatório ≤6 páginas e roteiro final.

**Pronto/M3:** outra pessoa consegue iniciar/testar pelo README, gráficos regeneram a partir dos brutos, demo falha sem corromper saída e fontes restritas não foram publicadas.

## 16. Divisão entre integrantes e cortes seguros

- A: gateway, protocolo, scheduler, balanceamento/failover.
- B: runtime, modelos, extração/schema, dados/avaliação e classificador.
- C: instrumentação, segurança, load generator, previsão e gráficos.
- Contratos definidos juntos; revisão cruzada de SSE/tempos e avaliação antes de integrar. Distribuição é sugestão, não obrigação de isolar componentes.

**Cortar primeiro:** frontend, OCR, FHIR, RAG, cache semântico, fine-tuning, comparação Gemma, benchmark GPU, longas evidências geradas em cada request e revisão humana dos 500 casos.

**Não cortar silenciosamente:** terceiro incremento, domínio/modelo distinto, autorização/rate limit, dois nós elegíveis para balanceamento, teste mid-stream, política de fila comparativa, previsão prévia, níveis N, repetições/gráficos e métricas.

Se faltar recurso para um requisito escolhido, relatar bloqueio e negociar redução com usuário/professor; não prometer "mesma nota" nem inventar aprovação. Failover com erro explícito após primeiro token já é a política planejada, sem implementação de retomada de prefixo.

## 17. Checklist de testes e evidências

- [ ] Configuração rejeita nó/modelo/domínio inexistente e limites inválidos.
- [ ] Dois domínios explícitos selecionam modelo/prompt/parâmetros próprios.
- [ ] `auto` não contorna autorização; baixa confiança tem tratamento definido.
- [ ] Deltas chegam antes de fim; heartbeat não conta em TTFT; Unicode é preservado.
- [ ] Contagem de tokens não é contagem de chunks.
- [ ] Ativos nunca excedem limite por nó; fila cheia e deadlines são observáveis.
- [ ] Cliente cancelado/liberação de slot e cliente lento não vazam jobs/memória.
- [ ] JSON truncado, inválido ou parcial não recebe status de resultado validado.
- [ ] Retry somente antes de saída; nó morto após delta gera erro parcial, sem concatenação.
- [ ] Balanceamento compara réplicas equivalentes com seleção atômica e desempate.
- [ ] Auth 401, domínio 403, rate limit 429 e sobrecarga 503 são distintos.
- [ ] TLS validado pelo cliente com CA; segredos/textos não entram em logs públicos.
- [ ] Fontes e anotações pareadas por ID, hashes verificados e arquivos históricos excluídos.
- [ ] Split/seed/grupos, prompt/modelo e avaliação humana registrados sem vazamento.
- [ ] Experimento usa N exatos, cinco repetições, configuração congelada e previsão anterior.
- [ ] Gráficos incluem incerteza, erros e discussão de FIFO/prioridade/saturação.
- [ ] README e relatório distinguem implementado, simulado, planejado e limitações.

## 18. Instruções prontas para o próximo agente

> Leia `PLANO_COMPLETO_PROJETO_1.md`, `README.md` e a seção Projeto 1 de `Propostas de Trabalho.md`. Confira o código existente antes de alterar. Preserve `data/anonymedbr/`, especialmente os JSONLs canônicos e auditorias. Implemente por fases, priorizando F0–F2/M1, com Python e inferência local em Ubuntu 8 GB/4 núcleos. Use modelos distintos por domínio, fila explícita por nó, SSE progressivo, testes e métricas precisas. Não espere GPU nem detalhes adicionais de hardware. Só depois integre extração/exportação, os três incrementos e carga fechada com previsão anterior e gráficos. Não copie frameworks AGPL sem avaliar obrigações, não publique o dataset com licença pendente e não use APIs externas como fallback de inferência. Faça progresso incremental, valide cada fase e atualize o README conforme a realidade. Ao encontrar um bloqueio de recursos ou compatibilidade, registre o resultado e use os fallbacks descritos, sem remover requisitos por conta própria. Não considere este documento prova de execução nem benchmark.

Não é preciso carregar todos os 500 prontuários no contexto do agente: começar pelos READMEs e manifesto; usar scripts para validar/medir e inspecionar pequenas amostras direcionadas. Só abrir auditorias de lotes se houver dúvida concreta de proveniência/anotação. Não repetir buscas amplas de modelos ou reler a conversa inteira: as pendências específicas estão enumeradas acima.
