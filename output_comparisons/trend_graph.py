import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

def main():
    # 1. Load Data
    try:
        df_default = pd.read_csv('csvs/default.csv')
        df_static = pd.read_csv('csvs/static.csv')
        df_dynamic = pd.read_csv('csvs/testing_delete.csv')
    except FileNotFoundError as e:
        print(f"Error: Could not find CSV file. {e}")
        return

    sns.set_theme(style="whitegrid")
    plt.rcParams.update({'font.size': 12, 'axes.titlesize': 14, 'axes.labelsize': 13})

    plot_styles = [
        {'label': 'Default Scheduler', 'color': '#e74c3c', 'marker': 'o'},   # Red
        {'label': 'Static Weights', 'color': '#3498db', 'marker': 's'},      # Blue
        {'label': 'Dynamic (Proposed)', 'color': '#2ecc71', 'marker': '^'}   # Green
    ]

    datasets = [df_default, df_static, df_dynamic]

    # ==========================================
    # GRAPH 1: Power Scalability Trend
    # ==========================================
    plt.figure(figsize=(9, 6))
    for df, style in zip(datasets, plot_styles):
        plt.plot(df['Total Pods'], df['Total Power (W)'], 
                 label=style['label'], color=style['color'], 
                 marker=style['marker'], linewidth=2.5, markersize=8)

    plt.title("Power Consumption Scalability vs. Workload", fontweight='bold', pad=15)
    plt.xlabel("Total Scheduled Pods", fontweight='bold')
    plt.ylabel("Total Power Consumption (Watts)", fontweight='bold')
    plt.ylim(ymin=0) 
    plt.legend(frameon=True, shadow=True, fontsize=11)
    plt.tight_layout()
    plt.savefig('report_trend_power.png', dpi=300)
    print("✅ Generated 'report_trend_power.png'")

    # ==========================================
    # GRAPH 2: Cluster Stability (LBF CPU)
    # ==========================================
    # LBF (Load Balancing Factor) measures variance. A lower/stable number is better.
    plt.figure(figsize=(9, 6))
    for df, style in zip(datasets, plot_styles):
        plt.plot(df['Total Pods'], df['LBF CPU'], 
                 label=style['label'], color=style['color'], 
                 marker=style['marker'], linewidth=2.5, markersize=8)

    plt.title("Cluster Stability: CPU Load Balancing Factor vs. Workload", fontweight='bold', pad=15)
    plt.xlabel("Total Scheduled Pods", fontweight='bold')
    plt.ylabel("CPU Load Balancing Factor (LBF)", fontweight='bold')
    plt.ylim(ymin=0)
    plt.legend(frameon=True, shadow=True, fontsize=11)
    plt.tight_layout()
    plt.savefig('report_trend_lbf.png', dpi=300)
    print("✅ Generated 'report_trend_lbf.png'")

if __name__ == "__main__":
    main()