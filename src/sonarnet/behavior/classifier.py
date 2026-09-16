"""Bộ phân loại hành vi hoạt động của phương tiện.

Sử dụng thuật toán tăng cường gradient. Ưu tiên XGBoost nếu có sẵn trong môi
trường, nếu không sẽ tự động chuyển sang ``HistGradientBoostingClassifier`` của
scikit-learn — thư viện luôn có mặt trong ảnh Python của Kaggle. Cả hai lựa chọn
đều cho chất lượng tương đương trên bài toán bảng số quy mô này.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..utils import get_logger, package_available

LOG = get_logger("behavior.classifier")


@dataclass
class BehaviorReport:
    """Kết quả đánh giá bộ phân loại hành vi."""

    backend: str
    classes: List[str]
    accuracy: float
    macro_f1: float
    per_class_f1: Dict[str, float]
    confusion_matrix: np.ndarray
    feature_importance: Optional[Dict[str, float]] = None
    n_train: int = 0
    n_test: int = 0

    def to_dict(self) -> Dict:
        return {
            "backend": self.backend,
            "classes": self.classes,
            "accuracy": float(self.accuracy),
            "macro_f1": float(self.macro_f1),
            "per_class_f1": {k: float(v) for k, v in self.per_class_f1.items()},
            "confusion_matrix": self.confusion_matrix.tolist(),
            "n_train": self.n_train,
            "n_test": self.n_test,
            "top_features": (
                dict(sorted(self.feature_importance.items(), key=lambda kv: -kv[1])[:12])
                if self.feature_importance
                else None
            ),
        }


class BehaviorClassifier:
    """Bao bọc thống nhất cho hai thư viện tăng cường gradient."""

    def __init__(self, backend: str = "auto", seed: int = 0) -> None:
        if backend == "auto":
            backend = "xgboost" if package_available("xgboost") else "sklearn"
        self.backend = backend
        self.seed = seed
        self.model = None
        self.classes_: List[str] = []
        self._label_to_idx: Dict[str, int] = {}

    # -- Huấn luyện --------------------------------------------------------
    def fit(self, X: np.ndarray, y: np.ndarray) -> "BehaviorClassifier":
        self.classes_ = sorted(set(map(str, y)))
        self._label_to_idx = {c: i for i, c in enumerate(self.classes_)}
        y_idx = np.array([self._label_to_idx[str(v)] for v in y], dtype=int)

        if self.backend == "xgboost":
            import xgboost as xgb

            self.model = xgb.XGBClassifier(
                n_estimators=450,
                max_depth=6,
                learning_rate=0.06,
                subsample=0.85,
                colsample_bytree=0.85,
                reg_lambda=1.2,
                objective="multi:softprob",
                num_class=len(self.classes_),
                tree_method="hist",
                random_state=self.seed,
                n_jobs=-1,
                eval_metric="mlogloss",
            )
        else:
            from sklearn.ensemble import HistGradientBoostingClassifier

            self.model = HistGradientBoostingClassifier(
                max_iter=450,
                max_depth=8,
                learning_rate=0.07,
                l2_regularization=1.0,
                random_state=self.seed,
            )
        self.model.fit(X, y_idx)
        return self

    # -- Suy luận ----------------------------------------------------------
    def predict(self, X: np.ndarray) -> np.ndarray:
        idx = self.model.predict(X)
        return np.array([self.classes_[int(i)] for i in idx])

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        return self.model.predict_proba(X)

    # -- Độ quan trọng đặc trưng ------------------------------------------
    def feature_importance(self, names: Sequence[str]) -> Optional[Dict[str, float]]:
        try:
            if self.backend == "xgboost":
                imp = np.asarray(self.model.feature_importances_, dtype=float)
            else:
                from sklearn.inspection import permutation_importance  # noqa: F401
                return None  # bỏ qua để tránh chi phí tính toán lớn
            total = float(imp.sum()) or 1.0
            return {n: float(v / total) for n, v in zip(names, imp)}
        except Exception:
            return None

    # -- Lưu và nạp --------------------------------------------------------
    def save(self, path: Path) -> Path:
        import pickle

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as f:
            pickle.dump(
                {
                    "backend": self.backend,
                    "classes": self.classes_,
                    "model": self.model,
                },
                f,
            )
        return path


def macro_f1_score(y_true: np.ndarray, y_pred: np.ndarray, classes: List[str]) -> Tuple[float, Dict[str, float]]:
    """Tính F1 vĩ mô và F1 theo từng lớp, không phụ thuộc scikit-learn."""
    per_class: Dict[str, float] = {}
    for c in classes:
        tp = int(np.sum((y_true == c) & (y_pred == c)))
        fp = int(np.sum((y_true != c) & (y_pred == c)))
        fn = int(np.sum((y_true == c) & (y_pred != c)))
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        per_class[c] = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    return float(np.mean(list(per_class.values()))), per_class


def confusion_matrix(y_true: np.ndarray, y_pred: np.ndarray, classes: List[str]) -> np.ndarray:
    idx = {c: i for i, c in enumerate(classes)}
    cm = np.zeros((len(classes), len(classes)), dtype=int)
    for t, p in zip(y_true, y_pred):
        cm[idx[str(t)], idx[str(p)]] += 1
    return cm


def train_and_evaluate(
    X: np.ndarray,
    y: np.ndarray,
    feature_names: Sequence[str],
    cfg,
) -> Tuple[BehaviorClassifier, BehaviorReport]:
    """Chia tập, huấn luyện và đánh giá bộ phân loại hành vi."""
    from sklearn.model_selection import train_test_split

    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y,
        test_size=cfg.behavior.test_size,
        random_state=cfg.seed,
        stratify=y,
    )

    clf = BehaviorClassifier(backend=cfg.behavior.backend, seed=cfg.seed)
    clf.fit(X_tr, y_tr)
    LOG.info(
        "Đã huấn luyện bộ phân loại hành vi bằng %s trên %d mẫu.",
        clf.backend, len(X_tr),
    )

    y_pred = clf.predict(X_te)
    acc = float(np.mean(y_pred == y_te))
    mf1, per_class = macro_f1_score(y_te, y_pred, clf.classes_)
    cm = confusion_matrix(y_te, y_pred, clf.classes_)

    report = BehaviorReport(
        backend=clf.backend,
        classes=clf.classes_,
        accuracy=acc,
        macro_f1=mf1,
        per_class_f1=per_class,
        confusion_matrix=cm,
        feature_importance=clf.feature_importance(feature_names),
        n_train=len(X_tr),
        n_test=len(X_te),
    )
    LOG.info("Độ chính xác %.4f | F1 vĩ mô %.4f", acc, mf1)
    return clf, report
