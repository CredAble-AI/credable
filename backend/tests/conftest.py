from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.adapters.assessment_adapter import (
    UnconfiguredDemoAssessmentAdapter,
    UnconfiguredSupplementalAssessmentAdapter,
)
from app.adapters.data_source_adapter import EmptyDemoDataSourceAdapter
from app.adapters.product_catalog_adapter import UnconfiguredProductCatalogAdapter
from app.adapters.product_condition_adapter import UnconfiguredProductConditionAdapter
from app.core.admin_auth import AdminApiKeyAuthenticator
from app.core.config import settings
from app.main import create_app
from app.repositories.assessment_repository import SqliteAssessmentRepository
from app.repositories.bank_data_repository import SqliteBankDataRepository
from app.repositories.consent_repository import SqliteConsentRepository
from app.repositories.credit_exposure_repository import SqliteCreditExposureRepository
from app.repositories.credit_history_repository import SqliteCreditHistoryRepository
from app.repositories.data_source_repository import SqliteDataSourceRepository
from app.repositories.evidence_consent_repository import SqliteEvidenceConsentRepository
from app.repositories.evidence_quality_repository import SqliteEvidenceQualityRepository
from app.repositories.evidence_selection_repository import SqliteEvidenceSelectionRepository
from app.repositories.evidence_submission_repository import SqliteEvidenceSubmissionRepository
from app.repositories.feature_snapshot_repository import SqliteFeatureSnapshotRepository
from app.repositories.loan_history_repository import SqliteLoanHistoryRepository
from app.repositories.policy_boundary_repository import SqlitePolicyBoundaryRepository
from app.repositories.product_catalog_repository import SqliteProductCatalogRepository
from app.repositories.product_condition_repository import SqliteProductConditionRepository
from app.repositories.session_repository import SqliteCustomerSessionRepository
from app.schemas.assessment import AssessmentSnapshotType
from app.schemas.consent import ConsentSourceType
from app.services.assessment_data_lineage_service import (
    AssessmentDataLineageService,
    SnapshotSource,
)
from app.services.assessment_service import (
    AssessmentComparisonService,
    AssessmentService,
    SupplementalAssessmentService,
)
from app.services.bank_data_service import BankDataService, DemoBankDataCatalogService
from app.services.consent_service import ConsentService, DemoConsentScopeCatalog
from app.services.credit_exposure_service import (
    CreditExposureService,
    DemoCreditExposureCatalogService,
)
from app.services.credit_history_service import (
    CreditHistoryService,
    DemoCreditHistoryCatalogService,
)
from app.services.data_source_service import DataSourceService
from app.services.evidence_consent_service import EvidenceConsentService
from app.services.evidence_quality_service import (
    DemoEvidenceQualityCatalog,
    EvidenceQualityService,
)
from app.services.evidence_selection_service import (
    DemoEvidenceCandidateCatalog,
    EvidenceSelectionService,
)
from app.services.evidence_submission_service import (
    DemoEvidenceFileCatalog,
    DemoEvidenceSubmissionCatalog,
    EvidenceSubmissionService,
)
from app.services.feature_snapshot_service import FeatureSnapshotService
from app.services.loan_history_service import DemoLoanHistoryCatalogService, LoanHistoryService
from app.services.model_registry_service import DemoModelRegistryCatalog, ModelRegistryService
from app.services.policy_boundary_service import (
    DemoPolicyBoundaryCatalog,
    EvidenceResolutionService,
    PolicyBoundaryService,
)
from app.services.product_catalog_service import ProductCatalogService
from app.services.product_condition_service import ProductConditionService
from app.services.session_service import CustomerSessionService, DemoProfileCatalog


@pytest.fixture
def session_repository(tmp_path) -> SqliteCustomerSessionRepository:
    return SqliteCustomerSessionRepository(tmp_path / "test.db")


@pytest.fixture
def session_service(
    session_repository: SqliteCustomerSessionRepository,
) -> CustomerSessionService:
    return CustomerSessionService(
        repository=session_repository,
        catalog=DemoProfileCatalog(settings.demo_profiles_path),
    )


