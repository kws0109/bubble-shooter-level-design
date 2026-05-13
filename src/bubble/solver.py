"""Monte Carlo bot players for difficulty calibration.

Iteration 2 mechanic
--------------------
Each turn the shooter holds a queue of TWO colors (current + alt). The bot
picks which queue slot to fire. After firing, only that slot is refilled
with a new random color; the other carries over. This matches Bubble Pop
Origin's color-swap mechanic.

Three bot strengths
-------------------
- WeakBot:    first valid match across either queue color; otherwise
              place adjacent to a same-color cluster.
- MediumBot:  enumerate (position, queue_index) and pick the one that
              maximizes current `popped`. Setup fallback when no match.
- StrongBot:  greedy + 1-step look-ahead bonus on top-K candidates.
              Look-ahead averages over the carried-over queue color and
              one random next color.

The spread between weak and strong clear-rate is the difficulty signal.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Protocol

from .board import Board, EMPTY, ShotResult


# --- result containers -----------------------------------------------------

@dataclass(frozen=True)
class PlayResult:
    cleared: bool
    shots_used: int
    bubbles_popped: int


@dataclass(frozen=True)
class CalibrationResult:
    bot_name: str
    runs: int
    clear_rate: float
    eac: float
    eac_all: float
    avg_popped: float

    def as_dict(self) -> dict:
        return {
            "bot_name": self.bot_name,
            "runs": self.runs,
            "clear_rate": self.clear_rate,
            "eac": self.eac,
            "eac_all": self.eac_all,
            "avg_popped": self.avg_popped,
        }


# --- bot interface ---------------------------------------------------------

ShotChoice = tuple[int, int, int]  # (row, col, queue_index in {0, 1})


class Bot(Protocol):
    name: str
    def choose_shot(self, board: Board, queue: list[int],
                    rng: random.Random) -> ShotChoice | None: ...


def _adjacent_to_same_color(board: Board, color: int,
                            position: tuple[int, int]) -> bool:
    return any(board.get(*n) == color for n in board.occupied_neighbors(*position))


# --- weak bot --------------------------------------------------------------

class WeakBot:
    name = "weak"

    def choose_shot(self, board: Board, queue: list[int],
                    rng: random.Random) -> ShotChoice | None:
        positions = board.valid_shot_positions()
        if not positions:
            return None
        rng.shuffle(positions)
        # First match across either queue color.
        for pos in positions:
            for qi, color in enumerate(queue):
                if board.simulate_shot(*pos, color).is_match:
                    return (pos[0], pos[1], qi)
        # Setup fallback: placement adjacent to same color.
        for pos in positions:
            for qi, color in enumerate(queue):
                if _adjacent_to_same_color(board, color, pos):
                    return (pos[0], pos[1], qi)
        # Last resort.
        return (positions[0][0], positions[0][1], 0)


# --- medium bot ------------------------------------------------------------

class MediumBot:
    name = "medium"

    def choose_shot(self, board: Board, queue: list[int],
                    rng: random.Random) -> ShotChoice | None:
        positions = board.valid_shot_positions()
        if not positions:
            return None
        rng.shuffle(positions)
        best_pop = 0
        best_choice: ShotChoice | None = None
        for pos in positions:
            for qi, color in enumerate(queue):
                popped = board.simulate_shot(*pos, color).popped
                if popped > best_pop:
                    best_pop = popped
                    best_choice = (pos[0], pos[1], qi)
        if best_choice is not None:
            return best_choice
        # Setup fallback.
        for pos in positions:
            for qi, color in enumerate(queue):
                if _adjacent_to_same_color(board, color, pos):
                    return (pos[0], pos[1], qi)
        return (positions[0][0], positions[0][1], 0)


# --- strong bot ------------------------------------------------------------

class StrongBot:
    """Greedy + 1-step look-ahead, restricted to top-K current candidates.

    The look-ahead score reflects the queue mechanic: after firing slot
    `qi`, the unused color `queue[1 - qi]` is still available next turn,
    paired with one new random color. We average the best one-shot
    popped value over that distribution.
    """
    name = "strong"
    LOOKAHEAD_DISCOUNT = 0.35
    LOOKAHEAD_K = 10  # 2-color queue doubles candidates; widen the gate.

    def choose_shot(self, board: Board, queue: list[int],
                    rng: random.Random) -> ShotChoice | None:
        positions = board.valid_shot_positions()
        if not positions:
            return None
        rng.shuffle(positions)

        scored: list[tuple[int, ShotChoice, Board]] = []
        for pos in positions:
            for qi, color in enumerate(queue):
                shot = board.simulate_shot(*pos, color)
                scored.append((shot.popped, (pos[0], pos[1], qi), shot.board_after))
        scored.sort(key=lambda x: x[0], reverse=True)

        best_score = -1.0
        best_choice: ShotChoice | None = None
        for current_popped, choice, after in scored[: self.LOOKAHEAD_K]:
            qi = choice[2]
            carried = queue[1 - qi]
            future_avg = self._lookahead_score(after, carried)
            score = current_popped + self.LOOKAHEAD_DISCOUNT * future_avg
            if score > best_score:
                best_score = score
                best_choice = choice
        return best_choice if best_choice is not None else scored[0][1]

    def _lookahead_score(self, board: Board, carried_color: int) -> float:
        if board.occupied_count() == 0:
            return 0.0
        positions = board.valid_shot_positions()
        if not positions:
            return 0.0
        # carried_color (deterministic) and one random next color, averaged.
        total = 0.0
        for next_color in range(1, board.num_colors + 1):
            colors = (carried_color, next_color)
            best_pair = 0
            for pos in positions:
                for color in colors:
                    v = board.simulate_shot(*pos, color).popped
                    if v > best_pair:
                        best_pair = v
            total += best_pair
        return total / board.num_colors


# --- play loop -------------------------------------------------------------

def play_one(board: Board, bot: Bot, rng: random.Random,
             shot_cap: int | None = None) -> PlayResult:
    board = board.clone()
    if shot_cap is None:
        shot_cap = max(board.shots_remaining, 1)
    shots_used = 0
    bubbles_popped = 0

    queue: list[int] = [
        rng.randint(1, board.num_colors),
        rng.randint(1, board.num_colors),
    ]

    while shots_used < shot_cap and board.occupied_count() > 0:
        choice = bot.choose_shot(board, queue, rng)
        if choice is None:
            break
        row, col, qi = choice
        color = queue[qi]
        result = board.simulate_shot(row, col, color)
        board = result.board_after
        shots_used += 1
        bubbles_popped += result.popped
        # Refill only the consumed slot.
        queue[qi] = rng.randint(1, board.num_colors)

    return PlayResult(
        cleared=(board.occupied_count() == 0),
        shots_used=shots_used,
        bubbles_popped=bubbles_popped,
    )


def calibrate(board: Board, bot: Bot, runs: int = 60,
              base_seed: int = 0,
              shot_cap: int | None = None) -> CalibrationResult:
    if shot_cap is None:
        shot_cap = max(3 * board.shots_remaining, 30)

    cleared = 0
    eac_sum = 0
    eac_all_sum = 0
    popped_sum = 0
    for i in range(runs):
        rng = random.Random(base_seed + i)
        result = play_one(board, bot, rng, shot_cap=shot_cap)
        eac_all_sum += result.shots_used
        popped_sum += result.bubbles_popped
        if result.cleared:
            cleared += 1
            eac_sum += result.shots_used

    return CalibrationResult(
        bot_name=bot.name,
        runs=runs,
        clear_rate=cleared / runs,
        eac=(eac_sum / cleared) if cleared else float("inf"),
        eac_all=eac_all_sum / runs,
        avg_popped=popped_sum / runs,
    )


ALL_BOTS: tuple[Bot, ...] = (WeakBot(), MediumBot(), StrongBot())


def calibrate_triplet(board: Board, runs: int = 60,
                      base_seed: int = 0) -> dict[str, CalibrationResult]:
    return {bot.name: calibrate(board, bot, runs=runs, base_seed=base_seed)
            for bot in ALL_BOTS}
