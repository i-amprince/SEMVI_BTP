import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np

def main():
    # 1. Load the Data
    df_default = pd.read_csv('csvs/default.csv')
    df_static = pd.read_csv('csvs/static.csv')
    df_dynamic = pd.read_csv('csvs/dynamic.csv')

    # 2. Define the metrics to plot and their readable titles
    metrics = {
        'LBF CPU': 'Load Balancing Factor (CPU)',
        'LBF Mem': 'Load Balancing Factor (Memory)',
        'LBF Pod': 'Load Balancing Factor (Pods)',
        'Total Power (W)': 'Avg Power Consumption (Watts)',
        'Avg Resource Fragmentation': 'Resource Fragmentation',
        'Active Nodes': 'Active Nodes Required'
    }

    # 3. Calculate the overall average for each metric across the simulation
    means_default = df_default.mean()
    means_static = df_static.mean()
    means_dynamic = df_dynamic.mean()

    # 4. Set up the Paper-Style 2x3 Grid Figure
    fig, axes = plt.subplots(2, 3, figsize=(16, 10))
    axes = axes.flatten()
    sns.set_theme(style="whitegrid")

    labels = ['Default', 'Static', 'Dynamic']
    
    # Paper-style color palette (Red, Blue, Green)
    colors = ['#e74c3c', '#3498db', '#2ecc71'] 

    # 5. Loop through each metric and generate its subplot
    for i, (col, title) in enumerate(metrics.items()):
        ax = axes[i]
        
        # Get the 3 values for the current metric
        values = [means_default[col], means_static[col], means_dynamic[col]]
        
        # Create the bars
        bars = ax.bar(labels, values, color=colors, edgecolor='black', alpha=0.85, width=0.6)
        
        # Formatting
        ax.set_title(title, fontsize=13, fontweight='bold', pad=12)
        ax.tick_params(axis='x', labelsize=12)
        
        # Add exact values on top of the bars
        for bar in bars:
            yval = bar.get_height()
            
            # Format the text depending on how large the number is
            if yval > 100:
                text = f"{yval:.0f}"
            elif yval > 10:
                text = f"{yval:.1f}"
            else:
                text = f"{yval:.4f}"
                
            ax.text(bar.get_x() + bar.get_width()/2, yval + (max(values)*0.02), 
                    text, ha='center', va='bottom', fontweight='bold', fontsize=11)
        
        # Add 20% headroom so the text doesn't hit the top of the subplot
        ax.set_ylim(0, max(values) * 1.25)
        
        # Add a subtle background grid for readability
        ax.grid(axis='y', linestyle='--', alpha=0.7)

    # 6. Final Polish and Save
    plt.tight_layout(pad=3.0)
    
    # Overall Title for the Figure
    plt.suptitle("Figure X: Comprehensive Performance Comparison Across Schedulers", 
                 fontsize=18, fontweight='bold', y=1.03)
    
    # Save as high-res PNG for the report
    filename = 'paper_reproduction_grid.png'
    plt.savefig(filename, dpi=300, bbox_inches='tight')
    print(f"✅ Success! Graph saved as '{filename}'")

if __name__ == "__main__":
    main()