@pytest.fixture
def consent_repository(tmp_path) -> SqliteConsentRepository:
    return SqliteConsentRepository(tmp_path / "test.db")


@pytest.fixture
def consent_service(
    consent_repository: SqliteConsentRepository,
    session_repository: SqliteCustomerSessionRepository,
) -> ConsentService:
    return ConsentService(
        repository=consent_repository,
        session_repository=session_repository,
        catalog=DemoConsentScopeCatalog(settings.demo_consent_scopes_path),
    )


@pytest.fixture
def bank_data_repository(tmp_path) -> SqliteBankDataRepository:
    return SqliteBankDataRepository(tmp_path / "test.db")


@pytest.fixture
def bank_data_service(
    bank_data_repository: SqliteBankDataRepository,
    session_service: CustomerSessionService,
) -> BankDataService:
    return BankDataService(
        repository=bank_data_repository,
        session_service=session_service,
        catalog=DemoBankDataCatalogService(settings.demo_bank_data_path),
    )


@pytest.fixture
def credit_history_repository(tmp_path) -> SqliteCreditHistoryRepository:
    return SqliteCreditHistoryRepository(tmp_path / "test.db")


@pytest.fixture
def credit_history_service(
    credit_history_repository: SqliteCreditHistoryRepository,
    session_service: CustomerSessionService,
) -> CreditHistoryService:
    return CreditHistoryService(
        repository=credit_history_repository,
        session_service=session_service,
        catalog=DemoCreditHistoryCatalogService(settings.demo_credit_history_path),
    )


@pytest.fixture
def loan_history_repository(tmp_path) -> SqliteLoanHistoryRepository:
    return SqliteLoanHistoryRepository(tmp_path / "test.db")


@pytest.fixture
def loan_history_service(
    loan_history_repository: SqliteLoanHistoryRepository,
    session_service: CustomerSessionService,
) -> LoanHistoryService:
    return LoanHistoryService(
        repository=loan_history_repository,
        session_service=session_service,
        catalog=DemoLoanHistoryCatalogService(settings.demo_loan_history_path),
    )


@pytest.fixture
def credit_exposure_repository(tmp_path) -> SqliteCreditExposureRepository:
    return SqliteCreditExposureRepository(tmp_path / "test.db")


@pytest.fixture
def credit_exposure_service(
    credit_exposure_repository: SqliteCreditExposureRepository,
    session_service: CustomerSessionService,
) -> CreditExposureService:
    return CreditExposureService(
        repository=credit_exposure_repository,
        session_service=session_service,
        catalog=DemoCreditExposureCatalogService(settings.demo_credit_exposures_path),
    )


@pytest.fixture
def assessment_data_lineage_service(
    bank_data_service: BankDataService,
    credit_history_service: CreditHistoryService,
    loan_history_service: LoanHistoryService,
    credit_exposure_service: CreditExposureService,
) -> AssessmentDataLineageService:
    return AssessmentDataLineageService(
        sources=(
            SnapshotSource(
                ConsentSourceType.BANK_INTERNAL,
                AssessmentSnapshotType.BANK_ACCOUNT_DATA,
                bank_data_service.repository,
            ),
            SnapshotSource(
                ConsentSourceType.BANK_INTERNAL,
                AssessmentSnapshotType.BANK_CREDIT_HISTORY,
                credit_history_service.repository,
            ),
            SnapshotSource(
                ConsentSourceType.BANK_INTERNAL,
                AssessmentSnapshotType.BANK_LOAN_HISTORY,
                loan_history_service.repository,
            ),
            SnapshotSource(
                ConsentSourceType.CREDIT_INFORMATION,
                AssessmentSnapshotType.EXTERNAL_CREDIT_EXPOSURE,
                credit_exposure_service.repository,
                "reported_at",
            ),
        )
    )


@pytest.fixture
def data_source_repository(tmp_path) -> SqliteDataSourceRepository:
    return SqliteDataSourceRepository(tmp_path / "test.db")


