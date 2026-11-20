# Kirana Vision Evaluation Samples

Place real or synthetic photos of Kirana ledger pages, UPI payment screenshots, and supplier bills here to evaluate the Gemini vision extraction model accuracy.

## File Format
For each test image:
1. `name.jpg` (or `.png` / `.webp`): The photo of the document.
2. `name.json`: The ground truth extracted data in this structure:

```json
{
  "doc_type": "khata_page",
  "total_shown": 540.0,
  "lines": [
    {
      "customer_name": "Ramesh",
      "type": "credit",
      "amount": 340.0,
      "date": "2026-11-18",
      "note": "Rice 5kg"
    },
    {
      "customer_name": "Suresh",
      "type": "payment",
      "amount": 200.0,
      "date": "2026-11-18",
      "note": "Cash"
    }
  ]
}
```

## Running Evaluation
From `dukaan-ai/backend`:
```bash
python tests/vision_eval.py
```
This will call the live Gemini Vision API on each sample photo and calculate:
- Document Type Accuracy (%)
- Customer Name Accuracy (%)
- Amount & Transaction Accuracy (%)
- Overall Exact Match (%)

