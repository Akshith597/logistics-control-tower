"""Multipage browser companion for the Logistics Control Tower report."""
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

ROOT = Path(__file__).parent / "data" / "public_dashboard"
PAGES = ["Executive Overview", "Carrier & Lane Performance", "Warehouse Operations",
         "Profitability", "Customer Experience & Claims", "Shipment Detail",
         "Data Quality & Coverage"]
st.set_page_config(page_title="Logistics Control Tower", page_icon="🚚", layout="wide")


@st.cache_data(show_spinner=False)
def load_data():
    files = {"fact": "fact_shipment.parquet", "carrier": "dim_carrier.parquet",
             "warehouse": "dim_warehouse.parquet", "customer": "dim_customer.parquet"}
    missing = [v for v in files.values() if not (ROOT / v).exists()]
    if missing:
        raise FileNotFoundError("Missing dashboard exports: " + ", ".join(missing))
    data = {k: pd.read_parquet(ROOT / v) for k, v in files.items()}
    f = data["fact"]
    for c in ["ship_date", "promised_delivery_date", "actual_delivery_date"]:
        f[c] = pd.to_datetime(f[c], errors="coerce")
    f["carrier_name"] = f.carrier_key.map(data["carrier"].set_index("carrier_key").carrier_legal_name).fillna("Unknown carrier")
    f["warehouse_name"] = f.warehouse_key.map(data["warehouse"].set_index("warehouse_key").warehouse_name).fillna("Unknown warehouse")
    f["customer_name"] = f.customer_key.map(data["customer"].set_index("customer_key").legal_name).fillna("Unknown customer")
    f["lane"] = f.warehouse_name + " → " + f.dest_city.fillna("Unknown") + ", " + f.dest_state.fillna("??")
    return f


def div(a, b): return float(a) / float(b) if b else None
def pct(v): return "—" if v is None or pd.isna(v) else f"{v:.1%}"
def usd(v, compact=False): return f"${v/1_000_000:.1f}M" if compact else f"${v:,.0f}"


def summary(d):
    official = d[d.official_kpi_eligible_flag.fillna(False)]
    otd, otif = official[official.final_on_time_flag.notna()], official[official.otif_flag.notna()]
    fill = official[official.shipment_fill_rate.notna()]
    revenue, margin = d.customer_revenue_usd.fillna(0).sum(), d.gross_margin_usd.fillna(0).sum()
    return {"n": len(d), "official": len(official), "otd_n": len(otd), "otif_n": len(otif),
            "fill_n": len(fill), "otd": div(otd.final_on_time_flag.sum(), len(otd)),
            "otif": div(otif.otif_flag.sum(), len(otif)), "fill": div((fill.shipment_fill_rate >= 1).sum(), len(fill)),
            "late": int((~otd.final_on_time_flag.fillna(True)).sum()), "revenue": float(revenue),
            "cost": float(d.carrier_cost_usd.fillna(0).sum()), "claims_paid": float(d.claims_paid_usd.fillna(0).sum()),
            "margin": float(margin), "margin_pct": div(margin, revenue),
            "complaints": int(d.complaint_flag.fillna(False).sum()), "claims": int(d.claim_flag.fillna(False).sum())}


def grouped(d, by, label):
    rows = []
    for name, g in d.groupby(by, dropna=False):
        s = summary(g)
        rows.append({label: name, "Shipments": s["n"], "OTD": s["otd"], "OTIF": s["otif"],
                     "Full-fill": s["fill"], "Late": s["late"], "Revenue": s["revenue"],
                     "Carrier cost": s["cost"], "Claims paid": s["claims_paid"],
                     "Gross margin": s["margin"], "Margin rate": s["margin_pct"],
                     "Complaints / 1K": div(1000*s["complaints"], s["n"]),
                     "Claim rate": div(s["claims"], s["n"])})
    return pd.DataFrame(rows)


def monthly(d):
    x = d[d.ship_date.notna()].copy()
    x["Month"] = x.ship_date.dt.to_period("M").dt.to_timestamp()
    rows = []
    for month, g in x.groupby("Month"):
        s = summary(g); rows.append({"Month": month, "Shipments": s["n"], "OTD": s["otd"],
                                     "OTIF": s["otif"], "Gross margin": s["margin"]})
    return pd.DataFrame(rows).set_index("Month") if rows else pd.DataFrame()


def metrics(items):
    for col, item in zip(st.columns(len(items)), items):
        label, value, *help_text = item
        col.metric(label, value, help=help_text[0] if help_text else None)


