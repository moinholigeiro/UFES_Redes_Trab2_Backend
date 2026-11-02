{ pkgs, ... }:
{
  # Runtime de inferência (llama-server) e utilitários de terminal.
  # Nada é instalado no sistema: tudo fica em .devenv/ e no venv do projeto.
  packages = [
    pkgs.llama-cpp
    pkgs.curl
    pkgs.jq
    pkgs.openssl
    pkgs.gh
  ];

  languages.python = {
    enable = true;
    package = pkgs.python313;
    venv = {
      enable = true;
      requirements = "-e .[dev]";
    };
  };

  env.PYTHONUNBUFFERED = "1";

  enterShell = ''
    echo "llama-server: $(llama-server --version 2>/dev/null | head -1)" >&2
    echo "python: $(python --version)" >&2
  '';
}
