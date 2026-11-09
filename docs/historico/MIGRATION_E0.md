# E0 — inventário e migração local (02/11/2026)

- Base histórica conferida: `937188091a9496e1ac4658d7900e9f8ff6dfcfac` (`main`); commit pai `8a49ce1`.
- A origem permanece em `Tudo Junto/`, sem reset, remoção ou rewrite. Alterações preexistentes nessa origem eram `README.md` modificado e `PLANO_CONTINUIDADE_REVISAO_E_3_REPOS.md` não rastreado; preservados.
- Backend: clonado localmente com `git clone --no-hardlinks`, mantendo os dois commits; sincronização de trabalho excluiu `.git`, `.devenv`, modelos, artefatos e `data/anonymedbr/`. Referência `origin` removida para não criar implicação de publicação. Próximas mudanças são feitas no destino Backend; a origem fica como cópia de segurança legível.
- Frontend e LLM: diretórios locais com `.git` independentes, sem remotes; estrutura inicial e testes próprios adicionados nesta execução.
- Inventário ignorado na origem: `.devenv/`, `.ruff_cache/`, `artifacts/`, `data/anonymedbr/`, `models/`, `src/llm_gateway.egg-info/` e caches Python. Dataset contém registros/fontes/anotações/auditorias e pesos GGUF permanecem somente no local original; hashes não foram copiados para outros repos.
- Manifesto local `migration_inventory.local.json` (modo `0600`, ignorado por Git) registra base, contagens/tamanhos de ignorados e hashes locais do roteador/pesos, sem conteúdo de registros.
- Regressão do snapshot original: 94 testes passaram com OpenSSL via `nix shell nixpkgs#openssl`. Backend após separar runtime/config: 94 testes passaram e Ruff check/format passaram em `devenv shell`. `devenv shell` do snapshot original não materializou na primeira tentativa; não foi feita instalação global.
- Arquitetura mantida: filas/load balancing/retries pertencem ao Backend; nenhum runtime ou dados de inferência no Frontend. `backends/llama_server.py` é adapter HTTP, não o runtime.
- Histórico Backend: clone sem hardlinks preserva commits e objetos; sem reescrever commits ou configurar remoto. A cópia original e seu `origin` não foram alterados.
- Sem commits, pushes, criação de remotos, licença atribuída ou publicação de dados nesta etapa.