def table(df, percent=(), currency=(), integer=()):
    fmt = {c: "{:.1%}" for c in percent if c in df}
    fmt.update({c: "${:,.0f}" for c in currency if c in df})
    fmt.update({c: "{:,.0f}" for c in integer if c in df})
    st.dataframe(df.style.format(fmt, na_rep="—"), width="stretch", hide_index=True)


def executive(d):
    st.header("Executive Overview"); st.caption("Are service and profitability healthy, and where should leadership act first?")
    s = summary(d)
    metrics([("Shipments", f"{s['n']:,}"), ("On-time delivery", pct(s["otd"]), f"{s['otd_n']:,} eligible"),
             ("OTIF", pct(s["otif"]), f"{s['otif_n']:,} eligible"), ("Full-fill", pct(s["fill"]), f"{s['fill_n']:,} eligible"),
             ("Gross margin", pct(s["margin_pct"])), ("Complaints / 1K", f"{div(1000*s['complaints'],s['n']):.1f}" if s["n"] else "—")])
    trend = monthly(d); a, b = st.columns(2)
    with a: st.subheader("Monthly service"); st.line_chart(trend, y=["OTD", "OTIF"], height=300)
    with b: st.subheader("Monthly gross margin"); st.line_chart(trend, y=["Gross margin"], height=300)
    c = grouped(d, "carrier_name", "Carrier").sort_values("Late", ascending=False)
    st.subheader("Carrier risk ranking"); st.bar_chart(c.set_index("Carrier")[["Late"]], height=260)
    table(c, ["OTD", "OTIF", "Margin rate"], ["Gross margin"], ["Shipments", "Late"])


def carrier_lane(d):
    st.header("Carrier & Lane Performance"); st.caption("Which partners and lanes combine poor service with high cost?")
    s = summary(d); late_days = d.loc[d.days_late.gt(0), "days_late"].mean()
    metrics([("Official KPI shipments", f"{s['official']:,}"), ("On-time delivery", pct(s["otd"])),
             ("Average days late", f"{late_days:.1f}" if pd.notna(late_days) else "—"),
             ("Cost / shipment", usd(div(s["cost"], s["n"])) if s["n"] else "—"),
             ("Claim rate", pct(div(s["claims"], s["n"])))])
    c = grouped(d, "carrier_name", "Carrier"); c["Cost / shipment"] = c["Carrier cost"] / c.Shipments
    chart = alt.Chart(c).mark_circle(opacity=.8).encode(x="Cost / shipment:Q", y=alt.Y("OTD:Q", axis=alt.Axis(format="%")),
        size="Shipments:Q", color="Carrier:N", tooltip=["Carrier", "Shipments", alt.Tooltip("OTD:Q", format=".1%"), alt.Tooltip("Cost / shipment:Q", format="$,.0f")]).properties(height=340)
    st.altair_chart(chart, width="stretch")
    lanes = grouped(d, "lane", "Lane").sort_values(["Late", "Shipments"], ascending=False)
    st.subheader("Lane risk queue"); table(lanes, ["OTD", "OTIF", "Margin rate", "Claim rate"], ["Carrier cost", "Gross margin"], ["Shipments", "Late"])


def warehouse(d):
    st.header("Warehouse Operations"); st.caption("Where do fulfillment speed and inventory execution coincide with service risk?")
    s = summary(d)
    metrics([("Cycle hours", f"{d.warehouse_cycle_hours.mean():.1f}"), ("Pick-to-pack", f"{d.pick_to_pack_hours.mean():.1f} hrs"),
             ("Pack-to-ship", f"{d.pack_to_ship_hours.mean():.1f} hrs"), ("Full-fill", pct(s["fill"])),
             ("Short-pick rate", pct(d.short_pick_flag.mean())), ("Inventory accuracy", pct(d.average_inventory_accuracy.mean()))])
    rows=[]
    for name,g in d.groupby("warehouse_name"):
        z=summary(g); rows.append({"Warehouse":name,"Shipments":len(g),"OTD":z["otd"],"Full-fill":z["fill"],"Cycle hours":g.warehouse_cycle_hours.mean(),"Short-pick rate":g.short_pick_flag.mean(),"Inventory accuracy":g.average_inventory_accuracy.mean()})
    x=pd.DataFrame(rows); st.subheader("Warehouse scorecard"); table(x,["OTD","Full-fill","Short-pick rate","Inventory accuracy"],integer=["Shipments"])
    if not x.empty:
        st.altair_chart(alt.Chart(x).mark_circle(size=180).encode(x="Cycle hours:Q",y=alt.Y("OTD:Q",axis=alt.Axis(format="%")),color="Warehouse:N",tooltip=list(x.columns)).properties(height=330),width="stretch")


