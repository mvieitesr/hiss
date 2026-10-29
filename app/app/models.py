from datetime import datetime
import enum

from sqlalchemy import (
    Table,
    Column,
    ForeignKey,
    String,
    Text,
    DateTime,
    Enum as SAEnum,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .extensions import db


class IssueStatus(str, enum.Enum):
    open = "open"
    in_progress = "in_progress"
    done = "done"


class IssuePriority(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"


# Association table for many-to-many Issue <-> Label
issue_labels = Table(
    "issue_labels",
    db.metadata,
    Column(
        "issue_id",
        ForeignKey("issues.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    ),
    Column(
        "label_id",
        ForeignKey("labels.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    ),
)


class Project(db.Model):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    issues: Mapped[list["Issue"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )

    def __repr__(self) -> str:
        return f"<Project {self.key}>"


class Issue(db.Model):
    __tablename__ = "issues"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    status: Mapped[str] = mapped_column(
        SAEnum(IssueStatus, name="issue_status", native_enum=True, validate_strings=True),
        nullable=False,
        server_default="open",
        default=IssueStatus.open,
    )
    priority: Mapped[str] = mapped_column(
        SAEnum(IssuePriority, name="issue_priority", native_enum=True, validate_strings=True),
        nullable=False,
        server_default="medium",
        default=IssuePriority.medium,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    project: Mapped["Project"] = relationship(back_populates="issues")
    comments: Mapped[list["Comment"]] = relationship(
        back_populates="issue", cascade="all, delete-orphan", passive_deletes=True
    )
    labels: Mapped[list["Label"]] = relationship(
        secondary=issue_labels, back_populates="issues", passive_deletes=True
    )

    def __repr__(self) -> str:
        return f"<Issue {self.id} {self.title}>"


class Comment(db.Model):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    issue_id: Mapped[int] = mapped_column(
        ForeignKey("issues.id", ondelete="CASCADE"), nullable=False, index=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    issue: Mapped["Issue"] = relationship(back_populates="comments")

    def __repr__(self) -> str:
        return f"<Comment {self.id}>"


class Label(db.Model):
    __tablename__ = "labels"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)

    issues: Mapped[list["Issue"]] = relationship(
        secondary=issue_labels, back_populates="labels", passive_deletes=True
    )

    def __repr__(self) -> str:
        return f"<Label {self.name}>"
