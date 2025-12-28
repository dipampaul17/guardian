"""
Visualization script for threshold sensitivity analysis.

Run this script to generate ROC and Precision-Recall curves:
    python /Users/dipam.paul/Downloads/guardian/experiments/results/plot_curves.py
    
Requires: matplotlib, pandas
"""

import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

# Load metrics
metrics = pd.read_csv("/Users/dipam.paul/Downloads/guardian/experiments/results/threshold_analysis_metrics_20251228_012943.csv")

# Create figure with subplots
fig, axes = plt.subplots(1, 3, figsize=(18, 5))

# ===== ROC Curve =====
ax = axes[0]
ax.plot(metrics['fpr'], metrics['tpr'], 'b-o', linewidth=2, markersize=4, label='Parity')
ax.plot([0, 1], [0, 1], 'r--', linewidth=1, label='Random')
ax.set_xlabel('False Positive Rate', fontsize=12)
ax.set_ylabel('True Positive Rate (Recall)', fontsize=12)
ax.set_title('ROC Curve', fontsize=14, fontweight='bold')
ax.legend()
ax.grid(alpha=0.3)

# ===== Precision-Recall Curve =====
ax = axes[1]
ax.plot(metrics['recall'], metrics['precision'], 'g-o', linewidth=2, markersize=4)
ax.set_xlabel('Recall', fontsize=12)
ax.set_ylabel('Precision', fontsize=12)
ax.set_title('Precision-Recall Curve', fontsize=14, fontweight='bold')
ax.grid(alpha=0.3)

# ===== F1 vs Threshold =====
ax = axes[2]
ax.plot(metrics['threshold'], metrics['f1'], 'm-o', linewidth=2, markersize=4, label='F1')
ax.plot(metrics['threshold'], metrics['precision'], 'b--', linewidth=1, label='Precision')
ax.plot(metrics['threshold'], metrics['recall'], 'r--', linewidth=1, label='Recall')

# Mark current threshold
ax.axvline(x=5.0, color='orange', linestyle=':', linewidth=2, label='Current (5.0)')

# Mark optimal threshold
optimal_idx = metrics['f1'].idxmax()
optimal_value = metrics.loc[optimal_idx, 'threshold']
ax.axvline(x=optimal_value, color='green', linestyle=':', linewidth=2, label=f'Optimal ({optimal_value:.1f})')

ax.set_xlabel('Threshold', fontsize=12)
ax.set_ylabel('Score', fontsize=12)
ax.set_title('Metrics vs Threshold', fontsize=14, fontweight='bold')
ax.legend()
ax.grid(alpha=0.3)

plt.tight_layout()
output_file = "/Users/dipam.paul/Downloads/guardian/experiments/results/threshold_analysis_curves.png"
plt.savefig(output_file, dpi=300, bbox_inches='tight')
print(f"\n✓ Curves saved to: {output_file}")
plt.show()
