"""Завдання 3.3 — система лінійних рівнянь: обернена матриця та метод Крамера."""

from __future__ import annotations

import numpy as np

DEFAULT_A = [[5, 1, -1],
             [1, 4, 2],
             [2, -3, 3]]

# Варіант з методички — для заміни за потреби.
MANUAL_A = [[4, 1, -1],
            [1, 5, 2],
            [2, -3, 2]]


def default_b(k: int) -> np.ndarray:
    """Вектор вільних членів для системи за замовчуванням."""
    return np.array([38, 6 * k + 25, 30 - k], dtype=float)


def manual_b(k: int) -> np.ndarray:
    """Вектор вільних членів з методички."""
    return np.array([35, 6 * k + 25, 30 - k], dtype=float)


def build_system(k: int, A=None, b=None) -> tuple[np.ndarray, np.ndarray]:
    """Повертає (A, b); якщо не передано — систему за замовчуванням."""
    A = np.array(DEFAULT_A if A is None else A, dtype=float)
    b = default_b(k) if b is None else np.asarray(b, dtype=float)
    return A, b


def solve_inverse(A: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Метод оберненої матриці: x = A⁻¹·b (аналог MINVERSE + MMULT)."""
    if np.isclose(np.linalg.det(A), 0):
        raise np.linalg.LinAlgError("det(A) = 0 — метод оберненої матриці неможливий")
    A_inv = np.linalg.inv(A)
    return A_inv, A_inv @ b


def cramer_matrices(A: np.ndarray, b: np.ndarray) -> list[np.ndarray]:
    """Допоміжні матриці Aᵢ: i-й стовпець A замінено вектором b."""
    mats = []
    for i in range(A.shape[1]):
        Ai = A.copy()
        Ai[:, i] = b
        mats.append(Ai)
    return mats


def solve_cramer(A: np.ndarray, b: np.ndarray) -> tuple[float, list[float], np.ndarray]:
    """Метод Крамера: xᵢ = Δᵢ / Δ (аналог MDETERM). Повертає (Δ, [Δᵢ], x)."""
    delta = float(np.linalg.det(A))
    if np.isclose(delta, 0):
        raise np.linalg.LinAlgError("Δ = 0 — метод Крамера неможливий")
    deltas = [float(np.linalg.det(Ai)) for Ai in cramer_matrices(A, b)]
    return delta, deltas, np.array(deltas) / delta


def run(k: int, A=None, b=None) -> dict:
    """Виконує завдання 3.3 і повертає всі проміжні та кінцеві результати."""
    A, b = build_system(k, A, b)
    A_inv, x_inv = solve_inverse(A, b)
    delta, deltas, x_cramer = solve_cramer(A, b)
    x_np = np.linalg.solve(A, b)
    return {
        "A": A,
        "b": b,
        "A_inv": A_inv,
        "x_inverse": x_inv,
        "cramer_matrices": cramer_matrices(A, b),
        "delta": delta,
        "deltas": deltas,
        "x_cramer": x_cramer,
        "x_numpy": x_np,
        "residual_inverse": A @ x_inv - b,
        "residual_cramer": A @ x_cramer - b,
        "check_inverse": bool(np.allclose(A @ x_inv, b)),
        "check_cramer": bool(np.allclose(A @ x_cramer, b)),
        "methods_agree": bool(np.allclose(x_inv, x_cramer) and np.allclose(x_inv, x_np)),
    }
