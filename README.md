# Banana Tree

A local Flask app for screening banana plant images, viewing held-out model metrics, and tracking saved predictions.

## Run locally

```powershell
python -m pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000`. The local demo account is `demo@bananatree.local` with password `banana123`.

## Retrain

The trained model is included. To retrain, put the four labeled image folders at the project root: `fusarium_wilt`, `healthy`, `natural_death_leaf`, and `rhizome_root`. The trainer reads original `.jpg` files named with numeric stems (for example, `1.jpg`) and excludes augmented variants.

```powershell
python train.py
```

The training script updates `banana_leaf_model.joblib`, `accuracy.txt`, `threshold.txt`, and `training_metrics.json`. The validation report is based on a held-out split and is not a guarantee of field performance. R-squared is not applicable to this classifier.

## Data files

Raw image datasets, the local SQLite database, uploaded images, and `prediction_results.csv` are excluded from Git. The CSV is regenerated from the local database on app startup and whenever predictions are added or removed.

Set a private `SECRET_KEY` before exposing the app beyond local development.