import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score, mean_absolute_error
import joblib

print("--- 📈 LINEAR REGRESSION TRAINING (POWER ONLY) ---")

# Load Dataset (Assuming it is now inside the ai_model folder)
try:
    df = pd.read_csv("btp_master_full_dataset.csv")
    print(f"Loaded {len(df)} rows from dataset.")
except FileNotFoundError:
    print("❌ Dataset not found. Ensure it is in the ai_model folder.")
    exit()

# Define Features
feature_cols = ['s_cpu', 's_mem', 's_node_frag', 's_active', 's_lbf_c', 's_lbf_m', 
                'b_cpu_avg', 'b_mem_avg', 'w_pod', 'w_cpu', 'w_mem', 'w_pow']
X = df[feature_cols]

# TARGET: ONLY Power (r_pow)
y = df['r_pow']

# Split data to test accuracy (80% training, 20% testing)
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# Train the Linear Regression Model
print("Training Linear Regression model...")
lr_model = LinearRegression()
lr_model.fit(X_train, y_train)

# Evaluate the Model (Crucial for your report)
predictions = lr_model.predict(X_test)
r2 = r2_score(y_test, predictions)
mae = mean_absolute_error(y_test, predictions)

print("\n📊 --- MODEL EVALUATION METRICS ---")
print(f"R² Score (Accuracy): {r2:.4f} (1.0 is perfect)")
print(f"Mean Absolute Error: {mae:.2f} Watts")

# Save the model
filename = "btp_linear_brain.pkl"
joblib.dump(lr_model, filename)
print(f"\n✅ Training complete! Linear Model saved as '{filename}'")