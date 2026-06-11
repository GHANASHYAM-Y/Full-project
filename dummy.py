import os
from model import load_model_if_exists, extract_embedding_for_image, predict_with_model

# 🔹 Load trained model
MODEL = load_model_if_exists()

# 🔹 CHANGE THIS TO YOUR TEST PATH
test_folder = r"C:\Ghana\Studies\projects\face detection full code - Copy\23_test"

correct = 0
wrong = 0
total = 0

print("\n===== TESTING STARTED =====\n")

for img in os.listdir(test_folder):
    path = os.path.join(test_folder, img)

    try:
        with open(path, "rb") as f:
            emb = extract_embedding_for_image(f)

        if emb is None:
            print(f"{img} → No face detected")
            continue

        pred, conf = predict_with_model(MODEL, emb)

        total += 1

        print(f"\nImage: {img}")
        print(f"Prediction: {pred}")
        print(f"Confidence: {round(conf, 3)}")

        # 🔥 EXPECTED = 23
        if str(pred) == "23":
            correct += 1
        else:
            wrong += 1

    except Exception as e:
        print(f"Error processing {img}: {e}")

# 🔹 FINAL RESULTS
print("\n===== RESULTS =====")
print("Total tested:", total)
print("Correct:", correct)
print("Wrong:", wrong)

if total > 0:
    accuracy = correct / total
    print("Accuracy:", round(accuracy * 100, 2), "%")