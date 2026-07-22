"""Validation helpers for GitHub reusable workflow visibility rules."""

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from models import Project, Repo, ProjectRepo


PUBLIC_CALLER_PRIVATE_RWX_REASON = (
    "This reusable workflow cannot be linked because public repositories cannot "
    "call reusable workflows from private repositories. Select a public RWX "
    "workflow or use a private caller project owned by the same account or organization."
)
PUBLIC_CALLER_INTERNAL_RWX_REASON = (
    "This reusable workflow cannot be linked because public repositories cannot "
    "call reusable workflows from internal repositories. Select a public RWX workflow."
)
PRIVATE_OWNER_MISMATCH_REASON = (
    "This reusable workflow cannot be linked because private reusable workflows "
    "must be called from private repositories owned by the same user or organization."
)
INTERNAL_OWNER_MISMATCH_REASON = (
    "This reusable workflow cannot be linked because internal reusable workflows "
    "must be called from internal or private repositories owned by the same user or organization."
)
UNKNOWN_VISIBILITY_REASON = (
    "This reusable workflow cannot be linked because repository visibility could not be verified."
)


@dataclass(frozen=True)
class RepositoryRef:
    full_name: str
    visibility: Optional[str]


@dataclass(frozen=True)
class ReusableWorkflowLinkValidationResult:
    allowed: bool
    reason: Optional[str] = None
    incompatible_repositories: tuple[str, ...] = ()


def _normalize_repo_name(repo_name: Optional[str]) -> Optional[str]:
    if not repo_name or "/" not in repo_name:
        return None
    owner, name = repo_name.strip().split("/", 1)
    if not owner or not name:
        return None
    return f"{owner.lower()}/{name.lower()}"


def _normalize_visibility(visibility: Optional[str]) -> Optional[str]:
    normalized = (visibility or "").strip().lower()
    if normalized in {"public", "private", "internal"}:
        return normalized
    return None


def _owner(repo_full_name: str) -> str:
    return repo_full_name.split("/", 1)[0].lower()


def get_project_repository_refs(db: Session, project: Project) -> list[RepositoryRef]:
    """Return a project's repositories with the backend-stored visibility scope.

    The current schema stores visibility at the project level, so every selected
    repository in the project uses the same verified/projected scope. Missing or
    unsupported visibility is intentionally returned as ``None`` so callers fail
    closed instead of assuming public access.
    """
    visibility = _normalize_visibility(getattr(project, "repository_visibility_scope", None))
    repos = (
        db.query(Repo)
        .join(ProjectRepo, ProjectRepo.repo_id == Repo.repo_id)
        .filter(ProjectRepo.project_id == project.project_id)
        .order_by(Repo.repo_name)
        .all()
    )
    return [
        RepositoryRef(full_name=repo.repo_name, visibility=visibility)
        for repo in repos
        if _normalize_repo_name(repo.repo_name)
    ]


def _validate_single_repo_pair(
    caller_repo: RepositoryRef,
    rwx_repo: RepositoryRef,
) -> ReusableWorkflowLinkValidationResult:
    caller_full_name = _normalize_repo_name(caller_repo.full_name)
    rwx_full_name = _normalize_repo_name(rwx_repo.full_name)

    if not caller_full_name or not rwx_full_name:
        return ReusableWorkflowLinkValidationResult(False, UNKNOWN_VISIBILITY_REASON)

    # GitHub always allows same-repository reusable workflow calls.
    if caller_full_name == rwx_full_name:
        return ReusableWorkflowLinkValidationResult(True)

    caller_visibility = _normalize_visibility(caller_repo.visibility)
    rwx_visibility = _normalize_visibility(rwx_repo.visibility)
    if not caller_visibility or not rwx_visibility:
        return ReusableWorkflowLinkValidationResult(False, UNKNOWN_VISIBILITY_REASON)

    if rwx_visibility == "public":
        return ReusableWorkflowLinkValidationResult(True)

    if rwx_visibility == "private":
        if caller_visibility == "public":
            return ReusableWorkflowLinkValidationResult(False, PUBLIC_CALLER_PRIVATE_RWX_REASON)
        if _owner(caller_full_name) == _owner(rwx_full_name):
            return ReusableWorkflowLinkValidationResult(True)
        return ReusableWorkflowLinkValidationResult(False, PRIVATE_OWNER_MISMATCH_REASON)

    if rwx_visibility == "internal":
        if caller_visibility == "public":
            return ReusableWorkflowLinkValidationResult(False, PUBLIC_CALLER_INTERNAL_RWX_REASON)
        if caller_visibility in {"private", "internal"} and _owner(caller_full_name) == _owner(rwx_full_name):
            return ReusableWorkflowLinkValidationResult(True)
        return ReusableWorkflowLinkValidationResult(False, INTERNAL_OWNER_MISMATCH_REASON)

    return ReusableWorkflowLinkValidationResult(False, UNKNOWN_VISIBILITY_REASON)


def validate_reusable_workflow_link(
    caller_project: Project,
    rwx_project: Project,
    db: Session,
) -> ReusableWorkflowLinkValidationResult:
    """Validate a standard project can call workflows from an RWX project.

    Every repository that can receive caller workflow YAML must be compatible
    with the RWX project's source repository. If any caller repository is not
    compatible, the entire link is rejected rather than creating partial links.
    """
    caller_repos = get_project_repository_refs(db, caller_project)
    rwx_repos = get_project_repository_refs(db, rwx_project)
    if not caller_repos or not rwx_repos:
        return ReusableWorkflowLinkValidationResult(False, UNKNOWN_VISIBILITY_REASON)

    rwx_repo = rwx_repos[0]
    incompatible: list[str] = []
    first_reason: Optional[str] = None
    for caller_repo in caller_repos:
        result = _validate_single_repo_pair(caller_repo, rwx_repo)
        if not result.allowed:
            incompatible.append(caller_repo.full_name)
            first_reason = first_reason or result.reason

    if incompatible:
        return ReusableWorkflowLinkValidationResult(
            False,
            first_reason or UNKNOWN_VISIBILITY_REASON,
            tuple(incompatible),
        )

    return ReusableWorkflowLinkValidationResult(True)


def reusable_workflow_validation_payload(
    result: ReusableWorkflowLinkValidationResult,
) -> dict:
    payload = {"allowed": result.allowed}
    if result.reason:
        payload["reason"] = result.reason
    if result.incompatible_repositories:
        payload["incompatible_repositories"] = list(result.incompatible_repositories)
    return payload
