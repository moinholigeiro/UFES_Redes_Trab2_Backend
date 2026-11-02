# ADR — fronteiras dos três repositórios

**Status:** aceito para migração local, ainda sem publicação.

- `UFES_Redes_Trab2_Backend`: gateway, adapters HTTP, filas, contratos públicos, roteamento, auth, schema/prompt clínicos, cliente, dados sintéticos do roteador, ferramentas de avaliação/experimento e docs. É o único dono de autorização, retry e load balancing.
- `UFES_Redes_Trab2_LLM`: implementação e pin do llama.cpp, manifesto público de modelos, configs privadas por nó, ferramentas de download/validação e supervisor/runtime. Vários hosts executam este mesmo produto. Não balanceia chamadas.
- `UFES_Redes_Trab2_Frontend`: UX web consumindo somente a API pública HTTPS do Backend por `fetch` POST + SSE; não escolhe nós e não mantém tokens persistentes por padrão.
- Contrato público autoritativo fica no Backend (`contracts/public/v1`); contrato runtime versionado ficará no LLM (`contracts/internal/v1`). Integração registra refs/hashes fixos, nunca `main` flutuante.
- Migração aditiva e local: origem preservada e histórico Backend mantido; nenhum remoto/push até instrução explícita. Arquivos GGUF, dataset AnonyMED-BR e segredos não entram nos clones de produto.
