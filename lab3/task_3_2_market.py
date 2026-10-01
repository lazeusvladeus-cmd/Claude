"""Завдання 3.2 — попит, пропозиція і рівновага ринку (аналог «Підбору параметра»)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import brentq, fsolve

Q_MIN, Q_MAX, Q_STEP = 10, 80, 5


def demand(q, k: int):
    """Попит: P = 1000·k / Q."""
    return 1000 * k / np.asarray(q, dtype=float)


def supply(q):
    """Пропозиція: P = e^(Q/10)."""
    return np.exp(np.asarray(q, dtype=float) / 10)


def excess(q: float, k: int) -> float:
    """Різниця попиту та пропозиції; дорівнює нулю в точці рівноваги."""
    return float(demand(q, k) - supply(q))


def build_table_10(k: int) -> pd.DataFrame:
    """Таблиця 10: попит і пропозиція для Q від 10 до 80 з кроком 5."""
    q = np.arange(Q_MIN, Q_MAX + Q_STEP, Q_STEP)
    return pd.DataFrame({
        "Кількість товару": q,
        "Попит": demand(q, k),
        "Пропозиція": supply(q),
    })


@dataclass
class Equilibrium:
    """Результат пошуку рівноваги."""

    q: float
    p1: float
    p2: float

    @property
    def diff(self) -> float:
        return self.p1 - self.p2

    @property
    def price(self) -> float:
        return self.p2


def find_equilibrium(k: int) -> Equilibrium:
    """Рівноважний випуск Q* методом Брента на [10, 80] (аналог Goal Seek)."""
    q = brentq(excess, Q_MIN, Q_MAX, args=(k,), xtol=1e-12)
    return Equilibrium(q=q, p1=float(demand(q, k)), p2=float(supply(q)))


def find_equilibrium_fsolve(k: int) -> float:
    """Те саме через scipy.optimize.fsolve — для порівняння."""
    return float(fsolve(lambda q: excess(q[0], k), x0=[(Q_MIN + Q_MAX) / 2])[0])


def bisection(k: int, a: float = Q_MIN, b: float = Q_MAX, tol: float = 1e-10) -> float:
    """Власний метод бісекції — для порівняння."""
    fa = excess(a, k)
    while b - a > tol:
        m = (a + b) / 2
        fm = excess(m, k)
        if fa * fm <= 0:
            b = m
        else:
            a, fa = m, fm
    return (a + b) / 2


def build_table_11(eq: Equilibrium) -> pd.DataFrame:
    """Таблиця 11: результати підбору параметра."""
    return pd.DataFrame({
        "Показник": [
            "Рівноважний випуск Q*",
            "P1 = 1000·k/Q* (попит)",
            "P2 = e^(Q*/10) (пропозиція)",
            "Різниця P1 − P2",
            "Ціна рівноваги P*",
        ],
        "Значення": [eq.q, eq.p1, eq.p2, eq.diff, eq.price],
    })


def crossing_interval(table_10: pd.DataFrame) -> tuple[float, float]:
    """Сусідні значення Q з таблиці 10, між якими попит і пропозиція перетинаються."""
    q = table_10["Кількість товару"].to_numpy()
    d = (table_10["Попит"] - table_10["Пропозиція"]).to_numpy()
    idx = np.where(np.sign(d[:-1]) != np.sign(d[1:]))[0]
    if len(idx) == 0:
        raise ValueError("Криві не перетинаються на заданому проміжку")
    i = idx[0]
    return float(q[i]), float(q[i + 1])


def conclusion(eq: Equilibrium, interval: tuple[float, float]) -> str:
    """Текстовий висновок до завдання 3.2."""
    lo, hi = interval
    return (
        f"Числовим методом (brentq) знайдено рівноважний випуск Q* = {eq.q:.4f} "
        f"і ціну P* = {eq.price:.2f}. За таблицею 10 різниця «попит − пропозиція» "
        f"змінює знак між Q = {lo:g} та Q = {hi:g}, і саме в цьому проміжку на графіку "
        f"перетинаються криві попиту й пропозиції. Отже, розв'язок, знайдений підбором "
        f"параметра, збігається з точкою перетину кривих на графіку."
    )


def plot_market(table_10: pd.DataFrame, eq: Equilibrium, surname: str, path,
                y_max: float | None = None) -> None:
    """Будує графік «Товарний ринок» і зберігає його у файл (dpi=150)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    q = table_10["Кількість товару"]
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.plot(q, table_10["Попит"], "o-", label="Попит", color="#1f77b4")
    ax.plot(q, table_10["Пропозиція"], "s-", label="Пропозиція", color="#d62728")
    ax.plot(eq.q, eq.price, "o", color="black", markersize=9, zorder=5)
    ax.annotate(
        f"Рівновага\nQ* = {eq.q:.4f}\nP* = {eq.price:.2f}",
        xy=(eq.q, eq.price), xytext=(-130, 70), textcoords="offset points",
        arrowprops={"arrowstyle": "->"},
        bbox={"boxstyle": "round", "fc": "white", "ec": "gray"},
    )
    if y_max is None:
        y_max = max(1200.0, float(table_10["Попит"].max()) * 1.1)
    ax.set_ylim(0, y_max)
    ax.set_xlim(Q_MIN - 2, Q_MAX + 2)
    ax.set_title(f"Товарний ринок ({surname})")
    ax.set_xlabel("Кількість товару")
    ax.set_ylabel("Ціна товару")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def run(k: int) -> dict:
    """Виконує завдання 3.2 і повертає таблиці та результати."""
    t10 = build_table_10(k)
    eq = find_equilibrium(k)
    interval = crossing_interval(t10)
    return {
        "table_10": t10,
        "table_11": build_table_11(eq),
        "equilibrium": eq,
        "q_fsolve": find_equilibrium_fsolve(k),
        "q_bisection": bisection(k),
        "interval": interval,
        "conclusion": conclusion(eq, interval),
    }
