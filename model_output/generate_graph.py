import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import os

# --- CONFIGURATION ---
# Define the names of your 4 CSV files and the label you want on the graph
# Update these filenames if yours are slightly different!
FILES = {
    "Regression": "results_linear_regression.csv",
    "Decision Tree": "results_decision_tree.csv",
    "Random Forest": "results_random_forest.csv",
    "XGBoost (Proposed)": "results_xgboost.csv"
}

# Set academic plotting style
sns.set_theme(style="whitegrid")
plt.rcParams.update({'font.size': 12, 'axes.titlesize': 14, 'axes.labelsize': 12})

# --- DATA LOADING ---
dataframes = {}
for label, filename in FILES.items():
    if os.path.exists(filename):
        dataframes[label] = pd.read_csv(filename)
    else:
        print(f"⚠️ Warning: {filename} not found. Skipping {label}.")

if not dataframes:
    print("❌ No CSV files found! Please check the filenames in the script.")
    exit()

# Ensure output directory exists
os.makedirs("report_graphs", exist_ok=True)

# =====================================================================
# GRAPH 1: Power Consumption vs. Cluster Load (Line Chart)
# Why it matters: Shows how your AI saves power dynamically as load increases.
# =====================================================================
plt.figure(figsize=(10, 6))
markers = ['o', 's', '^', 'D']

for (label, df), marker in zip(dataframes.items(), markers):
    plt.plot(df['Batch'], df['Total Power (W)'], marker=marker, linewidth=2, label=label)

plt.title("Total Cluster Power Consumption vs. Incoming Workload (Batches)")
plt.xlabel("Workload Batch (50 Pods per Batch)")
plt.ylabel("Total Power (Watts)")
plt.legend(title="Scheduling Algorithm")
plt.tight_layout()
plt.savefig("report_graphs/1_Power_Trend.png", dpi=300)
print("✅ Saved Graph 1: Power Trend")

# =====================================================================
# GRAPH 2: Unscheduled Pods Limit (The Hardware Ceiling)
# Why it matters: Proves that your power savings don't break the cluster SLA.
# =====================================================================
plt.figure(figsize=(10, 6))

for (label, df), marker in zip(dataframes.items(), markers):
    plt.plot(df['Batch'], df['Unscheduled'], marker=marker, linewidth=2, label=label)

plt.title("Cluster Capacity: Unscheduled Pods vs. Workload")
plt.xlabel("Workload Batch (50 Pods per Batch)")
plt.ylabel("Number of Unscheduled Pods")
plt.axhline(y=0, color='black', linestyle='--', linewidth=1) # Baseline 0
plt.legend(title="Scheduling Algorithm")
plt.tight_layout()
plt.savefig("report_graphs/2_Capacity_Trend.png", dpi=300)
print("✅ Saved Graph 2: Capacity Trend")

# =====================================================================
# GRAPH 3: The "First Row" Bar Chart (Low-Load Power Comparison)
# Why it matters: Highlight the massive power savings when the cluster is mostly empty.
# =====================================================================
plt.figure(figsize=(8, 6))

labels = []
first_row_powers = []
colors = ['#e74c3c', '#f39c12', '#3498db', '#2ecc71'] # Red, Orange, Blue, Green

for label, df in dataframes.items():
    labels.append(label)
    # Get the "Total Power (W)" from the very first row (Batch 1)
    power_val = df.iloc[1]['Total Power (W)']
    first_row_powers.append(power_val)

bars = plt.bar(labels, first_row_powers, color=colors[:len(labels)], edgecolor='black')

# Add the exact numbers on top of the bars
for bar in bars:
    yval = bar.get_height()
    plt.text(bar.get_x() + bar.get_width()/2, yval + 15, f"{yval:.0f} W", ha='center', va='bottom', fontweight='bold')

plt.title("Power Consumption at Initial Low-Load State (Batch 1)")
plt.ylabel("Total Power (Watts)")
plt.ylim(0, max(first_row_powers) * 1.2) # Add some headroom for labels
plt.tight_layout()
plt.savefig("report_graphs/3_First_Row_Bar.png", dpi=300)
print("✅ Saved Graph 3: Low-Load Bar Chart")

# =====================================================================
# GRAPH 4: Average Resource Fragmentation (Line Chart)
# Why it matters: Compares how well the algorithms pack the nodes.
# =====================================================================
plt.figure(figsize=(10, 6))

for (label, df), marker in zip(dataframes.items(), markers):
    if 'Avg Resource Fragmentation' in df.columns:
        plt.plot(df['Batch'], df['Avg Resource Fragmentation'], marker=marker, linewidth=2, label=label)

plt.title("Average Resource Fragmentation vs. Workload")
plt.xlabel("Workload Batch (50 Pods per Batch)")
plt.ylabel("Fragmentation Penalty Score")
plt.legend(title="Scheduling Algorithm")
plt.tight_layout()
plt.savefig("report_graphs/4_Fragmentation_Trend.png", dpi=300)
print("✅ Saved Graph 4: Fragmentation Trend")

print("\n🎉 All graphs have been generated and saved in the 'report_graphs' folder!")