@pytest.fixture
def data_source_service(
    data_source_repository: SqliteDataSourceRepository,
    consent_service: ConsentService,
    session_service: CustomerSessionService,
    bank_data_service: BankDataService,
    credit_history_service: CreditHistoryService,
    loan_history_service: LoanHistoryService,
    credit_exposure_service: CreditExposureService,
) -> DataSourceService:
    return DataSourceService(
        repository=data_source_repository,
        consent_service=consent_service,
        session_service=session_service,
        adapter=EmptyDemoDataSourceAdapter(),
        bank_internal_materializers=(
            bank_data_service,
            credit_history_service,
            loan_history_service,
        ),
        credit_information_materializers=(credit_exposure_service,),
    )


@pytest.fixture
def assessment_repository(tmp_path) -> SqliteAssessmentRepository:
    return SqliteAssessmentRepository(tmp_path / "test.db")


@pytest.fixture
def feature_snapshot_repository(tmp_path) -> SqliteFeatureSnapshotRepository:
    return SqliteFeatureSnapshotRepository(tmp_path / "test.db")


@pytest.fixture
def feature_snapshot_service(
    feature_snapshot_repository: SqliteFeatureSnapshotRepository,
    assessment_data_lineage_service: AssessmentDataLineageService,
    bank_data_repository: SqliteBankDataRepository,
    credit_history_repository: SqliteCreditHistoryRepository,
    loan_history_repository: SqliteLoanHistoryRepository,
    credit_exposure_repository: SqliteCreditExposureRepository,
) -> FeatureSnapshotService:
    return FeatureSnapshotService(
        repository=feature_snapshot_repository,
        data_lineage_service=assessment_data_lineage_service,
        bank_data_repository=bank_data_repository,
        credit_history_repository=credit_history_repository,
        loan_history_repository=loan_history_repository,
        credit_exposure_repository=credit_exposure_repository,
    )


@pytest.fixture
def assessment_service(
    assessment_repository: SqliteAssessmentRepository,
    session_service: CustomerSessionService,
    data_source_service: DataSourceService,
    assessment_data_lineage_service: AssessmentDataLineageService,
    feature_snapshot_service: FeatureSnapshotService,
    model_registry_service: ModelRegistryService,
) -> AssessmentService:
    return AssessmentService(
        repository=assessment_repository,
        session_service=session_service,
        data_source_service=data_source_service,
        adapter=UnconfiguredDemoAssessmentAdapter(),
        data_lineage_service=assessment_data_lineage_service,
        feature_snapshot_service=feature_snapshot_service,
        model_registry_service=model_registry_service,
    )


@pytest.fixture
def model_registry_service() -> ModelRegistryService:
    return ModelRegistryService(
        DemoModelRegistryCatalog(Path(__file__).parent / "fixtures" / "demo_model_registry.json")
    )


@pytest.fixture
def policy_boundary_repository(tmp_path) -> SqlitePolicyBoundaryRepository:
    return SqlitePolicyBoundaryRepository(tmp_path / "test.db")


@pytest.fixture
def policy_boundary_service(
    policy_boundary_repository: SqlitePolicyBoundaryRepository,
    session_service: CustomerSessionService,
    assessment_service: AssessmentService,
) -> PolicyBoundaryService:
    return PolicyBoundaryService(
        repository=policy_boundary_repository,
        session_service=session_service,
        assessment_service=assessment_service,
        catalog=DemoPolicyBoundaryCatalog(settings.demo_policy_boundaries_path),
    )


@pytest.fixture
def evidence_selection_repository(tmp_path) -> SqliteEvidenceSelectionRepository:
    return SqliteEvidenceSelectionRepository(tmp_path / "test.db")


