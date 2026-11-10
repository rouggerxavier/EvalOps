"""Shared source authorization for API and workers; resolve current labels on every use."""
from dataclasses import dataclass
from typing import Callable

from app.domain.tasks.contracts import AccessLabel, Environment


class AccessDenied(Exception):
    """Map to an opaque 404 at the transport boundary."""


@dataclass(frozen=True)
class Source:
    project_id: str
    label: AccessLabel | None
    environment: Environment | None = None


def authorize_sources(
    source: Source, *, project_id: str, environment: Environment | None,
    resolve: Callable[[str], Source],
) -> None:
    """Check saved restrictions and current transitive sources, including result environment."""
    visiting: set[str] = set()
    checked: set[str] = set()
    allowed = {environment} if environment else {"dev", "staging", "prod"}

    def check(current: Source, depth=0) -> None:
        if (current.project_id != project_id or current.label is None
                or depth > 64
                or (environment is not None and environment not in current.label.allowed_environments)
                or (environment is not None and current.environment not in (None, environment))):
            raise AccessDenied("not_found")
        allowed.intersection_update(current.label.allowed_environments)
        if current.environment is not None:
            allowed.intersection_update({current.environment})
        if not allowed:
            raise AccessDenied("not_found")
        for ref in current.label.source_refs:
            if ref in visiting:
                raise AccessDenied("not_found")
            if ref not in checked:
                visiting.add(ref)
                try:
                    referenced = resolve(ref)
                except KeyError as exc:
                    raise AccessDenied("not_found") from exc
                check(referenced, depth + 1)
                visiting.remove(ref)
                checked.add(ref)

    check(source)


def derive_label(
    sources: tuple[Source, ...], *, project_id: str, environment: Environment,
    resolve: Callable[[str], Source], source_refs: tuple[str, ...],
) -> AccessLabel:
    if len(sources) != len(source_refs):
        raise ValueError("source_refs_mismatch")
    allowed = {environment}
    origins: set[Environment] = set()
    for source in sources:
        authorize_sources(source, project_id=project_id, environment=environment, resolve=resolve)
        allowed.intersection_update(source.label.allowed_environments)
        origins.update(source.label.origin_environments)
    return AccessLabel(
        origin_environments=tuple(sorted(origins if sources else {environment})),
        allowed_environments=tuple(sorted(allowed)), source_refs=source_refs,
    )
