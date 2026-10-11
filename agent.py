import os
import time
import random
import chess
import chess.polyglot
import chess.syzygy

HERE = os.path.dirname(os.path.abspath(__file__))

"""
main flow:
get_move -> search_root -> negamax recursion -> qsearch recursion (+ evaluate for stand-pat)
side flow:
get_move -> order_move -> mvv_lva


alpha beta, depth 2:
push move A, at window -inf +inf.
We evaluate at depth 2, so try every move after A from Opp POV.
say -30. then -10. They pick -10 because it is the least bad for them.
score = -(-10) 
ideally we keep trying until we find a move where the Opp's best move is the most negative.
PRUNING
if move B, window -inf, -10, creates a move better than -10 (since Opp will play the best move available)
immediately prune move B - Opp will play atleast a move as good for them as -10. 
"""

try:
    TB = chess.syzygy.open_tablebase(os.path.join(HERE, "syzygy"))
except Exception:
    TB = None

PIECE_VALUE = [0, 100, 320, 330, 500, 900, 0]
MATE = 1_000_000
TB_WIN = 100_000
INF = 10**9
EXACT, LOWER, UPPER = 0, 1, 2

TT = {}          # zobrist key -> (depth, flag, score, best_move)
TT_MAX = 2_000_000

#custom exception, jumps call stack to get_move when timeout
class Timeout(Exception):
    pass
#creating class stops the need to pass in variables to functions
class Clock:
    deadline = 0.0
    nodes = 0

def tick():
    """
    checks time once every 2048 positions checked (either form qsearch or negamax)
    because time.time() too slow to call often.
    Important so that search returns the previous depth's best move 
    before time budget for each move runs out.
    """
    Clock.nodes += 1
    if Clock.nodes & 2047 == 0 and time.time() > Clock.deadline:
        raise Timeout

def popcount(x: int):
    """
    returns number of pieces
    """
    return x.bit_count()

def evaluate(board: chess.Board):
    """
    weighted sum of material, from the mover's perspective
    """
    us, them = board.turn, not board.turn
    score = 0
    for pt in range(1, 6):
        score += PIECE_VALUE[pt] * (popcount(board.pieces_mask(pt, us)) - popcount(board.pieces_mask(pt, them)))
    return score

def mvv_lva(board: chess.Board, move: chess.Move):
    """
    determines score of piece capture
    """
    victim = board.piece_type_at(move.to_square)
    if victim is None:  # en passant
        victim = chess.PAWN
    attacker = board.piece_type_at(move.from_square)
    return 10 * PIECE_VALUE[victim] - PIECE_VALUE[attacker]

def order_moves(board, moves, tt_move=None):
    """
    orders all legal moves from best to worst before searching
    """
    def key(m):
        if m == tt_move:
            return 10**7
        s = 0
        if board.is_capture(m):
            s += 10_000 + mvv_lva(board, m)
        if m.promotion:
            s += 9_000 + PIECE_VALUE[m.promotion]
        return s
    return sorted(moves, key=key, reverse=True)

def qsearch(board, alpha, beta):
    """
    recursively check captures against a stand-pat baseline
    apply a-b pruning so no checking worse captures after already seeing a better one.
    """
    # check MATE and checks; check legal moves again? since I can't stand-pat there?
    tick()
    stand = evaluate(board)
    if stand >= beta:
        return stand
    alpha = max(alpha, stand)
    caps = sorted(board.generate_legal_captures(),
                  key=lambda m: mvv_lva(board, m), reverse=True)
    for m in caps:
        board.push(m)
        score = -qsearch(board, -beta, -alpha)
        board.pop()
        if score >= beta:
            return score
        alpha = max(alpha, score)
    return alpha

def negamax(board, depth, alpha, beta, ply):
    """
    recursive a-b search on each move.
    """
    tick()
    if (board.halfmove_clock >= 100 or board.is_insufficient_material()
            or board.is_repetition(2)):
        return 0

    # Tablebase probe (WDL) inside the search
    if (TB is not None and not board.castling_rights
            and popcount(board.occupied) <= 4):
        try:
            wdl = TB.probe_wdl(board)
            if wdl == 2:
                return TB_WIN - ply
            if wdl == -2:
                return -TB_WIN + ply
            return 0
        except Exception:
            pass

    alpha_orig = alpha
    key = chess.polyglot.zobrist_hash(board)
    tt_move = None
    entry = TT.get(key)
    if entry is not None:
        e_depth, flag, e_score, tt_move = entry
        if e_depth >= depth:
            if flag == EXACT:
                return e_score
            if flag == LOWER:
                alpha = max(alpha, e_score)
            else:
                beta = min(beta, e_score)
            if alpha >= beta:
                return e_score

    if depth <= 0:
        return qsearch(board, alpha, beta)

    moves = list(board.legal_moves)
    if not moves:
        return -MATE + ply if board.is_check() else 0

    best, best_move = -INF, None
    for m in order_moves(board, moves, tt_move):
        board.push(m)
        score = -negamax(board, depth - 1, -beta, -alpha, ply + 1)
        board.pop()
        if score > best:
            best, best_move = score, m
        alpha = max(alpha, score)
        if alpha >= beta:
            break

    flag = EXACT
    if best <= alpha_orig:
        flag = UPPER
    elif best >= beta:
        flag = LOWER
    if len(TT) > TT_MAX:
        TT.clear()
    TT[key] = (depth, flag, best, best_move)
    return best

def search_root(board, depth, root_moves):
    """ 
    returns best move + score from list of moves
    """
    alpha, best_score, best_move = -INF, -INF, root_moves[0]
    for m in root_moves:
        board.push(m)
        score = -negamax(board, depth - 1, -INF, -alpha, 1)
        board.pop()
        if score > best_score:
            best_score, best_move = score, m
        alpha = max(alpha, score)
    return best_move, best_score

def tb_root_move(board):
    """Pick the best move purely from the tablebase, or None if not applicable."""
    if TB is None or board.castling_rights or popcount(board.occupied) > 4:
        return None
    try:
        best, best_key = None, None
        for m in board.legal_moves:
            board.push(m)
            wdl = -TB.probe_wdl(board)        # flip to our perspective
            dtz = abs(TB.probe_dtz(board))
            board.pop()
            # win: prefer lowest dtz; loss: prefer highest dtz; draws equal
            k = (wdl, -dtz if wdl > 0 else dtz)
            if best_key is None or k > best_key:
                best, best_key = m, k
        return best
    except Exception:
        return None

def get_move(fen: str, time_left_ms: int) -> str:
    """
    check if we can tb, otherwise set move budget. 
    check time against the budget every 2048 checked positions.
    iteratively search from best move to worst.
    returns best move 
    """
    board = chess.Board(fen)

    tb_move = tb_root_move(board)
    if tb_move is not None:
        return tb_move.uci()

    budget = max(0.05, min(time_left_ms / 1000 / 25, 10.0)) #[0.05s, 10s] for each move
    Clock.deadline = time.time() + budget
    Clock.nodes = 0

    root_moves = order_moves(board, list(board.legal_moves)) # order search for legal moves with quick heuristic. 
    best_move = root_moves[0] # assign our fallback best move to the best heuristically-determined move

    try:
        for depth in range(1, 60):
            move, score = search_root(board, depth, root_moves)
            best_move = move                # only kept if the iteration finished
            root_moves.remove(move)
            root_moves.insert(0, move)      # best move first next iteration
            if abs(score) > MATE - 100:     # score returned if MATE is MATE - ply, so MATE wihtin 100 plies should always catch MATE.
                break
    except Timeout:
        pass

    return best_move.uci()