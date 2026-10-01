"""Завдання 3.1 — вибір даних з таблиці (аналог розширеного фільтра Excel)."""

from __future__ import annotations

import pandas as pd

COLUMNS = [
    "База",
    "Магазин",
    "Товар",
    "Кількість поставленого товару",
    "Вартість поставленого товару",
]
QTY = COLUMNS[3]
COST = COLUMNS[4]


def build_prices(k: int) -> dict[str, float]:
    """Таблиця цін за одиницю товару (аналог Sheet2 в Excel)."""
    return {"Т1": k + 10, "Т2": 15, "Т4": 20, "Т5": k + 20}


def build_table_1(k: int) -> pd.DataFrame:
    """Таблиця 1: постачання товарів; вартість рахується через ціну (аналог VLOOKUP)."""
    rows = [
        ("Б1", "М1", "Т1", 10),
        ("Б1", "М1", "Т4", 60),
        ("Б1", "М2", "Т1", 5),
        ("Б3", "М1", "Т1", 15),
        ("Б3", "М2", "Т2", 2 * k),
        ("Б3", "М2", "Т4", k + 50),
        ("Б3", "М2", "Т5", 15),
        ("Б4", "М1", "Т1", 40),
    ]
    df = pd.DataFrame(rows, columns=COLUMNS[:4])
    df[COST] = df[QTY] * df["Товар"].map(build_prices(k))
    return df


def filter_and(df: pd.DataFrame, conditions: dict[str, str]) -> pd.DataFrame:
    """Рядки, що задовольняють УСІ умови «стовпець == значення» (критерії в одному рядку)."""
    mask = pd.Series(True, index=df.index)
    for column, value in conditions.items():
        mask &= df[column] == value
    return df[mask].reset_index(drop=True)


def filter_or(df: pd.DataFrame, column: str, values: list[str]) -> pd.DataFrame:
    """Рядки, у яких стовпець дорівнює ХОЧА Б ОДНОМУ зі значень (критерії в різних рядках)."""
    mask = pd.Series(False, index=df.index)
    for value in values:
        mask |= df[column] == value
    return df[mask].reset_index(drop=True)


def unique_values(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """Перелік значень стовпця без повторень (аналог «Лише унікальні записи»)."""
    return df[[column]].drop_duplicates().reset_index(drop=True)


def table_7(df: pd.DataFrame) -> pd.DataFrame:
    """Таблиця 7: постачання товару Т1 у магазин М1."""
    return filter_and(df, {"Магазин": "М1", "Товар": "Т1"})


def table_8(df: pd.DataFrame) -> pd.DataFrame:
    """Таблиця 8: постачання товарів Т1 та Т4."""
    return filter_or(df, "Товар", ["Т1", "Т4"])


def table_9(df: pd.DataFrame) -> pd.DataFrame:
    """Таблиця 9: перелік магазинів без повторень."""
    return unique_values(df, "Магазин")


def query_examples(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Ті самі умови, записані через df.query(...)."""
    return {
        'Магазин == "М1" and Товар == "Т1"': df.query('Магазин == "М1" and Товар == "Т1"').reset_index(drop=True),
        'Товар in ["Т1", "Т4"]': df.query('Товар in ["Т1", "Т4"]').reset_index(drop=True),
    }


def run(k: int) -> dict[str, pd.DataFrame]:
    """Виконує завдання 3.1 і повертає всі таблиці."""
    t1 = build_table_1(k)
    return {
        "table_1": t1,
        "prices": pd.DataFrame(list(build_prices(k).items()), columns=["Товар", "Ціна"]),
        "table_7": table_7(t1),
        "table_8": table_8(t1),
        "table_9": table_9(t1),
    }
