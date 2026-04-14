import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import r2_score, mean_absolute_error
import joblib

print("--- 🌲 RANDOM FOREST TRAINING (POWER ONLY) ---")

try:
    df = pd.read_csv("btp_master_full_dataset.csv")
    print(f"Loaded {len(df)} rows from dataset.")
except FileNotFoundError:
    print("❌ Dataset not found. Ensure it is in the ai_model folder.")
    exit()

feature_cols = ['s_cpu', 's_mem', 's_node_frag', 's_active', 's_lbf_c', 's_lbf_m', 
                'b_cpu_avg', 'b_mem_avg', 'w_pod', 'w_cpu', 'w_mem', 'w_pow']
X = df[feature_cols]

# TARGET: ONLY Power (r_pow)
y = df['r_pow']

# Split data (80% training, 20% testing)
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# Train the Random Forest Model
print("Training Random Forest model (Predicting ONLY Power)...")
rf_model = RandomForestRegressor(n_estimators=150, random_state=42, n_jobs=-1)
rf_model.fit(X_train, y_train)

# Evaluate the Model
predictions = rf_model.predict(X_test)
r2 = r2_score(y_test, predictions)
mae = mean_absolute_error(y_test, predictions)

print("\n📊 --- MODEL EVALUATION METRICS ---")
print(f"R² Score (Accuracy): {r2:.4f} (1.0 is perfect)")
print(f"Mean Absolute Error: {mae:.2f} Watts")

# Save the model (Optional, since you only really need this for the R2 score)
filename = "btp_rf_power_only_brain.pkl"
joblib.dump(rf_model, filename)
print(f"\n✅ Training complete! Model saved as '{filename}'")