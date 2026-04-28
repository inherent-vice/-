from __future__ import annotations

from dataclasses import dataclass, field

@dataclass
class DocumentCandidateScore:
    rcp_no: str
    title: str
    score: int
    grade: str
    source: str
    evidence: list[str] = field(default_factory=list)
    reject_reason: str = ""
    dcm_no: str | None = None

    def to_dict(self):
        return {
            "rcp_no": self.rcp_no,
            "title": self.title,
            "score": self.score,
            "grade": self.grade,
            "source": self.source,
            "evidence": list(self.evidence),
            "reject_reason": self.reject_reason,
            "dcm_no": self.dcm_no,
        }

@dataclass
class TermsheetMatchResult:
    rcp_no: str | None
    title: str | None
    dcm_no: str | None
    pdf: bytes | None
    source: str
    error: str | None = None
    score: int = 0
    confidence: str = ""
    evidence: list[str] = field(default_factory=list)
    candidates: list[dict] = field(default_factory=list)

@dataclass
class ResultReportMatch:
    rcp_no: str | None
    title: str | None
    dcm_no: str | None
    pdf: bytes | None
    text: str
    source: str
    error: str | None = None
    score: int = 0
    confidence: str = ""
    evidence: list[str] = field(default_factory=list)
    candidates: list[dict] = field(default_factory=list)

@dataclass
class ResultAmount:
    name: str
    value: int | None
    raw: str

@dataclass
class ResultAnalysis:
    status: str
    label: str
    confidence: str
    reason: str
    evidence: list[str]
    amounts: list[ResultAmount]
