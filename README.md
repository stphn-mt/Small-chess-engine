# Chess Engine

A small chess engine written in Python on top of [python-chess](https://python-chess.readthedocs.io/). It was built for Optiver's chessathon, where the engine is given a position and a clock and must return a move. 
Unfortunately, I joined the hackathon late, but I wanted to keep working on my program because I found the set-up nice to work with. This is the result after that extra work.

The engine searches with negamax and alpha-beta pruning, uses a transposition table and quiescence search, and can play perfect 4-piece endgames from Syzygy tablebases.

## Features

- **Negamax with alpha-beta pruning** as the core search
- **Iterative deepening**: searches depth 1, 2, 3, ... and always returns the best move from the last fully completed depth
- **Transposition table** keyed on Zobrist hashes, storing depth, bound type (`EXACT`, `LOWER`, `UPPER`), score and best move
- **Move ordering**: transposition-table move first, then captures by MVV-LVA (most valuable victim, least valuable attacker), then promotions
- **Quiescence search**: resolves capture sequences at the leaves to avoid the horizon effect
- **Syzygy tablebase support** (optional): perfect play for positions with 4 or fewer pieces and no castling rights
- **Time management**: spends roughly 1/25 of the remaining clock per move, bounded between 50 ms and 10 s
- **Mate detection**: stops deepening search as soon as a forced mate is found, and prefers faster mates

## Usage

The entry point is `get_move`:

```python
from engine import get_move

fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
move = get_move(fen, time_left_ms=60_000)
print(move)  # a move in UCI notation, e.g. "e2e4"
```

| Argument | Type | Description |
| --- | --- | --- |
| `fen` | `str` | The current position in FEN |
| `time_left_ms` | `int` | Time remaining on the engine's clock, in milliseconds |

It returns the chosen move as a UCI string.

## Tablebases (optional)

To enable endgame play, place Syzygy tablebase files in a `syzygy/` folder next to the engine file:

```
engine.py
syzygy/
    KQvK.rtbw
    KQvK.rtbz
    ...
```

If the folder is missing, the engine still works and simply skips tablebase lookups. Only positions with 4 or fewer pieces and no castling rights are probed. Keep the total submission size in mind if your platform has an upload limit (chessathon caps submissions at 50 MB).

## How it works

```
get_move
 ├── tb_root_move        # 4 pieces or fewer -> plays straight from the tablebase
 └── iterative deepening loop
      └── search_root    # one pass at a fixed depth over all root moves
           └── negamax   # alpha-beta, TT lookup/store, draw and mate detection
                └── qsearch   # captures only, until the position is quiet
```

- `tick()` counts nodes and checks the clock every 2048 nodes. When time is up it raises `Timeout`, which unwinds the whole recursive search at once. `get_move` catches it and returns the move from the last completed depth.
- `evaluate` is a material count from the side to move's perspective.
- Mate scores are `MATE - ply`, so shorter mates score higher.

## Limitations

- Evaluation is material only: no piece-square tables, pawn structure, king safety or mobility
- `qsearch` only considers captures, so it can miss mates and checks that follow a capture sequence
- The transposition table is cleared entirely when it reaches 2 million entries, rather than using a replacement scheme
- No null-move pruning, late move reductions or killer/history heuristics yet
- No opening book, although that was part of the 50MB file submission tradeoff from the hackathon

## Possible next steps

- Add piece-square tables to the evaluation
- Handle checks and checkmates in quiescence search
- Add null-move pruning and late move reductions
- Add killer and history heuristics to move ordering
- Replace the clear-everything TT policy with depth-preferred replacement
