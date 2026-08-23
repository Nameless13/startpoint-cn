export interface EquipmentDissolveEntry {
    ability_soul_id: number
    obtain_source: number
    generate_ability_soul: boolean
    max_level: number
}


export interface ItemSaleEntry {
    category: number
    sale_price: number
    sellable: boolean
}


export interface EquipmentCraftEntry {
    dissolve_craft: number
    awakening_craft: number
    dissolve_star: number
}
