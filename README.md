# conda-declarative

Declarative workflows for conda environment handling.

> [!IMPORTANT] This project is still in early stages of development. Don't use
> it in production (yet). We do welcome feedback on what the expected behaviour
> should have been if something doesn't work!

## What is this?

`conda declarative` proposes an alternative workflow for the lifecycle of
`conda` environments. It is based around the idea of having a "manifest file"
where all the user input for the environment is declared and stored. This is
exposed via two new subcommands:

- `conda edit`: opens an editor to perform modifications on the active
  environment manifest file.
- `conda apply`: renders the manifest file as a history checkpoint and links the
  solved packages to disk.

### Manifest

The manifest is a file that lives at `conda-meta/conda.toml`; its format follows
[a proposal for a TOML-based environment
specification](https://docs.google.com/document/d/1Q_M66kFGCYLuaqAqez_jlsqxnQEQh5tSUBtvEz3ixdA/edit?tab=t.styv1cfnnyqy#heading=h.5yxwasl3gb67)
which is implemented using [environment specifier
hooks](https://docs.conda.io/projects/conda/en/stable/dev-guide/plugins/environment_specifiers.html).

Under the hood, the `TomlSpec` class provides the interface required of a valid
environment specifier, acting as a converter between

- TOML files
- dictionaries of parsed environments
- `conda.models.environment.Environment` instances

The TomlSpec class can be instantiated with any of these and can be used to
generate the others. To do this the `TomlSpec` class employs a
`TomlSingleEnvironment` Pydantic model which carries out serialization,
deserialization, and validation.

```
┌────┐     ┌────┐     ┌─────────────────────┐     ┌────────┐     ┌───────────┐     ┌─────┐
│TOML│◄───►│dict│◄───►│TomlSingleEnvironment│◄───►│TomlSpec│◄───►│Environment│◄───►│conda│
└────┘     └────┘     └─────────────────────┘     └────────┘     └───────────┘     └─────┘
```

### Caveats

- If the user doesn't have an existing `conda-meta/conda.toml` in their prefix,
  one will be generated for them when `conda edit` is run. To do this, the
  current approach looks at the packages that are already installed in the
  environment. Because there's no way to know which of them were explicitly
  requested by the user, or whether any version constraints were requested when
  they were installed, _all_ of them are currently added to the `dependencies`
  with the currently installed version.

  This makes it really hard to add new packages (because the version constraints
  are likely too tight to solve), and likely doesn't match the intent of the
  user.

  An alternative approach is to use `conda-meta/history` to populate
  `conda.toml` with the user-requested packages; but this doesn't work if the
  environment isn't managed by `conda`, as is the case for the development
  environments used in this project (`pixi` doesn't write to
  `conda-meta/history`).

- Package removal doesn't work yet. The main focus so far has been on the TUI
  and the spec.

## Installation

This is a `conda` plugin and goes in the `base` environment:

```bash 
conda install -n base conda-forge::conda-declarative
```

More information is available on our
[documentation](https://conda-incubator.github.io/conda-declarative).

## Try it locally

1. Make sure `pixi` and `git` are installed. [Instructions for
   `pixi`](https://pixi.sh/latest/installation/).
2. Clone this repository: `git clone
   https://github.com/jaimergp/conda-declarative`
3. Change to that directory: `cd conda-declarative`
4. Run the help message: `pixi run conda edit --help`

We _could_ just use the default pixi env to try things, but it doesn't write a
good `history` file, so `conda edit|apply` will misunderstand what to do and
remove everything sometimes. For now, let's use this default conda to create a
demo environment to do things with:

1. Create a demo environment with `conda` and `pip`: `pixi run conda create -p
   .pixi/envs/demo conda pip`
2. Pseudo-activate it: `conda spawn ./.pixi/envs/demo`.
3. Install conda-self in it `pip install -e .`
4. Play with `python -m conda edit`
   1. `python -m conda edit` to open the TUI and play around
   2. `python -m conda apply` to sync the changes done in the TUI
   3. You can also edit the file reported by `python -m conda edit --show` and
      then run `python -m conda apply` directly.

## Contributing

Please refer to [`CONTRIBUTING.md`](/CONTRIBUTING.md).
