import pandas as pd
import joblib
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score

# 1. Load your 3000-row dataset
df = pd.read_csv('btp_perfect_dataset.csv')

# 2. Define Features (What the AI sees) and Targets (What the AI predicts)
# State + The Weights chosen = The Outcome
features = ['s_cpu', 's_mem', 's_frag', 'w_pod', 'w_cpu', 'w_mem', 'w_pow']
targets = ['r_frag', 'r_unsched', 'r_pow', 'r_lbf_c', 'r_lbf_m']

X = df[features]
y = df[targets]

# 3. Split Data (80% Training, 20% Testing)
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# 4. Train the Multi-Output Random Forest
print("Training the Power-Aware Model...")
model = RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)
model.fit(X_train, y_train)

# 5. Evaluate
predictions = model.predict(X_test)
print(f"Model Training Complete.")
print(f"R2 Score (Accuracy): {r2_score(y_test, predictions):.4f}")
print(f"Mean Absolute Error: {mean_absolute_error(y_test, predictions):.4f}")

# 6. Save the model for your scheduler to use
joblib.dump(model, 'btp_model.pkl')
print("✅ Model saved as 'btp_model.pkl'")