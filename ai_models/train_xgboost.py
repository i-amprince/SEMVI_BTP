import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.multioutput import MultiOutputRegressor
from sklearn.metrics import mean_absolute_error
import xgboost as xgb
import joblib

print("--- 🚀 XGBOOST TRAINING (DUAL-OBJECTIVE: POWER & FRAG) ---")

try:
    df = pd.read_csv("btp_master_full_dataset.csv")
    print(f"Loaded {len(df)} rows from dataset.")
except FileNotFoundError:
    print("❌ Dataset not found.")
    exit()

feature_cols = ['s_cpu', 's_mem', 's_node_frag', 's_active', 's_lbf_c', 's_lbf_m', 
                'b_cpu_avg', 'b_mem_avg', 'w_pod', 'w_cpu', 'w_mem', 'w_pow']
X = df[feature_cols]

# TARGET: BOTH Power and Fragmentation
y = df[['r_pow', 'r_node_frag']] 

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# Wrap XGBoost in a MultiOutputRegressor
print("Training Dual-Objective Model...")
base_model = xgb.XGBRegressor(n_estimators=150, learning_rate=0.1, max_depth=6)
multi_model = MultiOutputRegressor(base_model)
multi_model.fit(X_train, y_train)

# Test the model
preds = multi_model.predict(X_test)
mae_pow = mean_absolute_error(y_test['r_pow'], preds[:, 0])
mae_frag = mean_absolute_error(y_test['r_node_frag'], preds[:, 1])

print(f"✅ Training Complete!")
print(f"Power Prediction Error: ±{mae_pow:.2f} W")
print(f"Fragmentation Prediction Error: ±{mae_frag:.4f}")

joblib.dump(multi_model, "btp_xgboost_brain.pkl")
print("💾 Saved as btp_xgboost_brain.pkl")