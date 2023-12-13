from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class MdtDialoutArgs(_message.Message):
    __slots__ = ["ReqId", "data", "errors"]
    DATA_FIELD_NUMBER: _ClassVar[int]
    ERRORS_FIELD_NUMBER: _ClassVar[int]
    REQID_FIELD_NUMBER: _ClassVar[int]
    ReqId: int
    data: bytes
    errors: str
    def __init__(self, ReqId: _Optional[int] = ..., data: _Optional[bytes] = ..., errors: _Optional[str] = ...) -> None: ...
