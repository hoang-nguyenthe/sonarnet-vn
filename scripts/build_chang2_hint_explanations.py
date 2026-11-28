"""Export per-case XGBoost TreeSHAP scores for the published AIS review banks."""
from hashlib import sha256
from importlib.metadata import version
import json
from pathlib import Path

import numpy as np
from xgboost import DMatrix

from build_chang2_review_bank import MODEL_SEED, review_bank, trained_model
from evaluate_chang2 import REVIEW_POSITIVE, VN, study_bank
from sonarnet.behavior.features import FEATURE_NAMES

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / 'reports/final/chang2'


def explain(model, inputs, cases):
    booster = model.model.get_booster()
    matrix = DMatrix(inputs)
    margins = booster.predict(matrix, output_margin=True, strict_shape=True)
    shap = booster.predict(matrix, pred_contribs=True, strict_shape=True)
    scores = model.predict_proba(inputs)
    predictions = model.predict(inputs)
    np.testing.assert_allclose(shap.sum(axis=-1), margins, atol=5e-5, rtol=0)
    shifted = np.exp(margins - margins.max(axis=1, keepdims=True))
    np.testing.assert_allclose(shifted / shifted.sum(axis=1, keepdims=True), scores, atol=1e-6)

    result = {}
    for index, case in enumerate(cases):
        winner, runner_up = np.argsort(-margins[index], kind='stable')[:2]
        predicted_class = model.classes_[winner]
        assert predicted_class == predictions[index]
        assert (VN[predicted_class], predicted_class in REVIEW_POSITIVE) == (
            case['hint_class'], case['hint_priority'],
        ), case['id']
        difference = shap[index, winner] - shap[index, runner_up]
        margin_difference = margins[index, winner] - margins[index, runner_up]
        np.testing.assert_allclose(difference.sum(), margin_difference, atol=1e-4, rtol=0)
        result[case['id']] = {
            'winner': int(winner),
            'runner_up': int(runner_up),
            'scores': scores[index].round(8).astype(float).tolist(),
            'gap': round(float(margin_difference), 6),
            'base_gap': round(float(difference[-1]), 6),
            'inputs': [round(float(value), 7) for value in inputs[index]],
            'feature_gaps': [round(float(value), 6) for value in difference[:-1]],
        }
    return result


def main():
    model = trained_model(MODEL_SEED)
    banks = (
        ('review-bank-200.json', review_bank(model)),
        ('study-cases.json', study_bank(model, with_inputs=True)),
    )
    cases = {}
    digests = {}
    for name, (published, inputs) in banks:
        original = (REPORTS / name).read_bytes()
        if published != json.loads(original):
            raise ValueError(f'Rebuilt samples or predictions differ from the published {name}')
        digests[name] = sha256(original).hexdigest()
        cases.update(explain(model, inputs, published))
    assert len(cases) == 216
    payload = {
        'model': 'XGBoost history_augmented',
        'seed': MODEL_SEED,
        'versions': {pkg: version(pkg) for pkg in ('numpy', 'scikit-learn', 'xgboost')},
        'booster_sha256': sha256(model.model.get_booster().save_raw(raw_format='ubj')).hexdigest(),
        'banks_sha256': digests,
        'classes': [VN[label] for label in model.classes_],
        'features': FEATURE_NAMES,
        'cases': cases,
    }
    output = ROOT / 'web/chang2/hint-explanations.js'
    output.write_text('window.SONARNET_HINT_EXPLANATIONS = ' +
                      json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(',', ':')) +
                      ';\n')
    print(f'Verified TreeSHAP for {len(cases)} published cases in {output.name}')


if __name__ == '__main__':
    main()
