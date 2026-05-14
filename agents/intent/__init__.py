"""Agent 意图与实体解析（modify 主路径确定性；歧义 LLM 默认开，可 MODIFY_INTENT_LLM=0 关）。"""

from agents.intent.resolution import (
    FIELD_TO_TABLE,
    SOURCE_TABLES,
    ModifyResolutionContext,
    ModifyResolutionError,
    canonical_modify_field_name,
    find_card_id_for_bug_source_id,
    infer_source_tuple_from_card_dict,
    normalize_modification_key_set,
    remap_card_layer_modification_keys,
    resolve_modify_target_and_id,
)

__all__ = [
    "FIELD_TO_TABLE",
    "SOURCE_TABLES",
    "ModifyResolutionContext",
    "ModifyResolutionError",
    "canonical_modify_field_name",
    "find_card_id_for_bug_source_id",
    "infer_source_tuple_from_card_dict",
    "normalize_modification_key_set",
    "remap_card_layer_modification_keys",
    "resolve_modify_target_and_id",
]
