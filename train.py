import argparse
import json
import random
import re
from pathlib import Path

import joblib
import numpy as np
from PIL import Image
from sklearn.metrics import accuracy_score, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.svm import LinearSVC


ROOT = Path(__file__).resolve().parent
MODEL_PATH = ROOT / "banana_leaf_model.joblib"
ACCURACY_PATH = ROOT / "accuracy.txt"
THRESHOLD_PATH = ROOT / "threshold.txt"
METRICS_PATH = ROOT / "training_metrics.json"
CLASS_NAMES = ("fusarium_wilt", "healthy", "natural_death_leaf", "rhizome_root")
IMAGE_SIZE = 24
TARGET_ACCEPTED_ACCURACY = 0.90


def extract_features(image):
    rgb = np.asarray(
        image.convert("RGB").resize((IMAGE_SIZE, IMAGE_SIZE), Image.Resampling.LANCZOS),
        dtype=np.float32,
    ) / 255.0
    gray = rgb.mean(axis=2)
    gradients = np.concatenate((np.diff(gray, axis=0).reshape(-1), np.diff(gray, axis=1).reshape(-1)))
    color_features = np.concatenate(
        [np.histogram(rgb[:, :, channel], bins=16, range=(0, 1), density=True)[0] for channel in range(3)]
    )
    return np.concatenate((rgb.reshape(-1), gradients, color_features)).astype(np.float32)


def _decision_signals(features, classifier):
    scores = np.asarray(classifier.decision_function(features))
    signals = np.exp(scores - np.max(scores, axis=1, keepdims=True))
    return signals / signals.sum(axis=1, keepdims=True)


def train_model(
    samples_per_class=60,
    model_path=MODEL_PATH,
    accuracy_path=ACCURACY_PATH,
    threshold_path=THRESHOLD_PATH,
    metrics_path=METRICS_PATH,
):
    if samples_per_class < 10:
        raise ValueError("Use at least 10 samples per class for a stratified validation split.")

    features = []
    labels = []
    rng = random.Random(23)
    for class_name in CLASS_NAMES:
        folder = ROOT / class_name
        originals = [path for path in folder.glob("*.jpg") if re.fullmatch(r"\d+", path.stem)]
        if not originals:
            raise RuntimeError(f"No original training images were found in {folder.name}.")
        rng.shuffle(originals)
        selected = originals[:samples_per_class]
        for image_path in selected:
            with Image.open(image_path) as image:
                features.append(extract_features(image))
            labels.append(class_name)
        print(f"Loaded {len(selected)} images for {class_name}.")

    train_features, validation_features, train_labels, validation_labels = train_test_split(
        np.asarray(features),
        np.asarray(labels),
        test_size=0.2,
        random_state=23,
        stratify=np.asarray(labels),
    )
    classifier = LinearSVC(class_weight="balanced", random_state=23, max_iter=5000)
    classifier.fit(train_features, train_labels)

    predictions = classifier.predict(validation_features)
    correct = predictions == validation_labels
    confidence_scores = np.round(_decision_signals(validation_features, classifier).max(axis=1) * 100, 1)
    confidence_threshold = 101.0
    for candidate in sorted(set(confidence_scores)):
        accepted = confidence_scores >= candidate
        if float(correct[accepted].mean()) >= TARGET_ACCEPTED_ACCURACY:
            confidence_threshold = float(candidate)
            break

    accepted = confidence_scores >= confidence_threshold
    accepted_count = int(accepted.sum())
    accepted_accuracy = float(correct[accepted].mean()) if accepted_count else 0.0
    overall_accuracy = float(accuracy_score(validation_labels, predictions))
    matrix = confusion_matrix(validation_labels, predictions, labels=CLASS_NAMES)
    per_class_metrics = []
    for index, class_name in enumerate(CLASS_NAMES):
        true_positive = int(matrix[index, index])
        false_positive = int(matrix[:, index].sum() - true_positive)
        false_negative = int(matrix[index, :].sum() - true_positive)
        true_negative = int(matrix.sum() - true_positive - false_positive - false_negative)
        precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
        recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
        specificity = true_negative / (true_negative + false_positive) if true_negative + false_positive else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_class_metrics.append(
            {
                "name": class_name,
                "support": int(matrix[index, :].sum()),
                "precision_pct": round(precision * 100, 1),
                "recall_pct": round(recall * 100, 1),
                "specificity_pct": round(specificity * 100, 1),
                "f1_pct": round(f1 * 100, 1),
            }
        )
    metrics = {
        "model": "LinearSVC",
        "classes": list(CLASS_NAMES),
        "training_samples": len(train_labels),
        "validation_samples": len(validation_labels),
        "accuracy_pct": round(overall_accuracy * 100, 1),
        "precision_pct": round(float(np.mean([item["precision_pct"] for item in per_class_metrics])), 1),
        "recall_pct": round(float(np.mean([item["recall_pct"] for item in per_class_metrics])), 1),
        "specificity_pct": round(float(np.mean([item["specificity_pct"] for item in per_class_metrics])), 1),
        "f1_pct": round(float(np.mean([item["f1_pct"] for item in per_class_metrics])), 1),
        "r2": None,
        "r2_note": "Not applicable: R-squared is a regression metric; this model predicts classes.",
        "confidence_threshold_pct": confidence_threshold,
        "accepted_accuracy_pct": round(accepted_accuracy * 100, 1),
        "accepted_samples": accepted_count,
        "per_class": per_class_metrics,
        "confusion_matrix": matrix.tolist(),
    }
    report = [
        "Banana leaf classifier validation report",
        "Model: LinearSVC",
        f"Original images per class: {samples_per_class}",
        f"Training images: {len(train_labels)}",
        f"Validation images: {len(validation_labels)}",
        f"Overall validation accuracy: {metrics['accuracy_pct']:.1f}%",
        f"Macro precision: {metrics['precision_pct']:.1f}%",
        f"Macro recall / sensitivity: {metrics['recall_pct']:.1f}%",
        f"Macro specificity: {metrics['specificity_pct']:.1f}%",
        f"Macro F1 score: {metrics['f1_pct']:.1f}%",
        "R2: N/A (R-squared is for regression, not classification)",
        f"Target accepted accuracy: {TARGET_ACCEPTED_ACCURACY * 100:.1f}%",
        f"Confidence threshold: {confidence_threshold:.1f}%",
        f"Accepted validation accuracy: {accepted_accuracy * 100:.1f}%",
        f"Accepted validation coverage: {accepted_count}/{len(validation_labels)}",
        "Confusion matrix (actual rows, predicted columns; order: " + ", ".join(CLASS_NAMES) + "):",
        "  " + " ".join(CLASS_NAMES),
    ]
    for class_name, row in zip(CLASS_NAMES, matrix.tolist()):
        report.append(f"  {class_name}: " + " ".join(str(value) for value in row))
    report.extend([
        "Per-class validation accuracy:",
    ])
    for class_name in CLASS_NAMES:
        class_mask = validation_labels == class_name
        class_accuracy = float(correct[class_mask].mean())
        report.append(
            f"  {class_name}: {class_accuracy * 100:.1f}% "
            f"({int(correct[class_mask].sum())}/{int(class_mask.sum())})"
        )

    joblib.dump(
        {
            "classifier": classifier,
            "image_size": IMAGE_SIZE,
            "confidence_threshold": confidence_threshold,
            "metrics": metrics,
        },
        model_path,
        compress=3,
    )
    Path(accuracy_path).write_text("\n".join(report) + "\n", encoding="utf-8")
    Path(threshold_path).write_text(f"{confidence_threshold:.1f}\n", encoding="ascii")
    Path(metrics_path).write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    return model_path


