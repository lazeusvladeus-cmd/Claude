"""Лабораторна робота №3 (ІКТ) мовою Python. Точка входу.

Приклад: python main.py --k 7 --surname Колеснік
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

import task_3_1_filter
import task_3_2_market
import task_3_3_linear
from report import save_all

try:
    from tabulate import tabulate
except ImportError:  # tabulate необов'язковий
    tabulate = None

LINE = "=" * 78


def show(df: pd.DataFrame, floatfmt: str | tuple[str, ...] = ".2f") -> str:
    """Форматує таблицю для консолі."""
    if tabulate:
        return tabulate(df, headers="keys", tablefmt="github", showindex=False,
                        floatfmt=floatfmt)
    return df.to_string(index=False)


def fmt_matrix(M: np.ndarray, fmt: str = "10.4f") -> str:
    """Форматує матрицю або вектор для консолі."""
    M = np.atleast_2d(M)
    return "\n".join("  [" + " ".join(format(v, fmt) for v in r) + " ]" for r in M)


def header(title: str) -> None:
    print(f"\n{LINE}\n{title}\n{LINE}")


def sub(title: str) -> None:
    print(f"\n--- {title} ---")


def report_3_1(r: dict) -> None:
    header("ЗАВДАННЯ 3.1. Вибір даних з таблиці (розширений фільтр)")
    sub("Ціни за одиницю товару (аналог Sheet2, використовується як VLOOKUP)")
    print(show(r["prices"]))
    sub("Таблиця 1. Постачання товарів")
    print(show(r["table_1"]))
    sub("Таблиця 7. Товар Т1 у магазин М1  (Магазин == М1 І Товар == Т1)")
    print(show(r["table_7"]))
    sub("Таблиця 8. Товари Т1 та Т4  (Товар == Т1 АБО Товар == Т4)")
    print(show(r["table_8"]))
    sub("Таблиця 9. Перелік магазинів без повторень")
    print(show(r["table_9"]))
    sub("Ті самі умови через df.query(...)")
    for expr, df in task_3_1_filter.query_examples(r["table_1"]).items():
        print(f"df.query('{expr}') -> {len(df)} рядк(ів)")


def report_3_2(r: dict) -> None:
    header("ЗАВДАННЯ 3.2. Попит, пропозиція, рівновага (підбір параметра)")
    sub("Таблиця 10. Попит і пропозиція")
    print(show(r["table_10"], (".0f", ".2f", ".2f")))
    sub("Таблиця 11. Рівновага (scipy.optimize.brentq — аналог Goal Seek)")
    eq = r["equilibrium"]
    print(f"Рівноважний випуск Q*         = {eq.q:.4f}")
    print(f"P1 = 1000·k/Q* (попит)        = {eq.p1:.2f}")
    print(f"P2 = e^(Q*/10) (пропозиція)   = {eq.p2:.2f}")
    print(f"Різниця P1 − P2               = {eq.diff:.2e}")
    print(f"Ціна рівноваги P*             = {eq.price:.2f}")
    sub("Порівняння числових методів")
    print(f"brentq:   Q* = {eq.q:.4f}")
    print(f"fsolve:   Q* = {r['q_fsolve']:.4f}")
    print(f"бісекція: Q* = {r['q_bisection']:.4f}")
    sub("Висновок")
    print(r["conclusion"])


def report_3_3(r: dict) -> None:
    header("ЗАВДАННЯ 3.3. Система лінійних рівнянь")
    sub("Матриця A")
    print(fmt_matrix(r["A"], "6.0f"))
    sub("Вектор b")
    print(fmt_matrix(r["b"], "6.0f"))
    sub("Метод 1. Обернена матриця: x = A⁻¹·b")
    print(f"det(A) = {r['delta']:.4f} ≠ 0, отже обернена матриця існує")
    print("A⁻¹ =")
    print(fmt_matrix(r["A_inv"]))
    print("x =", fmt_matrix(r["x_inverse"]).strip())
    sub("Метод 2. Метод Крамера: xᵢ = Δᵢ / Δ")
    for i, Ai in enumerate(r["cramer_matrices"], start=1):
        print(f"A{i} =")
        print(fmt_matrix(Ai, "6.0f"))
    print(f"Δ  = {r['delta']:.4f}")
    for i, d in enumerate(r["deltas"], start=1):
        print(f"Δ{i} = {d:.4f}")
    for i, x in enumerate(r["x_cramer"], start=1):
        print(f"x{i} = Δ{i}/Δ = {x:.4f}")
    sub("Перевірка")
    print("A·x − b (обернена):", fmt_matrix(r["residual_inverse"], ".2e").strip())
    print("A·x − b (Крамер):  ", fmt_matrix(r["residual_cramer"], ".2e").strip())
    print("numpy.linalg.solve:", fmt_matrix(r["x_numpy"]).strip())
    print(f"A·x ≈ b (обернена): {'так' if r['check_inverse'] else 'ні'}")
    print(f"A·x ≈ b (Крамер):   {'так' if r['check_cramer'] else 'ні'}")
    print(f"Розв'язки всіх методів збігаються: {'так' if r['methods_agree'] else 'ні'}")


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Лабораторна робота №3 (ІКТ) на Python")
    parser.add_argument("--k", type=int, default=7, help="номер студента в журналі (за замовчуванням 7)")
    parser.add_argument("--surname", default="Колеснік", help="прізвище виконавця")
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "output",
                        help="папка для результатів")
    args = parser.parse_args(argv)
    if args.k <= 0:
        parser.error("k має бути додатним цілим числом")
    return args


def main(argv=None) -> None:
    args = parse_args(argv)
    print(LINE)
    print(f"Лабораторна робота №3. Виконав(ла): {args.surname}. Варіант k = {args.k}")
    print(LINE)

    r31 = task_3_1_filter.run(args.k)
    r32 = task_3_2_market.run(args.k)
    r33 = task_3_3_linear.run(args.k)
    report_3_1(r31)
    report_3_2(r32)
    report_3_3(r33)

    paths = save_all(r31, r32, r33, args.k, args.surname, args.output)
    header("Збережені файли")
    for path in paths.values():
        print(f"  {path}")


if __name__ == "__main__":
    main()
