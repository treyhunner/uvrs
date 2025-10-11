# Contributing

## Prerequisites

- [uv](https://github.com/astral-sh/uv#installation) for dependency management
- [just](https://github.com/casey/just) for task running

`just` can be installed with:

```console
uv tool install just-rust
```


## Pre-commit hooks

To configure pre-commit hooks:

```console
just setup
```


## Running linters, auto-formatters and tests

Before submitting changes run all linters, auto-formatters, and automated tests with:

```console
just check
```


## Running specific tests

To pass specific arguments to pytest (to run specific tests for example) use `just test`:

```console
just test -k some_pattern
```

To run code coverage:

```console
just test-cov
```