@pytest.fixture
def evidence_selection_service(
    evidence_selection_repository: SqliteEvidenceSelectionRepository,
    evidence_submission_repository: SqliteEvidenceSubmissionRepository,
    assessment_repository: SqliteAssessmentRepository,
    policy_boundary_repository: SqlitePolicyBoundaryRepository,
    session_service: CustomerSessionService,
    policy_boundary_service: PolicyBoundaryService,
    data_source_service: DataSourceService,
) -> EvidenceSelectionService:
    return EvidenceSelectionService(
        repository=evidence_selection_repository,
        session_service=session_service,
        boundary_service=policy_boundary_service,
        data_source_service=data_source_service,
        assessment_repository=assessment_repository,
        resolution_repository=policy_boundary_repository,
        submission_repository=evidence_submission_repository,
        catalog=DemoEvidenceCandidateCatalog(settings.demo_evidence_candidates_path),
    )


@pytest.fixture
def evidence_submission_repository(tmp_path) -> SqliteEvidenceSubmissionRepository:
    return SqliteEvidenceSubmissionRepository(tmp_path / "test.db")


@pytest.fixture
def evidence_consent_repository(tmp_path) -> SqliteEvidenceConsentRepository:
    return SqliteEvidenceConsentRepository(tmp_path / "test.db")


@pytest.fixture
def evidence_consent_service(
    evidence_consent_repository: SqliteEvidenceConsentRepository,
    session_service: CustomerSessionService,
    evidence_selection_service: EvidenceSelectionService,
) -> EvidenceConsentService:
    return EvidenceConsentService(
        repository=evidence_consent_repository,
        session_service=session_service,
        selection_repository=evidence_selection_service.repository,
    )


@pytest.fixture
def evidence_submission_service(
    evidence_submission_repository: SqliteEvidenceSubmissionRepository,
    session_service: CustomerSessionService,
    evidence_selection_service: EvidenceSelectionService,
    evidence_consent_service: EvidenceConsentService,
) -> EvidenceSubmissionService:
    return EvidenceSubmissionService(
        repository=evidence_submission_repository,
        session_service=session_service,
        selection_service=evidence_selection_service,
        evidence_consent_service=evidence_consent_service,
        catalog=DemoEvidenceSubmissionCatalog(settings.demo_evidence_submissions_path),
        file_catalog=DemoEvidenceFileCatalog(settings.demo_evidence_files_path),
    )


@pytest.fixture
def evidence_quality_repository(tmp_path) -> SqliteEvidenceQualityRepository:
    return SqliteEvidenceQualityRepository(tmp_path / "test.db")


@pytest.fixture
def evidence_quality_service(
    evidence_quality_repository: SqliteEvidenceQualityRepository,
    evidence_submission_repository: SqliteEvidenceSubmissionRepository,
    evidence_consent_repository: SqliteEvidenceConsentRepository,
    session_service: CustomerSessionService,
    evidence_submission_service: EvidenceSubmissionService,
) -> EvidenceQualityService:
    return EvidenceQualityService(
        repository=evidence_quality_repository,
        submission_repository=evidence_submission_repository,
        evidence_consent_repository=evidence_consent_repository,
        session_service=session_service,
        catalog=DemoEvidenceQualityCatalog(settings.demo_evidence_quality_path),
        file_catalog=evidence_submission_service.file_catalog,
    )


@pytest.fixture
def supplemental_assessment_service(
    assessment_repository: SqliteAssessmentRepository,
    session_service: CustomerSessionService,
    evidence_quality_repository: SqliteEvidenceQualityRepository,
    evidence_submission_repository: SqliteEvidenceSubmissionRepository,
    evidence_consent_repository: SqliteEvidenceConsentRepository,
    evidence_selection_repository: SqliteEvidenceSelectionRepository,
    policy_boundary_repository: SqlitePolicyBoundaryRepository,
    model_registry_service: ModelRegistryService,
) -> SupplementalAssessmentService:
    return SupplementalAssessmentService(
        repository=assessment_repository,
        session_service=session_service,
        quality_repository=evidence_quality_repository,
        submission_repository=evidence_submission_repository,
        evidence_consent_repository=evidence_consent_repository,
        selection_repository=evidence_selection_repository,
        boundary_repository=policy_boundary_repository,
        adapter=UnconfiguredSupplementalAssessmentAdapter(),
        model_registry_service=model_registry_service,
    )


