from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Telemetry(_message.Message):
    __slots__ = ["collection_end_time", "collection_id", "collection_start_time", "data_gpb", "data_gpbkv", "encoding_path", "model_version", "msg_timestamp", "node_id_str", "subscription_id_str"]
    COLLECTION_END_TIME_FIELD_NUMBER: _ClassVar[int]
    COLLECTION_ID_FIELD_NUMBER: _ClassVar[int]
    COLLECTION_START_TIME_FIELD_NUMBER: _ClassVar[int]
    DATA_GPBKV_FIELD_NUMBER: _ClassVar[int]
    DATA_GPB_FIELD_NUMBER: _ClassVar[int]
    ENCODING_PATH_FIELD_NUMBER: _ClassVar[int]
    MODEL_VERSION_FIELD_NUMBER: _ClassVar[int]
    MSG_TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    NODE_ID_STR_FIELD_NUMBER: _ClassVar[int]
    SUBSCRIPTION_ID_STR_FIELD_NUMBER: _ClassVar[int]
    collection_end_time: int
    collection_id: int
    collection_start_time: int
    data_gpb: TelemetryGPBTable
    data_gpbkv: _containers.RepeatedCompositeFieldContainer[TelemetryField]
    encoding_path: str
    model_version: str
    msg_timestamp: int
    node_id_str: str
    subscription_id_str: str
    def __init__(self, node_id_str: _Optional[str] = ..., subscription_id_str: _Optional[str] = ..., encoding_path: _Optional[str] = ..., model_version: _Optional[str] = ..., collection_id: _Optional[int] = ..., collection_start_time: _Optional[int] = ..., msg_timestamp: _Optional[int] = ..., data_gpbkv: _Optional[_Iterable[_Union[TelemetryField, _Mapping]]] = ..., data_gpb: _Optional[_Union[TelemetryGPBTable, _Mapping]] = ..., collection_end_time: _Optional[int] = ...) -> None: ...

class TelemetryField(_message.Message):
    __slots__ = ["bool_value", "bytes_value", "delete", "double_value", "fields", "float_value", "name", "sint32_value", "sint64_value", "string_value", "timestamp", "timestamp_nano", "uint32_value", "uint64_value"]
    BOOL_VALUE_FIELD_NUMBER: _ClassVar[int]
    BYTES_VALUE_FIELD_NUMBER: _ClassVar[int]
    DELETE_FIELD_NUMBER: _ClassVar[int]
    DOUBLE_VALUE_FIELD_NUMBER: _ClassVar[int]
    FIELDS_FIELD_NUMBER: _ClassVar[int]
    FLOAT_VALUE_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    SINT32_VALUE_FIELD_NUMBER: _ClassVar[int]
    SINT64_VALUE_FIELD_NUMBER: _ClassVar[int]
    STRING_VALUE_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_NANO_FIELD_NUMBER: _ClassVar[int]
    UINT32_VALUE_FIELD_NUMBER: _ClassVar[int]
    UINT64_VALUE_FIELD_NUMBER: _ClassVar[int]
    bool_value: bool
    bytes_value: bytes
    delete: bool
    double_value: float
    fields: _containers.RepeatedCompositeFieldContainer[TelemetryField]
    float_value: float
    name: str
    sint32_value: int
    sint64_value: int
    string_value: str
    timestamp: int
    timestamp_nano: int
    uint32_value: int
    uint64_value: int
    def __init__(self, timestamp: _Optional[int] = ..., name: _Optional[str] = ..., bytes_value: _Optional[bytes] = ..., string_value: _Optional[str] = ..., bool_value: bool = ..., uint32_value: _Optional[int] = ..., uint64_value: _Optional[int] = ..., sint32_value: _Optional[int] = ..., sint64_value: _Optional[int] = ..., double_value: _Optional[float] = ..., float_value: _Optional[float] = ..., fields: _Optional[_Iterable[_Union[TelemetryField, _Mapping]]] = ..., delete: bool = ..., timestamp_nano: _Optional[int] = ...) -> None: ...

class TelemetryGPBTable(_message.Message):
    __slots__ = ["row"]
    ROW_FIELD_NUMBER: _ClassVar[int]
    row: _containers.RepeatedCompositeFieldContainer[TelemetryRowGPB]
    def __init__(self, row: _Optional[_Iterable[_Union[TelemetryRowGPB, _Mapping]]] = ...) -> None: ...

class TelemetryRowGPB(_message.Message):
    __slots__ = ["content", "delete", "keys", "timestamp", "timestamp_nano"]
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    DELETE_FIELD_NUMBER: _ClassVar[int]
    KEYS_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_NANO_FIELD_NUMBER: _ClassVar[int]
    content: bytes
    delete: bool
    keys: bytes
    timestamp: int
    timestamp_nano: int
    def __init__(self, timestamp: _Optional[int] = ..., delete: bool = ..., timestamp_nano: _Optional[int] = ..., keys: _Optional[bytes] = ..., content: _Optional[bytes] = ...) -> None: ...