def profitability(d):
    st.header("Profitability"); st.caption("Which customers and lanes create or erode value?")
    s=summary(d); metrics([("Revenue",usd(s["revenue"],True)),("Carrier cost",usd(s["cost"],True)),("Claims paid",usd(s["claims_paid"],True)),("Gross margin",usd(s["margin"],True)),("Gross margin %",pct(s["margin_pct"])),("Margin / shipment",usd(div(s["margin"],s["n"])) if s["n"] else "—")])
    c=grouped(d,"customer_name","Customer")
    if not c.empty:
        st.altair_chart(alt.Chart(c).mark_circle(opacity=.8).encode(x="Revenue:Q",y=alt.Y("Margin rate:Q",axis=alt.Axis(format="%")),size="Shipments:Q",color="Customer:N",tooltip=["Customer","Shipments",alt.Tooltip("Revenue:Q",format="$,.0f"),alt.Tooltip("Margin rate:Q",format=".1%")]).properties(height=340),width="stretch")
    lanes=grouped(d,"lane","Lane").sort_values("Gross margin"); st.subheader("Lowest-margin lanes")
    table(lanes,["Margin rate","OTD"],["Revenue","Carrier cost","Claims paid","Gross margin"],["Shipments"])


def customers(d):
    st.header("Customer Experience & Claims"); st.caption("Where do service failures coincide with complaints, claims, and poor sentiment?")
    s=summary(d); responses=int(d.survey_response_count.fillna(0).sum()); nps=div(100*(d.promoter_count.sum()-d.detractor_count.sum()),responses)
    metrics([("Complaint rate",pct(div(s["complaints"],s["n"]))),("Complaints / 1K",f"{div(1000*s['complaints'],s['n']):.1f}" if s["n"] else "—"),("Claim rate",pct(div(s["claims"],s["n"]))),("Claims paid",usd(s["claims_paid"],True)),("Average CSAT",f"{d.average_csat_score.mean():.2f}" if d.average_csat_score.notna().any() else "—"),("NPS",f"{nps:.1f}" if nps is not None else "—")])
    st.info(f"Survey response coverage: {responses:,} responses across {s['n']:,} shipments ({div(responses,s['n']):.1%})." if s["n"] else "No shipments match the filters.")
    c=grouped(d,"customer_name","Customer")
    if not c.empty:
        st.altair_chart(alt.Chart(c).mark_circle(opacity=.8).encode(x=alt.X("OTD:Q",axis=alt.Axis(format="%")),y="Complaints / 1K:Q",size="Shipments:Q",color="Customer:N",tooltip=["Customer","Shipments",alt.Tooltip("OTD:Q",format=".1%")]).properties(height=340),width="stretch")
    st.subheader("Customer claim and complaint queue"); table(c.sort_values(["Claims paid","Complaints / 1K"],ascending=False),["OTD","Claim rate"],["Claims paid"],["Shipments"])


def detail(d):
    st.header("Shipment Detail"); st.caption("Inspect one shipment's operational, financial, and customer signals.")
    if d.empty: st.warning("No shipments match the filters."); return
    selected=st.selectbox("Shipment ID",sorted(d.tms_shipment_id.dropna().astype(str))); r=d[d.tms_shipment_id.astype(str).eq(selected)].iloc[0]
    status="Unresolved" if pd.isna(r.final_on_time_flag) else ("On time" if bool(r.final_on_time_flag) else "Late")
    metrics([("Status",status),("Mode / service",f"{r['mode']} · {r['service_level_name']}"),("Promised",str(r.promised_delivery_date.date()) if pd.notna(r.promised_delivery_date) else "—"),("Delivered",str(r.actual_delivery_date.date()) if pd.notna(r.actual_delivery_date) else "—"),("Days late",f"{r.days_late:.0f}" if pd.notna(r.days_late) else "—")])
    a,b=st.columns(2)
    with a: st.subheader("Operations"); st.json({"warehouse":r.warehouse_name,"carrier":r.carrier_name,"lane":r.lane,"exception":r.exception_code,"warehouse_cycle_hours":r.warehouse_cycle_hours,"fill_rate":r.shipment_fill_rate,"short_pick":bool(r.short_pick_flag) if pd.notna(r.short_pick_flag) else None})
    with b: st.subheader("Financial & customer"); st.json({"customer":r.customer_name,"revenue_usd":r.customer_revenue_usd,"carrier_cost_usd":r.carrier_cost_usd,"claims_paid_usd":r.claims_paid_usd,"gross_margin_usd":r.gross_margin_usd,"ticket_count":r.ticket_count,"csat":r.average_csat_score,"nps":r.shipment_nps})


