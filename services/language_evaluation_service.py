def evaluate_language_predictions(rows, high_confidence_threshold=0.85):
    total = len(rows)
    predicted = [row for row in rows if row.get("predictedLanguage")]
    correct = [row for row in predicted if row.get("predictedLanguage") == row.get("expectedLanguage")]
    high_confidence = [row for row in predicted if float(row.get("confidence") or 0) >= high_confidence_threshold]
    high_correct = [row for row in high_confidence if row.get("predictedLanguage") == row.get("expectedLanguage")]
    confirmed = [row for row in rows if row.get("confirmedLanguage")]
    corrected = [row for row in confirmed if row.get("confirmedLanguage") != row.get("predictedLanguage")]
    return {
        "samples": total,
        "coverage": round(len(predicted) / total, 4) if total else 0,
        "accuracy": round(len(correct) / len(predicted), 4) if predicted else 0,
        "highConfidenceSamples": len(high_confidence),
        "highConfidenceAccuracy": round(len(high_correct) / len(high_confidence), 4) if high_confidence else 0,
        "confirmationRate": round(len(confirmed) / total, 4) if total else 0,
        "correctionRate": round(len(corrected) / len(confirmed), 4) if confirmed else 0,
    }


def release_gate(metrics, minimum_accuracy=0.9, minimum_coverage=0.9, minimum_high_confidence_accuracy=0.95, maximum_correction_rate=0.1):
    checks = {
        "accuracy": metrics.get("accuracy", 0) >= minimum_accuracy,
        "coverage": metrics.get("coverage", 0) >= minimum_coverage,
        "highConfidenceAccuracy": metrics.get("highConfidenceAccuracy", 0) >= minimum_high_confidence_accuracy,
        "correctionRate": metrics.get("correctionRate", 0) <= maximum_correction_rate,
    }
    return {"passed": all(checks.values()), "checks": checks, "metrics": metrics}
