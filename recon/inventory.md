# SolarMind UI Inventory

## App URL
http://localhost:8501/

## Page Structure
- **Overview** (default): sidebar radio "Overview"
- **Inverter detail**: sidebar radio "Inverter detail"

## Sidebar Controls
- Period presets: radio group (7 days / 30 days / 90 days / 12 months / All data / Custom)
  - Selector: `[data-testid="stSidebar"] [data-testid="stRadio"]:first-of-type`
- High-loss month hotspot buttons (below period presets)
  - Selector: buttons containing "· €" in sidebar
- Page navigation: radio group ("Overview" / "Inverter detail")
  - Selector: `[data-testid="stSidebar"] [data-testid="stRadio"]:last-of-type`
- Decision agent toggle: sidebar toggle
  - Selector: `[data-testid="stToggle"]`
- Ask SolarMind form: text input + submit button
  - Selector: `[data-testid="stSidebar"] [data-testid="stForm"]`

## Overview Page Panels
1. Title: "SolarMind: Fix First"
   - Selector: `h1` (first)
2. KPI metrics row (5 columns): Production GWh / Avoidable loss € / Curtailment € / Weather uncertain € / Fault hours
   - Selector: `[data-testid="stMetric"]`
3. "Inverter loss heatmap" subheader + Plotly heatmap
   - Selector: `[data-testid="stPlotlyChart"]`
4. "Fix First ranking" subheader + "Explain this ranking" button + dataframe
   - Selector: `[data-testid="stDataFrame"]`
5. "Early-warning lead time" subheader + 3 metrics + matplotlib timeline chart
   - Selector: `[data-testid="stImageContainer"], [data-testid="stPyplot"]`

## Inverter Detail Page Panels
1. Title: "Inverter evidence"
   - Selector: `h1` (first on detail page)
2. Inverter selectbox (sidebar)
   - Selector: `[data-testid="stSidebar"] [data-testid="stSelectbox"]`
3. 4 KPI metrics: Avoidable loss € / Lost energy kWh / Degradation trend %/yr / Curtailment loss €
   - Selector: `[data-testid="stMetric"]`
4. Demo story warning box (for INV 01.07.045)
   - Selector: `[data-testid="stAlert"]`
5. "Output versus own healthy early-life baseline" line chart
   - Selector: `[data-testid="stVegaLiteChart"]`
6. "Fault-code evidence" table (left column)
   - Selector: `.stColumns [data-testid="stDataFrame"]:first-of-type`
7. "Service tickets" table (right column)
   - Selector: `.stColumns [data-testid="stDataFrame"]:last-of-type`
8. "Evidence-backed work order" table
   - Selector: `[data-testid="stDataFrame"]:last-of-type`
9. "Annual loss attribution" bar chart
   - Selector: `[data-testid="stVegaLiteChart"]:last-of-type`

## Settle Strategy
- Wait for `[data-testid="stStatusWidget"]` to detach, then +1200ms quiet

## Navigation
- Overview → Inverter detail: click sidebar text "Inverter detail"
- Inverter detail → Overview: click sidebar text "Overview"
- Time period: click sidebar radio labels ("30 days", "All data", etc.)
- Inverter selector: stSelectbox in sidebar on detail page
