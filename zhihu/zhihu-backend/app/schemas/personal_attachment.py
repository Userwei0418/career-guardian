from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PersonalAttachmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_type: str
    logical_key: str
    version_number: int
    display_name: str
    original_filename: str
    content_type: str
    file_size: int
    is_active: bool
    created_at: datetime
