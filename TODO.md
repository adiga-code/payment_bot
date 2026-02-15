# TODO List for Payment Bot

## Database Schema Changes

### Remove Bank-Level Limits (Future Task)
**Status:** Pending
**Priority:** Low

Currently, the Bank model has limit fields that should be removed since limits are now managed at the account level (CompanyBank model).

**Fields to remove from `banks` table:**
- `daily_limit`
- `weekly_limit`
- `current_daily_used`
- `current_weekly_used`

**Migration SQL:**
```sql
ALTER TABLE banks
DROP COLUMN IF EXISTS daily_limit,
DROP COLUMN IF EXISTS weekly_limit,
DROP COLUMN IF EXISTS current_daily_used,
DROP COLUMN IF EXISTS current_weekly_used;
```

**Model changes required:**
- Update `bot/database/models.py` - remove limit fields from Bank class
- Remove any references to bank limits in code (currently not used)

---

## Feature Enhancements

### Hierarchical Statistics for Supervisor
**Status:** Not Implemented
**Priority:** Medium

Implement detailed hierarchical statistics showing:
- Date → Clients → Companies → Banks → Individual Applications with numbers

**Requirements:**
- No depth limits - show all levels
- Display application numbers in statistics
- Nested structure with subtotals at each level
- Example format:
  ```
  12.02.2026 - 15 заявок на сумму 17,000,000₽
    └─ Клиент "Сингапур" - 8 заявок
       └─ Компания "Кванти" - 5 заявок
          └─ Альфа банк
             ├─ Заявка №1 от "Сингапур" - 500,000₽
             ├─ Заявка №2 от "Виндовс" - 1,000,000₽
             └─ Заявка №3 от "Сингапур" - 2,500,000₽
             Итого: 4,000,000₽
  ```

**Implementation approach:**
- Add new callback handler `cb_stats_hierarchical` in supervisor.py
- Create data structure builder method
- Create hierarchical text formatter
- Add keyboard navigation for drilling down/up levels
- Consider adding pagination for large datasets

---

_Last updated: 2026-02-15_
