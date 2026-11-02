{ pkgs, ... }:
{
  # Utilitários do gateway; inferência instalada/executada pelo repositório LLM.
  # Nada é instalado no sistema: tudo fica em .devenv/ e no venv do projeto.
  packages = [
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
      requirements = ''
        -e .[dev]
      '';
    };
  };

  env.PYTHONUNBUFFERED = "1";

  enterShell = ''
    echo "python: $(python --version)" >&2
  '';
}
