# Generated Work Orders

Run `python analysis/export_work_orders.py` to rebuild the CSV and top-three PDF work
orders from validated DuckDB tables.

`annual_eur_at_risk` is the mean technical loss for complete years 2024 and 2025.
`lifetime_avoidable_loss_eur` is retained separately and reconciles exactly to M4's
`v_fix_first` ranking. Curtailment remains a separate field.
