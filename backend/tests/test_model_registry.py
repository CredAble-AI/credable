import json
from pathlib import Path

from app.schemas.assessment import (
    AdapterAssessmentResult,
    AssessmentStatus,
    AssessmentUncertainty,
    CalibrationMode,
)
from app.schemas.model_registry import ModelRole
from app.services.model_registry_service import DemoModelRegistryCatalog, ModelRegistryService


def completed_result(model_version: str) -> AdapterAssessmentResult:
    return AdapterAssessmentResult(
        status=AssessmentStatus.COMPLETED,
        model_version=model_version,
        uncertainty=AssessmentUncertainty(
            grade_set=["DEMO_GRADE_B"],
            calibration_mode=CalibrationMode.RULE_TABLE,
            calibration_version="test-calibration-v1",
        ),
    )


def write_registry(
    path: Path,
    *,
    model_role: str = "BASELINE_ASSESSMENT",
    validation_status: str = "DEMO_ONLY",
    operational_state: str = "RUNNING",
) -> None:
    path.write_text(
        json.dumps(
            {
                "registryVersion": "test-registry-v1",
                "models": [
                    {
                        "modelVersion": "test-model-v1",
                        "modelRole": model_role,
                        "validationStatus": validation_status,
                        "operationalState": operational_state,
                        "demoOnly": True,
                    }
                ],
                "demoOnly": True,
            }
        ),
        encoding="utf-8",
    )


def test_registered_running_model_is_allowed(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    write_registry(path)
    service = ModelRegistryService(DemoModelRegistryCatalog(path))

    result, resolution = service.govern(
        completed_result("test-model-v1"),
        ModelRole.BASELINE_ASSESSMENT,
    )

    assert result.status == AssessmentStatus.COMPLETED
    assert resolution is not None
    assert resolution.registered is True
    assert resolution.allowed is True
    assert resolution.validation_status == "DEMO_ONLY"
    assert resolution.operational_state == "RUNNING"
    assert service.readiness() == {"model_registry_catalog": True}


def test_unregistered_model_is_blocked(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    write_registry(path)
    service = ModelRegistryService(DemoModelRegistryCatalog(path))

    result, resolution = service.govern(
        completed_result("unknown-model-v1"),
        ModelRole.BASELINE_ASSESSMENT,
    )

    assert result.status == AssessmentStatus.FAILED
    assert result.model_version is None
    assert result.uncertainty is None
    assert result.reason_code == "ASSESSMENT_MODEL_NOT_REGISTERED"
    assert resolution is not None
    assert resolution.registered is False
    assert resolution.allowed is False


def test_model_role_mismatch_is_blocked(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    write_registry(path, model_role="SUPPLEMENTAL_ASSESSMENT")
    service = ModelRegistryService(DemoModelRegistryCatalog(path))

    result, resolution = service.govern(
        completed_result("test-model-v1"),
        ModelRole.BASELINE_ASSESSMENT,
    )

    assert result.reason_code == "ASSESSMENT_MODEL_ROLE_MISMATCH"
    assert resolution is not None
    assert resolution.allowed is False


def test_suspended_model_is_blocked(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    write_registry(path, operational_state="SUSPENDED")
    service = ModelRegistryService(DemoModelRegistryCatalog(path))

    result, resolution = service.govern(
        completed_result("test-model-v1"),
        ModelRole.BASELINE_ASSESSMENT,
    )

    assert result.reason_code == "ASSESSMENT_MODEL_SUSPENDED"
    assert resolution is not None
    assert resolution.operational_state == "SUSPENDED"
    assert resolution.allowed is False


def test_non_completed_result_does_not_require_model_registration(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    write_registry(path)
    service = ModelRegistryService(DemoModelRegistryCatalog(path))
    original = AdapterAssessmentResult(
        status=AssessmentStatus.INSUFFICIENT_DATA,
        reason_code="DATA_NOT_READY",
    )

    result, resolution = service.govern(original, ModelRole.BASELINE_ASSESSMENT)

    assert result == original
    assert resolution is None
