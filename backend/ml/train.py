"""
Training script for the Explainable ML Criticality Scoring Service (Phase C).
Generates synthetic data with controlled stochastic noise, trains a GradientBoostingRegressor,
extracts feature importances, validates on all real database defects, and serializes the model.
"""
import os
import sys
# Ensure workspace root is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import logging
from datetime import datetime, timezone
from typing import Dict, Any, Tuple
import numpy as np
import joblib
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, r2_score, mean_absolute_error

from backend.database import SessionLocal
from backend.models import TMSDefect, SMMSDefect, TDMSDefect
from backend.ml.feature_extractor import (
    FEATURE_NAMES,
    DOMAIN_WEIGHTS,
    extract_defect_features,
    calculate_domain_formula_score,
)

logger = logging.getLogger("backend.ml.train")
MODEL_PATH = os.path.join(os.path.dirname(__file__), "criticality_model.joblib")

def generate_synthetic_dataset(
    n_samples: int = 2500,
    noise_std: float = 2.5,
    random_state: int = 42,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Generates realistic synthetic samples across the 5 domain features
    and labels them with the domain formula plus controlled Gaussian noise.
    """
    rng = np.random.RandomState(random_state)
    
    # 1. Severity: [25 (low), 50 (medium), 75 (high), 95 (critical)]
    severity_choices = [25.0, 50.0, 75.0, 95.0]
    severity_probs = [0.25, 0.40, 0.25, 0.10]
    severities = rng.choice(severity_choices, size=n_samples, p=severity_probs)
    
    # 2. Urgency: [25 (>96h), 30 (no deadline), 50 (48-96h), 70 (24-48h), 85 (12-24h), 100 (<12h)]
    urgency_choices = [25.0, 30.0, 50.0, 70.0, 85.0, 100.0]
    urgency_probs = [0.15, 0.15, 0.25, 0.20, 0.15, 0.10]
    urgencies = rng.choice(urgency_choices, size=n_samples, p=urgency_probs)
    
    # 3. Section Traffic Density: continuous between 70.0 and 100.0 (corridor distribution)
    traffic = rng.uniform(70.0, 100.0, size=n_samples)
    
    # 4. Recurrence: [15 (0 open), 35 (1 open), 55 (2 open), 75 (3 open), 95 (4+ open)]
    recurrence_choices = [15.0, 35.0, 55.0, 75.0, 95.0]
    recurrence_probs = [0.30, 0.35, 0.20, 0.10, 0.05]
    recurrences = rng.choice(recurrence_choices, size=n_samples, p=recurrence_probs)
    
    # 5. Block Required: [20 (off-track), 100 (track/signal/power block required)]
    block_req_choices = [20.0, 100.0]
    block_req_probs = [0.25, 0.75]
    block_reqs = rng.choice(block_req_choices, size=n_samples, p=block_req_probs)
    
    X = np.column_stack([severities, urgencies, traffic, recurrences, block_reqs])
    
    # Compute ground-truth labels from hand-crafted domain formula
    weights = np.array([
        DOMAIN_WEIGHTS["severity_score"],
        DOMAIN_WEIGHTS["urgency_score"],
        DOMAIN_WEIGHTS["traffic_density"],
        DOMAIN_WEIGHTS["recurrence_score"],
        DOMAIN_WEIGHTS["block_required_score"],
    ])
    
    y_clean = np.dot(X, weights)
    
    # Add controlled Gaussian noise so the model doesn't just memorize deterministic algebra
    noise = rng.normal(0, noise_std, size=n_samples)
    y = np.clip(y_clean + noise, 1.0, 100.0)
    
    return X, y

def train_and_evaluate():
    """
    Trains the GradientBoostingRegressor, extracts feature importances,
    and runs held-out validation against all real database defects.
    """
    print("=" * 75)
    print("  SIH26027 — TRAINING EXPLAINABLE ML CRITICALITY SCORER (PHASE C)")
    print("=" * 75)
    
    print("\n[1/4] Generating synthetic dataset (N=2,500 with noise std=2.5)...")
    X, y = generate_synthetic_dataset(n_samples=2500, noise_std=2.5, random_state=42)
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.20, random_state=42)
    print(f"  --> Train set: {len(X_train)} samples | Test set: {len(X_test)} samples")
    
    print("\n[2/4] Training GradientBoostingRegressor (100 estimators, max_depth=4)...")
    model = GradientBoostingRegressor(
        n_estimators=100,
        max_depth=4,
        learning_rate=0.1,
        random_state=42,
    )
    model.fit(X_train, y_train)
    
    # Evaluate test performance
    y_pred = model.predict(X_test)
    test_r2 = r2_score(y_test, y_pred)
    test_rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    test_mae = mean_absolute_error(y_test, y_pred)
    
    print(f"  --> Test R^2 Score: {test_r2:.4f} (Target: >0.95)")
    print(f"  --> Test RMSE:      {test_rmse:.2f} points")
    print(f"  --> Test MAE:       {test_mae:.2f} points")
    
    # Feature Importances Breakdown
    importances = model.feature_importances_
    importance_dict = {
        name: round(float(imp * 100), 2)
        for name, imp in zip(FEATURE_NAMES, importances)
    }
    
    print("\n[3/4] Model Feature Importances vs Domain Baseline Weights:")
    print(f"  {'Feature Name':<22} | {'Domain Weight':<15} | {'Model Importance':<18}")
    print("  " + "-" * 62)
    for feat in FEATURE_NAMES:
        dom_w = f"{DOMAIN_WEIGHTS[feat] * 100:.1f}%"
        mod_imp = f"{importance_dict[feat]:.2f}%"
        print(f"  {feat:<22} | {dom_w:<15} | {mod_imp:<18}")
        
    # Held-Out Validation against real Supabase defects
    print("\n[4/4] Validating against Real Corridor Database Defects...")
    db = SessionLocal()
    validation_results = []
    try:
        tms = db.query(TMSDefect).all()
        smms = db.query(SMMSDefect).all()
        tdms = db.query(TDMSDefect).all()
        
        all_defects = [("TMS", d) for d in tms] + [("SMMS", d) for d in smms] + [("TDMS", d) for d in tdms]
        print(f"  Found {len(all_defects)} real defects in database.")
        
        real_features = []
        real_stored_scores = []
        real_formula_scores = []
        
        for dept, d in all_defects:
            req_block = getattr(d, "requires_track_block", getattr(d, "requires_signal_block", getattr(d, "requires_power_block", True)))
            feats = extract_defect_features(
                db=db,
                block_section_id=d.block_section_id,
                severity=d.severity,
                required_by=d.required_by,
                requires_block=req_block,
                detected_at=d.detected_at,
            )
            feat_vec = [feats[name] for name in FEATURE_NAMES]
            real_features.append(feat_vec)
            real_stored_scores.append(d.criticality_score)
            real_formula_scores.append(calculate_domain_formula_score(feats))
            
        real_X = np.array(real_features)
        real_predicted = model.predict(real_X)
        
        real_mae = mean_absolute_error(real_formula_scores, real_predicted)
        real_r2 = r2_score(real_formula_scores, real_predicted)
        
        print(f"  --> Real Defects Sample Count: {len(real_predicted)}")
        print(f"  --> Model vs Formula MAE:      {real_mae:.2f} points")
        print(f"  --> Model vs Formula R^2:      {real_r2:.4f}")
        
        print("\n  Sample Real Defect Predictions:")
        print(f"  {'Defect Code':<14} | {'Dept':<5} | {'Stored':<7} | {'Formula':<8} | {'Predicted':<10}")
        print("  " + "-" * 56)
        for i in range(min(8, len(all_defects))):
            dept, d = all_defects[i]
            print(f"  {d.defect_code:<14} | {dept:<5} | {d.criticality_score:<7} | {real_formula_scores[i]:<8.1f} | {real_predicted[i]:<10.1f}")
            
    finally:
        db.close()
        
    # Serialize model artifact
    artifact = {
        "model": model,
        "feature_names": FEATURE_NAMES,
        "domain_weights": DOMAIN_WEIGHTS,
        "feature_importances": importance_dict,
        "metrics": {
            "test_r2": float(test_r2),
            "test_rmse": float(test_rmse),
            "test_mae": float(test_mae),
            "real_mae": float(real_mae),
            "real_r2": float(real_r2),
        },
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }
    joblib.dump(artifact, MODEL_PATH)
    print(f"\n[OK] Model successfully serialized and saved to:\n     {MODEL_PATH}")
    print("=" * 75)
    return artifact

if __name__ == "__main__":
    train_and_evaluate()
