import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import os

def main():
    print("📊 Generating Fixed 24-Hour Diurnal Comparison Graph...")

    # 1. Load the Data
    try:
        df_default = pd.read_csv("diurnal_default.csv")
        df_dynamic = pd.read_csv("diurnal_dynamic.csv")
    except FileNotFoundError as e:
        print(f"❌ Error: Could not find one of the CSV files. {e}")
        return

    # Set academic plotting style
    sns.set_theme(style="whitegrid")
    plt.rcParams.update({'font.size': 12})

    # --- THE FIX: Map the 8 simulation steps to 24 hours ---
    # This multiplies the steps (0, 1, 2...) by 3 to create 3-hour intervals 
    # Result: 00:00, 03:00, 06:00, 09:00, 12:00, 15:00, 18:00, 21:00
    hours_24 = df_dynamic['Hour'] * 3 

    traffic_pods = df_dynamic['Target Pods']
    power_default = df_default['Total Power (W)']
    power_dynamic = df_dynamic['Total Power (W)']

    # 2. Set up the Dual-Axis Figure
    fig, ax1 = plt.subplots(figsize=(12, 6))

    # X-Axis configuration (Now using hours_24)
    ax1.set_xlabel('Time of Day (24-Hour Cycle)', fontweight='bold', fontsize=12)
    ax1.set_xticks(hours_24)
    ax1.set_xticklabels([f"{int(h):02d}:00" for h in hours_24], rotation=45)

    # Plot 1: Power Consumption (Left Y-Axis)
    ax1.set_ylabel('Total Power Consumption (Watts)', fontweight='bold', fontsize=12)
    
    line1 = ax1.plot(hours_24, power_default, label='Default Scheduler (Rigid)', 
                     color='#e74c3c', linewidth=3, linestyle='--', marker='s', markersize=7)
    
    line2 = ax1.plot(hours_24, power_dynamic, label='Dynamic AI Scheduler (Smart)', 
                     color='#2ecc71', linewidth=3, marker='o', markersize=8)
    
    max_power = max(power_default.max(), power_dynamic.max())
    ax1.set_ylim(0, max_power * 1.2)

    # Plot 2: Simulated Traffic Load (Right Y-Axis)
    ax2 = ax1.twinx()  
    ax2.set_ylabel('Cluster Workload (Active Pods)', color='#3498db', fontweight='bold', fontsize=12)
    
    line3 = ax2.plot(hours_24, traffic_pods, label='Incoming Traffic Load', 
                     color='#3498db', linewidth=2, alpha=0.7)
    ax2.fill_between(hours_24, traffic_pods, color='#3498db', alpha=0.1)
    
    ax2.set_ylim(0, traffic_pods.max() * 1.5)

    # 3. Combine Legends and Format
    lines = line1 + line2 + line3
    labels = [l.get_label() for l in lines]
    ax1.legend(lines, labels, loc='upper left', frameon=True, shadow=True, fontsize=11)

    plt.title('24-Hour Diurnal Simulation: AI Power Adaptation vs. Default Rigid Scaling', 
              fontweight='bold', fontsize=14, pad=15)
    plt.tight_layout()

    # 4. Save High-Res Image
    filename = 'report_diurnal_final.png'
    plt.savefig(filename, dpi=300)
    print(f"✅ Success! Fixed 24-hour graph saved as '{filename}'")

if __name__ == "__main__":
    main()