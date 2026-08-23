declare const AccountIdBrand: unique symbol
export type AccountId = number & { [AccountIdBrand]: never }

declare const PlayerIdBrand: unique symbol
export type PlayerId = number & { [PlayerIdBrand]: never }

export function asAccountId(id: number): AccountId { return id as AccountId }
export function asPlayerId(id: number): PlayerId { return id as PlayerId }