def load_classifier(model_path=MODEL_PATH):
    if not model_path.is_file():
        return None
    saved_model = joblib.load(model_path)
    if saved_model.get("image_size") != IMAGE_SIZE:
        raise RuntimeError("The saved classifier uses an incompatible image size. Run python train.py again.")
    return saved_model["classifier"]


def load_threshold(threshold_path=THRESHOLD_PATH):
    if not threshold_path.is_file():
        return None
    try:
        threshold = float(threshold_path.read_text(encoding="ascii").strip())
    except ValueError as error:
        raise RuntimeError("The threshold file must contain a numeric score. Run python train.py again.") from error
    if not 0 <= threshold <= 101:
        raise RuntimeError("The threshold must be between 0 and 101. Run python train.py again.")
    return threshold


def load_validation_accuracy(accuracy_path=ACCURACY_PATH):
    if not accuracy_path.is_file():
        return None
    for line in accuracy_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("Overall validation accuracy:"):
            return float(line.partition(":")[2].strip().rstrip("%"))
    return None


def load_training_metrics(metrics_path=METRICS_PATH):
    if not metrics_path.is_file():
        return None
    return json.loads(metrics_path.read_text(encoding="utf-8"))


def predict_image(image, classifier):
    features = extract_features(image).reshape(1, -1)
    signals = _decision_signals(features, classifier)[0]
    best_index = int(np.argmax(signals))
    return str(classifier.classes_[best_index]), round(float(signals[best_index]) * 100, 1)


def main():
    parser = argparse.ArgumentParser(description="Train the banana leaf image classifier.")
    parser.add_argument(
        "--samples-per-class",
        type=int,
        default=60,
        help="Number of original images to use from each class folder (default: 60).",
    )
    arguments = parser.parse_args()
    try:
        model_path = train_model(arguments.samples_per_class)
    except (RuntimeError, ValueError) as error:
        parser.error(str(error))
    print(f"Saved classifier to {model_path}")
    print(f"Saved validation results to {ACCURACY_PATH}")
    print(f"Saved confidence cutoff to {THRESHOLD_PATH}")
    print(f"Saved chart data to {METRICS_PATH}")


if __name__ == "__main__":
    main()