@pytest.fixture
def assessment_comparison_service(
    assessment_repository: SqliteAssessmentRepository,
    session_service: CustomerSessionService,
) -> AssessmentComparisonService:
    return AssessmentComparisonService(
        repository=assessment_repository,
        session_service=session_service,
    )


@pytest.fixture
def evidence_resolution_service(
    policy_boundary_repository: SqlitePolicyBoundaryRepository,
    assessment_repository: SqliteAssessmentRepository,
    session_service: CustomerSessionService,
    policy_boundary_service: PolicyBoundaryService,
) -> EvidenceResolutionService:
    return EvidenceResolutionService(
        repository=policy_boundary_repository,
        assessment_repository=assessment_repository,
        session_service=session_service,
        catalog=policy_boundary_service.catalog,
    )


@pytest.fixture
def product_catalog_repository(tmp_path) -> SqliteProductCatalogRepository:
    return SqliteProductCatalogRepository(tmp_path / "test.db")


@pytest.fixture
def product_catalog_service(
    product_catalog_repository: SqliteProductCatalogRepository,
    session_service: CustomerSessionService,
) -> ProductCatalogService:
    return ProductCatalogService(
        repository=product_catalog_repository,
        session_service=session_service,
        adapter=UnconfiguredProductCatalogAdapter(),
    )


@pytest.fixture
def product_condition_repository(tmp_path) -> SqliteProductConditionRepository:
    return SqliteProductConditionRepository(tmp_path / "test.db")


@pytest.fixture
def product_condition_service(
    product_condition_repository: SqliteProductConditionRepository,
    session_service: CustomerSessionService,
    product_catalog_service: ProductCatalogService,
    assessment_service: AssessmentService,
    data_source_service: DataSourceService,
) -> ProductConditionService:
    return ProductConditionService(
        repository=product_condition_repository,
        session_service=session_service,
        catalog_service=product_catalog_service,
        assessment_service=assessment_service,
        data_source_service=data_source_service,
        adapter=UnconfiguredProductConditionAdapter(),
    )


@pytest.fixture
def client(
    session_service: CustomerSessionService,
    bank_data_service: BankDataService,
    credit_history_service: CreditHistoryService,
    loan_history_service: LoanHistoryService,
    credit_exposure_service: CreditExposureService,
    consent_service: ConsentService,
    data_source_service: DataSourceService,
    assessment_service: AssessmentService,
    policy_boundary_service: PolicyBoundaryService,
    evidence_selection_service: EvidenceSelectionService,
    evidence_consent_service: EvidenceConsentService,
    evidence_submission_service: EvidenceSubmissionService,
    evidence_quality_service: EvidenceQualityService,
    supplemental_assessment_service: SupplementalAssessmentService,
    assessment_comparison_service: AssessmentComparisonService,
    evidence_resolution_service: EvidenceResolutionService,
    product_catalog_service: ProductCatalogService,
    product_condition_service: ProductConditionService,
    model_registry_service: ModelRegistryService,
) -> Generator[TestClient]:
    with TestClient(
        create_app(
            session_service=session_service,
            bank_data_service=bank_data_service,
            credit_history_service=credit_history_service,
            loan_history_service=loan_history_service,
            credit_exposure_service=credit_exposure_service,
            consent_service=consent_service,
            data_source_service=data_source_service,
            assessment_service=assessment_service,
            policy_boundary_service=policy_boundary_service,
            evidence_selection_service=evidence_selection_service,
            evidence_consent_service=evidence_consent_service,
            evidence_submission_service=evidence_submission_service,
            evidence_quality_service=evidence_quality_service,
            supplemental_assessment_service=supplemental_assessment_service,
            assessment_comparison_service=assessment_comparison_service,
            evidence_resolution_service=evidence_resolution_service,
            product_catalog_service=product_catalog_service,
            product_condition_service=product_condition_service,
            model_registry_service=model_registry_service,
            admin_authenticator=AdminApiKeyAuthenticator("test-admin-api-key"),
        )
    ) as test_client:
        yield test_client