def quality(d, full):
    st.header("Data Quality & Coverage"); st.caption("How much confidence should the audience place in each part of the analysis?")
    cov={"Ship date":d.ship_date.notna().mean(),"Customer match":d.customer_key.notna().mean(),"Carrier match":d.carrier_key.notna().mean(),"Warehouse match":d.warehouse_key.notna().mean(),"Invoice match":d.invoice_count.gt(0).mean(),"WMS match":d.wms_record_count.gt(0).mean(),"Fill rate":d.shipment_fill_rate.notna().mean(),"Survey response":d.survey_response_count.gt(0).mean()}
    metrics([(k,pct(v)) for k,v in list(cov.items())[:6]])
    s=summary(d); rows=[{"Measure":k,"Coverage":v,"Covered rows":round(len(d)*v),"Total rows":len(d)} for k,v in cov.items()]
    rows += [{"Measure":"OTD eligible","Coverage":div(s["otd_n"],len(d)),"Covered rows":s["otd_n"],"Total rows":len(d)},{"Measure":"OTIF eligible","Coverage":div(s["otif_n"],len(d)),"Covered rows":s["otif_n"],"Total rows":len(d)}]
    st.subheader("KPI eligibility and coverage"); table(pd.DataFrame(rows),["Coverage"],integer=["Covered rows","Total rows"])
    st.warning(f"{full.ship_date.isna().sum():,} shipments have no ship date and are excluded from date-filtered analytical pages.")
    st.info("Synthetic portfolio dataset · Shipment grain · Official service KPIs require an eligible shipment and a resolved outcome.")


try: fact=load_data()
except FileNotFoundError as e: st.error(str(e)); st.stop()
st.markdown("<style>.block-container{padding-top:1.6rem}[data-testid=stMetricValue]{letter-spacing:-.035em}.kicker{color:#0b7285;font-weight:700;text-transform:uppercase;letter-spacing:.08em;font-size:.75rem}</style><div class=kicker>Interactive portfolio report</div><h1>Logistics Control Tower</h1>",unsafe_allow_html=True)
with st.sidebar:
    st.title("🚚 Control Tower"); page=st.radio("Navigate",PAGES,label_visibility="collapsed"); st.divider(); st.subheader("Global filters")
    selections={c:st.multiselect(label,sorted(fact[c].dropna().unique())) for c,label in [("carrier_name","Carrier"),("warehouse_name","Warehouse"),("customer_name","Customer"),("mode","Transportation mode"),("dest_state","Destination state")]}
    dated=fact[fact.ship_date.notna()]; dates=st.date_input("Shipment date",value=(dated.ship_date.min().date(),dated.ship_date.max().date()),min_value=dated.ship_date.min().date(),max_value=dated.ship_date.max().date())
    st.divider(); st.link_button("Download PBIX","https://github.com/Akshith597/logistics-control-tower/releases/latest/download/Logistics_Control_Tower.pbix",width="stretch"); st.link_button("View source","https://github.com/Akshith597/logistics-control-tower",width="stretch")
filtered=fact.copy()
for c,values in selections.items():
    if values: filtered=filtered[filtered[c].isin(values)]
start,end=dates if isinstance(dates,tuple) and len(dates)==2 else (dates,dates)
filtered=filtered[filtered.ship_date.notna() & filtered.ship_date.dt.date.between(start,end)]
st.caption(f"{len(filtered):,} dated shipments in the current view · {start} to {end}")
if filtered.empty:
    st.warning("No dated shipments match the current filters. Adjust the filters in the sidebar.")
    st.stop()
render={"Executive Overview":executive,"Carrier & Lane Performance":carrier_lane,"Warehouse Operations":warehouse,"Profitability":profitability,"Customer Experience & Claims":customers,"Shipment Detail":detail}
quality(filtered,fact) if page=="Data Quality & Coverage" else render[page](filtered)
st.divider(); st.caption("Rates are recalculated at shipment grain using eligible denominators. Associations shown are descriptive, not causal.")
