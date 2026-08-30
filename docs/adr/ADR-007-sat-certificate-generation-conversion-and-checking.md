# ADR-007: SAT certificate generation, conversion, and checking

## Context

Solver output alone lacks mathematical authority. Phase 1 needs a tested SAT model path and a formally verified final UNSAT checker.

## Decision

Pin CaDiCaL `c607304…` (3.0.1), DRAT-trim `2e3b2dc…`, and cake_lpr `a36874a…`. Run them as separate shell-free processes. The command contracts are:

```text
cadical INPUT.cnf OUTPUT.drat
drat-trim INPUT.cnf OUTPUT.drat -L OUTPUT.lrat
cake_lpr --CML_HEAP_SIZE=128 --CML_STACK_SIZE=128 INPUT.cnf OUTPUT.lrat
```

The static `--competition` CaDiCaL build omits convenience options such as `-q`; the argument contract therefore uses positional input and proof paths only. CaDiCaL exit 10 plus `s SATISFIABLE` enters a separate strict Python checker process. Exit 20 plus `s UNSATISFIABLE` enters DRAT validation/LRAT conversion, then cake_lpr; acceptance requires exit 0 and `s VERIFIED UNSAT`. The explicit CakeML heap and stack flags replace cake_lpr's 4 GiB defaults so its address-space reservation remains within the 512 MiB Phase 1 process limit.

## Alternatives considered

Trusting DRAT-trim as the final checker left converter and authority coupled. Direct LRAT emission reduced a stage while narrowing solver choice.

## Material consequences

Proof bytes, conversion output, executable hashes, source commits, commands, exits, and reports become immutable artifacts. Checker images exclude solver code.

## Failure modes

Malformed DIMACS, incompatible binary DRAT, output exhaustion, timeout, converter rejection, and checker rejection remain typed evidence. Failed originals precede repair.

## Reversal path

Register another pinned generator/converter/checker triple after positive, negative, malformed, and resource tests.

## Verification

The tiny fixtures establish accepted SAT/UNSAT and rejected invalid LRAT behavior. Upstream command evidence comes from each repository README and the cake_lpr SAT Competition checker note.
