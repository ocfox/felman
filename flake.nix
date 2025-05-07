{
  description = "fleman - automatic kao rou";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable-small";
    flake-parts.url = "github:hercules-ci/flake-parts";
    systems.url = "github:nix-systems/default";

    pyproject-nix = {
      url = "github:nix-community/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    uv2nix = {
      url = "github:adisbladis/uv2nix";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    pyproject-build-systems = {
      url = "github:pyproject-nix/build-system-pkgs";
      inputs = {
        pyproject-nix.follows = "pyproject-nix";
        uv2nix.follows = "uv2nix";
        nixpkgs.follows = "nixpkgs";
      };
    };
  };

  outputs =
    inputs:
    inputs.flake-parts.lib.mkFlake { inherit inputs; } {
      systems = import inputs.systems;

      perSystem =
        {
          pkgs,
          lib,
          ...
        }:
        let
          workspace = inputs.uv2nix.lib.workspace.loadWorkspace { workspaceRoot = ./.; };

          overlay = workspace.mkPyprojectOverlay {
            sourcePreference = "wheel";
          };

          python = pkgs.python312;

          pythonSet =
            (pkgs.callPackage inputs.pyproject-nix.build.packages {
              inherit python;
            }).overrideScope
              (
                lib.composeManyExtensions [
                  inputs.pyproject-build-systems.overlays.default
                  overlay
                  # Add ffmpeg as a dependency
                  (final: prev: {
                    fleman = prev.fleman.overrideAttrs (old: {
                      propagatedBuildInputs = (old.propagatedBuildInputs or [ ]) ++ [
                        pkgs.ffmpeg
                      ];
                    });
                  })
                ]
              );
        in
        {
          formatter = pkgs.nixfmt;

          packages = {
            default = pythonSet.mkVirtualEnv "fleman-env" workspace.deps.default;
          };

          apps = {
            default = {
              type = "app";
              program = "${pythonSet.mkVirtualEnv "fleman-env" workspace.deps.default}/bin/fleman";
            };
          };

          devShells = {
            impure = pkgs.mkShell {
              packages = [
                python
                pkgs.uv
                pkgs.ffmpeg
              ];
              env =
                {
                  UV_PYTHON_DOWNLOADS = "never";
                  UV_PYTHON = python.interpreter;
                }
                // lib.optionalAttrs pkgs.stdenv.isLinux {
                  LD_LIBRARY_PATH = lib.makeLibraryPath pkgs.pythonManylinuxPackages.manylinux1;
                };
              shellHook = ''
                unset PYTHONPATH
                echo "Welcome to the fleman impure development environment!"
              '';
            };

            default =
              let
                editableOverlay = workspace.mkEditablePyprojectOverlay {
                  root = "$REPO_ROOT";
                };
                editablePythonSet = pythonSet.overrideScope (
                  lib.composeManyExtensions [
                    editableOverlay

                    # Apply fixups for building an editable package
                    (final: prev: {
                      fleman = prev.fleman.overrideAttrs (old: {
                        # Include editables dependencies for hatchling
                        nativeBuildInputs =
                          old.nativeBuildInputs
                          ++ final.resolveBuildSystem {
                            editables = [ ];
                          };
                      });
                    })
                  ]
                );
                virtualenv = editablePythonSet.mkVirtualEnv "fleman-dev-env" workspace.deps.all;
              in
              pkgs.mkShell {
                packages = [
                  virtualenv
                  pkgs.uv
                  pkgs.ffmpeg
                ];
                env = {
                  UV_NO_SYNC = "1";
                  UV_PYTHON = "${virtualenv}/bin/python";
                  UV_PYTHON_DOWNLOADS = "never";
                };

                shellHook = ''
                  unset PYTHONPATH
                  export REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo $PWD)
                  echo "Welcome to the fleman development environment!"
                '';
              };
          };
        };
    };
}
