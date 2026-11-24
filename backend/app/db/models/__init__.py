"""Phase 1 全部 ORM 模型（对应 PRD §7 核心表结构）。"""

from app.db.models.coverage import CoverageReport
from app.db.models.defect import Defect, DefectCategory, DefectStatus, Severity
from app.db.models.execution import Execution, ExecutionStatus, ResultStatus, TestResult, TriggerType
from app.db.models.project import Project, ProjectStatus
from app.db.models.test_case import CaseSource, CaseType, TestCase
from app.db.models.user import ApiKey, User, UserRole

__all__ = [
    "ApiKey",
    "CaseSource",
    "CaseType",
    "CoverageReport",
    "Defect",
    "DefectCategory",
    "DefectStatus",
    "Execution",
    "ExecutionStatus",
    "Project",
    "ProjectStatus",
    "ResultStatus",
    "Severity",
    "TestCase",
    "TestResult",
    "TriggerType",
    "User",
    "UserRole",
]
