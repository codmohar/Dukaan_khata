"""Evaluation runner for Gemini Vision extraction on Kirana khata photos and bills.

Loops over `backend/tests/samples/*.jpg` with matching `*.json` ground truth,
calls live `extract()`, and prints per-image name accuracy and amount accuracy.

Usage:
  cd dukaan-ai/backend
  python tests/vision_eval.py
"""
import asyncio
import json
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.tools import normalize_customer_query
from app.services.vision import Extraction, extract

SAMPLES_DIR = Path(__file__).resolve().parent / "samples"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def score_image_extraction(pred: Extraction, ground_truth: dict) -> dict:
    gt_lines = ground_truth.get("lines", [])
    pred_lines = pred.lines

    doc_type_match = pred.doc_type == ground_truth.get("doc_type")

    if not gt_lines and not pred_lines:
        return {
            "doc_type_match": doc_type_match,
            "gt_count": 0,
            "pred_count": 0,
            "name_accuracy": 100.0,
            "amount_accuracy": 100.0,
            "matched_lines": 0,
        }

    matched_names = 0
    matched_amounts = 0

    # Greedy pair matching between ground truth and predicted lines
    unmatched_preds = list(pred_lines)
    for gt in gt_lines:
        gt_name = normalize_customer_query(gt.get("customer_name") or "").lower()
        gt_amt = float(gt.get("amount", 0.0))

        best_idx = -1
        best_dist = float("inf")

        for idx, p in enumerate(unmatched_preds):
            dist = abs(float(p.amount) - gt_amt)
            if dist < best_dist:
                best_dist = dist
                best_idx = idx

        if best_idx >= 0 and best_dist <= max(2.0, gt_amt * 0.02):
            matched_amounts += 1
            p = unmatched_preds.pop(best_idx)
            p_name = normalize_customer_query(p.customer_name or "").lower()
            if gt_name and p_name and (gt_name in p_name or p_name in gt_name):
                matched_names += 1
        elif best_idx >= 0:
            p = unmatched_preds.pop(best_idx)
            p_name = normalize_customer_query(p.customer_name or "").lower()
            if gt_name and p_name and (gt_name in p_name or p_name in gt_name):
                matched_names += 1

    total_gt = max(len(gt_lines), 1)
    name_acc = round((matched_names / total_gt) * 100.0, 1)
    amt_acc = round((matched_amounts / total_gt) * 100.0, 1)

    return {
        "doc_type_match": doc_type_match,
        "gt_count": len(gt_lines),
        "pred_count": len(pred_lines),
        "name_accuracy": name_acc,
        "amount_accuracy": amt_acc,
        "matched_names": matched_names,
        "matched_amounts": matched_amounts,
    }


async def main():
    if not SAMPLES_DIR.exists():
        print(f"Samples directory {SAMPLES_DIR} does not exist.")
        return

    image_files = sorted(
        [p for p in SAMPLES_DIR.iterdir() if p.suffix.lower() in IMAGE_EXTS]
    )

    if not image_files:
        print(
            f"No sample images found in {SAMPLES_DIR}.\n"
            f"Add .jpg photos with matching .json ground truth files to run vision evaluation.\n"
            f"See {SAMPLES_DIR / 'README.md'} for instructions."
        )
        return

    print(f"Found {len(image_files)} sample image(s) in {SAMPLES_DIR}...\n")
    print(f"{'Image File':<25} | {'DocType':<12} | {'Lines (GT/Pred)':<16} | {'Name Acc':<10} | {'Amount Acc':<10}")
    print("-" * 80)

    total_gt_lines = 0
    total_names_matched = 0
    total_amts_matched = 0
    evaluated_count = 0

    today = date.today().isoformat()

    for img_path in image_files:
        gt_path = img_path.with_suffix(".json")
        if not gt_path.exists():
            print(f"{img_path.name:<25} | SKIPPED (no matching {gt_path.name} ground truth)")
            continue

        with open(gt_path, "r", encoding="utf-8") as f:
            gt_data = json.load(f)

        mime = "image/jpeg" if img_path.suffix.lower() in (".jpg", ".jpeg") else f"image/{img_path.suffix.lower().strip('.')}"
        img_bytes = img_path.read_bytes()

        try:
            pred = await extract(img_bytes, mime, None, today)
            score = score_image_extraction(pred, gt_data)
            evaluated_count += 1
            total_gt_lines += score["gt_count"]
            total_names_matched += score.get("matched_names", 0)
            total_amts_matched += score.get("matched_amounts", 0)

            doc_tag = "✓ " + pred.doc_type if score["doc_type_match"] else "✗ " + pred.doc_type
            counts = f"{score['gt_count']} / {score['pred_count']}"
            print(
                f"{img_path.name:<25} | {doc_tag:<12} | {counts:<16} | "
                f"{score['name_accuracy']:>8.1f}% | {score['amount_accuracy']:>8.1f}%"
            )
        except Exception as e:
            print(f"{img_path.name:<25} | ERROR: {e}")

    if evaluated_count > 0 and total_gt_lines > 0:
        overall_name = round((total_names_matched / total_gt_lines) * 100.0, 1)
        overall_amt = round((total_amts_matched / total_gt_lines) * 100.0, 1)
        print("-" * 80)
        print(f"Overall Accuracy Across {evaluated_count} Photo(s):")
        print(f"  Customer Names: {overall_name}% ({total_names_matched}/{total_gt_lines})")
        print(f"  Amounts/Values: {overall_amt}% ({total_amts_matched}/{total_gt_lines})")


if __name__ == "__main__":
    asyncio.run(main())

