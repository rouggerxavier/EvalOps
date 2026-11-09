from datetime import datetime, timezone
from typing import Annotated

from pydantic import AfterValidator


def server_timestamp(value: datetime) -> datetime:
    # Only server-owned UTC timestamps can recover the offset dropped by SQLite.
    return value.replace(tzinfo=timezone.utc) if value.utcoffset() is None else value


ServerTimestamp = Annotated[datetime, AfterValidator(server_timestamp)]
