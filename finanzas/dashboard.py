"""
Dashboard financiero — julio 2026
Lee finanzas/movimientos.csv y genera resumen + gráficos.
Ejecutar: python finanzas/dashboard.py
"""
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from pathlib import Path

CSV_PATH = Path(__file__).parent / "movimientos.csv"
OUT_DIR = Path(__file__).parent / "output"
OUT_DIR.mkdir(exist_ok=True)


def cargar_movimientos():
    df = pd.read_csv(CSV_PATH, parse_dates=["Fecha"])
    df["Monto"] = pd.to_numeric(df["Monto"], errors="coerce")
    df = df.dropna(subset=["Monto"])
    df["Pendiente"] = df["Notas"].str.contains("PENDIENTE", na=False)
    return df


def resumen_texto(df):
    confirmados = df[~df["Pendiente"]]
    ingresos = confirmados[confirmados["Tipo"] == "Ingreso"]["Monto"].sum()
    gastos = confirmados[confirmados["Tipo"] == "Gasto"]["Monto"].sum()
    neto = ingresos + gastos

    print("=" * 52)
    print("  RESUMEN FINANCIERO — JULIO 2026")
    print("=" * 52)
    print(f"  Total ingresos (confirmados):  ${ingresos:>10.2f}")
    print(f"  Total gastos   (confirmados):  ${gastos:>10.2f}")
    print(f"  Neto:                          ${neto:>10.2f}")
    print()
    print("  GASTO POR CATEGORÍA (confirmados):")
    por_cat = (
        confirmados[confirmados["Tipo"] == "Gasto"]
        .groupby("Categoría")["Monto"]
        .sum()
        .sort_values()
    )
    for cat, monto in por_cat.items():
        print(f"    {cat:<35} ${monto:>8.2f}")
    print()
    print("  GASTO POR CUENTA (confirmados):")
    por_cuenta = (
        confirmados[confirmados["Tipo"] == "Gasto"]
        .groupby("Cuenta")["Monto"]
        .sum()
        .sort_values()
    )
    for cuenta, monto in por_cuenta.items():
        print(f"    {cuenta:<35} ${monto:>8.2f}")
    print()
    pendientes = df[df["Pendiente"]]
    if not pendientes.empty:
        print(f"  ⚠️  FILAS CON MONTO PENDIENTE: {len(pendientes)}")
        for _, row in pendientes.iterrows():
            monto_str = f"${row['Monto']:.2f}" if pd.notna(row["Monto"]) else "(sin monto)"
            print(f"    {row['Fecha'].date()} | {row['Cuenta']} | {row['Descripción'][:45]} | {monto_str}")
    print("=" * 52)
    return ingresos, gastos, neto, por_cat, por_cuenta


def graficar(df, por_cat, por_cuenta):
    confirmados = df[~df["Pendiente"]]
    gastos_df = confirmados[confirmados["Tipo"] == "Gasto"]

    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    fig.suptitle("Dashboard Financiero — Julio 2026", fontsize=14, fontweight="bold")

    # Gasto por categoría
    ax1 = axes[0]
    categorias = por_cat.abs()
    bars = ax1.barh(categorias.index, categorias.values, color="#e74c3c", alpha=0.8)
    ax1.set_title("Gasto por Categoría")
    ax1.set_xlabel("USD")
    ax1.xaxis.set_major_formatter(mticker.FormatStrFormatter("$%.0f"))
    for bar, val in zip(bars, categorias.values):
        ax1.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height() / 2,
                 f"${val:.2f}", va="center", fontsize=7)
    ax1.margins(x=0.2)

    # Gasto por cuenta
    ax2 = axes[1]
    cuentas = por_cuenta.abs()
    bars2 = ax2.barh(cuentas.index, cuentas.values, color="#3498db", alpha=0.8)
    ax2.set_title("Gasto por Cuenta")
    ax2.set_xlabel("USD")
    ax2.xaxis.set_major_formatter(mticker.FormatStrFormatter("$%.0f"))
    for bar, val in zip(bars2, cuentas.values):
        ax2.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height() / 2,
                 f"${val:.2f}", va="center", fontsize=7)
    ax2.margins(x=0.2)

    # Ingresos vs Gastos (pie)
    ax3 = axes[2]
    ingresos_total = confirmados[confirmados["Tipo"] == "Ingreso"]["Monto"].sum()
    gastos_total = gastos_df["Monto"].abs().sum()
    ax3.pie(
        [ingresos_total, gastos_total],
        labels=[f"Ingresos\n${ingresos_total:.2f}", f"Gastos\n${gastos_total:.2f}"],
        colors=["#2ecc71", "#e74c3c"],
        autopct="%1.1f%%",
        startangle=90,
    )
    ax3.set_title("Ingresos vs Gastos")

    plt.tight_layout()
    out_path = OUT_DIR / "dashboard_jul2026.png"
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"\n  Gráfico guardado: {out_path}")
    plt.close()


if __name__ == "__main__":
    df = cargar_movimientos()
    ingresos, gastos, neto, por_cat, por_cuenta = resumen_texto(df)
    graficar(df, por_cat, por_cuenta)
