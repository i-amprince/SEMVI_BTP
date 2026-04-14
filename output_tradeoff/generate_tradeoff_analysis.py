import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# ==========================================
# CONFIGURATION
# ==========================================
DATASET_PATH = "../ai_models/btp_master_full_dataset.csv" 
POWER_COL = "r_pow"
FRAG_COL = "r_node_frag"

def main():
    print(f"Reading {DATASET_PATH}...")
    try:
        df = pd.read_csv(DATASET_PATH)
    except FileNotFoundError:
        print("Error: Dataset file not found.")
        return

    # ==========================================
    # 1. CORRELATION
    # ==========================================
    correlation = df[POWER_COL].corr(df[FRAG_COL])
    print(f"Correlation (r): {correlation:.4f}")

    # Save correlation
    corr_results = pd.DataFrame({
        "Analysis": ["Power vs Fragmentation"],
        "Pearson_R": [round(correlation, 4)],
        "Interpretation": ["Negative Correlation" if correlation < 0 else "Positive Correlation"]
    })
    corr_results.to_csv("tradeoff_correlation.csv", index=False)

    # ==========================================
    # 2. PARETO FRONT (Minimize both)
    # ==========================================
    sorted_df = df.sort_values(by=[POWER_COL, FRAG_COL])

    pareto_x = []
    pareto_y = []
    min_frag_so_far = float('inf')

    for _, row in sorted_df.iterrows():
        if row[FRAG_COL] < min_frag_so_far:
            pareto_x.append(row[POWER_COL])
            pareto_y.append(row[FRAG_COL])
            min_frag_so_far = row[FRAG_COL]

    # ==========================================
    # 3. CLEAN VISUALIZATION (ONLY PARETO)
    # ==========================================
    plt.figure(figsize=(12, 7))
    sns.set_style("whitegrid")

    plt.plot(
        pareto_x,
        pareto_y,
        color='crimson',
        marker='o',
        linewidth=3,
        markersize=6
    )

    # Labels
    plt.title(
        "Trade-off Between Power Consumption and Resource Fragmentation",
        fontsize=15,
        pad=20
    )
    plt.xlabel("Total Power Consumption (r_pow) [Watts]", fontsize=12)
    plt.ylabel("Resource Fragmentation Score (r_node_frag)", fontsize=12)

    # Correlation annotation
    plt.annotate(
        f'Pearson r = {correlation:.2f} (Negative Correlation)',
        xy=(0.05, 0.05),
        xycoords='axes fraction',
        bbox=dict(boxstyle="round", fc="white", ec="gray")
    )

    plt.tight_layout()
    plt.savefig("pareto_tradeoff_clean.png", dpi=300)
    print("Saved: pareto_tradeoff_clean.png")
    plt.show()


if __name__ == "__main__":
    main()