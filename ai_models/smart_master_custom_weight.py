from flask import Flask, jsonify
import logging

app = Flask(__name__)
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

current_weights = {"pods": 0.25, "cpu": 0.25, "memory": 0.25, "power": 0.25}

@app.route('/get_weights', methods=['GET'])
def get_weights():
    return jsonify(current_weights)

if __name__ == "__main__":
    print("--- MANUAL WEIGHT OVERRIDE MODE ---")
    try:
        w_p = float(input("Enter weight for Pods: "))
        w_c = float(input("Enter weight for CPU: "))
        w_m = float(input("Enter weight for Memory: "))
        w_pow = float(input("Enter weight for Power: "))
        
        # Normalize the weights so they always sum to 1.0
        total = w_p + w_c + w_m + w_pow
        if total == 0:
            raise ValueError("Total sum cannot be zero.")
            
        current_weights = {
            "pods": w_p / total,
            "cpu": w_c / total,
            "memory": w_m / total,
            "power": w_pow / total
        }
        
        print(f"\nServing normalized weights on port 5000: {current_weights}")
    except ValueError:
        print("\nInvalid input detected. Serving default weights (0.25 each).")

    app.run(host='0.0.0.0', port=5000, use_reloader=False)