{ pkgs ? import <nixpkgs> {}, dev ? false }:
with pkgs;
with pkgs.octoprint.python.pkgs;

mkShell {
  name = "octoprint-universal-filament-sensor";

  nativeBuildInputs = [ mypy ] ++ lib.optionals dev [ pip pylint rope autopep8 ];

  buildInputs = [
    octoprint
    libgpiod
  ];

  shellHook = ''
    export PYTHONPATH="$PYTHONPATH:${toString ./.}"
  '';
}

