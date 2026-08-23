# /latest/api/index.php/equipment/bulk_sell_stack

一键分解（批量出售装备全部 stack），CN 客户端通过装备列表「一键分解」按钮触发。
装备被完全删除，获得锻造石 + 星之粒 + 能力魂。

## Request
### Headers
```
Host: (server host)
Content-Type: application/x-www-form-urlencoded
PARAM: (session token)
SHORT_UDID: (device short udid)
APP_VER: (client version)
...
```

### Body
```json
{
  "equipment_ids": [3030021, 4030001],
  "viewer_id": 297417490,
  "api_count": 19
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `equipment_ids` | `int[]` | 要分解的装备 ID 列表 |
| `viewer_id` | `int` | 玩家 viewer_id |
| `api_count` | `int` | API 调用计数 |

> **注意**：与 `sell_equipment`/`sell_stack` 不同，`bulk_sell_stack` 同时奖励锻造石和星之粒。

## Response
```json
{
  "data_headers": {
    "servertime": 1752772027,
    "viewer_id": 297417490,
    "result_code": 1
  },
  "data": {
    "equipment_list": [
      {
        "null": 1,
        "viewer_id": 0,
        "equipment_id": 1030031,
        "protection": false,
        "level": 1,
        "enhancement_level": 0,
        "stack": 3
      }
    ],
    "item_list": {
      "100000": 1280,
      "990008": 42,
      "3030021": 8,
      "4030001": 6
    },
    "mail_arrived": false
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `equipment_list` | `object[]` | 分解后**全部剩余**装备的完整快照（被分解的已删除） |
| `item_list` | `Record<int, int>` | 更新的物品：`100000`（锻造石）、`990008`（星之粒）、装备 ID（能力魂） |
| `mail_arrived` | `bool` | 是否有新邮件 |

## 实现逻辑

### 奖励计算
每件装备按 `稀有度 × stack` 发放：
```
craftPoint  = dissolving_craft_point[rarity] × stack  → item 100000
starGrain   = dissolving_star_grain[rarity]  × stack  → item 990008
abilitySoul = stack                                      → item equipmentId
```

### 操作
1. 累加所有装备的奖励（Phase 1）
2. 删除装备记录 `deletePlayerEquipmentSync`
3. 发放锻造石、星之粒、能力魂
4. 获取全部剩余装备 → 完整快照返回

### 常量（来源：CDN）

| 稀有度 | dissolving_craft_point | dissolving_star_grain |
|--------|-----------------------|----------------------|
| 1★ | 1 | 0 |
| 2★ | 2 | 0 |
| 3★ | 3 | 1 |
| 4★ | 4 | 5 |
| 5★ | 5 | 15 |

- `craft_point_item_id`: `100000`（锻造石）
- `star_grain_item_id`: `990008`（星之粒）

### 相关文件
- 实现：`src/routes/api/equipment.ts:444`
- 配置：`assets/config.json`（`craft_point_item_id`, `star_grain_item_id`）
- CDN：`equipment_craft_point_exchange.json`, `equipment_dissolve_rate.json`
- 请求：CN 客户端 `EquipmentBulkSellStackRealRemote.as`
- 离线逻辑：CN 客户端 `EquipmentBulkSellStackDummyRemote.as`
