/**
 * 代号对照表 — 已废弃。
 * 现在所有 ID 统一使用 business code，不再区分 k_id 和 code。
 * 保留身份函数作为兼容层，后续可删除。
 */
export function kIdToBusinessCode(kId: number): number {
    return kId;
}

export function businessCodeToKId(code: number): number {
    return code;
}
