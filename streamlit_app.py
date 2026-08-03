import json
from pathlib import Path

import pandas as pd
import streamlit as st

from edf_importer import DRIVE_URL, import_data


ROOT = Path(__file__).parent
DATA_PATH = ROOT / "data" / "db.json"
APP_VERSION = "periodo-sin-total-2026-08-03"


st.set_page_config(page_title="EDF Repago", page_icon="EDF", layout="wide")

st.markdown(
    """
    <style>
      .block-container { padding-top: 1.4rem; padding-bottom: 2rem; }
      div[data-testid="stMetric"] {
        background: rgba(255,255,255,.04);
        border: 1px solid rgba(255,255,255,.08);
        border-radius: 10px;
        padding: .8rem .9rem;
      }
      .edf-card {
        border: 1px solid rgba(255,255,255,.12);
        border-radius: 10px;
        padding: .85rem .9rem;
        margin: .55rem 0;
        background: rgba(255,255,255,.035);
      }
      .edf-card-title { font-weight: 800; font-size: 1rem; margin-bottom: .2rem; }
      .edf-card-sub { color: rgba(250,250,250,.72); font-size: .86rem; margin-bottom: .45rem; }
      .edf-badges { display: flex; flex-wrap: wrap; gap: .35rem; margin-top: .45rem; }
      .edf-badge {
        border-radius: 999px;
        padding: .16rem .48rem;
        font-size: .78rem;
        font-weight: 700;
        background: rgba(15,143,109,.18);
        border: 1px solid rgba(15,143,109,.28);
      }
      @media (max-width: 700px) {
        .block-container { padding-left: .75rem; padding-right: .75rem; }
        h1 { font-size: 1.85rem !important; }
        h2, h3 { font-size: 1.22rem !important; }
        div[data-testid="stMetric"] { padding: .65rem .7rem; }
        div[data-testid="stMetricValue"] { font-size: 1.55rem; }
        .stTabs [data-baseweb="tab-list"] { gap: .25rem; overflow-x: auto; }
        .stTabs [data-baseweb="tab"] { padding-left: .45rem; padding-right: .45rem; }
      }
    </style>
    """,
    unsafe_allow_html=True,
)


def load_db_from_disk():
    if not DATA_PATH.exists():
        return None
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def load_db_from_upload(uploaded_file):
    if uploaded_file is None:
        return None
    return json.loads(uploaded_file.getvalue().decode("utf-8"))


@st.cache_data(ttl=900, show_spinner=False)
def load_db_from_drive(folder_url):
    return import_data(sync=True, folder_url=folder_url)


def band_label(pct, hl):
    if hl <= 0:
        return "Venta 0"
    if pct < 25:
        return "0%-25%"
    if pct < 50:
        return "25%-50%"
    if pct < 75:
        return "50%-75%"
    if pct < 100:
        return "75%-99%"
    return "100%+"


def get_repayment(edf):
    repayment = edf.get("repayment") or {}
    return {
        "hl": repayment.get("hl") or 0,
        "pct": repayment.get("pct") or 0,
        "target": repayment.get("target") or 0,
        "minimum": repayment.get("minimum") or 0,
        "band": (repayment.get("band") or {}).get("label") or "",
    }


def available_periods(db):
    periods = set()
    for customer in db.get("customers", []):
        monthly = customer.get("monthlySalesByBusiness") or {}
        for business_data in monthly.values():
            periods.update((business_data or {}).keys())
    return sorted(periods)


def selected_periods(db, period_mode):
    periods = available_periods(db)
    if not periods:
        return []
    if period_mode == "Total cargado":
        return periods
    if period_mode == "Mes corriente":
        return [periods[-1]]
    return periods[-3:]


def business_hl_for_period(customer, business, periods, average=False):
    monthly = customer.get("monthlySalesByBusiness") or {}
    values = monthly.get(business) or {}
    total = sum(float(values.get(period, 0) or 0) for period in periods)
    if average and periods:
        return round(total / len(periods), 3)
    return round(total, 3)


def repayment_for_values(hl, target):
    pct = round((hl / target) * 100) if target else 0
    return {
        "hl": round(hl, 3),
        "pct": pct,
        "target": target,
        "minimum": round(target * 0.75, 3),
        "band": band_label(pct, hl),
    }


def period_repayment_map(db, periods, average):
    edfs = db.get("edfs", [])
    customers = {str(customer.get("id")): customer for customer in db.get("customers", [])}
    repayment = {}
    grouped = {}
    for edf in edfs:
        if edf.get("status") != "PDV" or not edf.get("customerId"):
            continue
        key = (str(edf.get("customerId")), edf.get("business") or "OTROS")
        grouped.setdefault(key, []).append(edf)

    for group in grouped.values():
        group.sort(key=lambda item: (item.get("asset") or "", item.get("serial") or ""))

    for (customer_id, business), group in grouped.items():
        customer = customers.get(customer_id) or {}
        available_hl = business_hl_for_period(customer, business, periods, average=average)
        total_target = sum((get_repayment(edf)["target"] or 1.6) for edf in group) or 1
        for edf in group:
            base = get_repayment(edf)
            target = base["target"] or 1.6
            assigned = min(target, available_hl * (target / total_target))
            repayment[edf.get("id")] = repayment_for_values(assigned, target)
    return repayment


def status_label(status):
    labels = {
        "PDV": "En PDV",
        "DEPOSITO": "Deposito",
        "STOCK": "Stock",
        "REPARACION": "Reparacion",
        "BAJA DEFINITIVA": "Baja definitiva",
    }
    return labels.get(status or "", status or "-")


def build_edf_rows(db, period_mode="Trimestre promedio"):
    periods = selected_periods(db, period_mode)
    use_period = period_mode != "Total cargado"
    period_map = period_repayment_map(db, periods, average=period_mode == "Trimestre promedio") if use_period else {}
    rows = []
    for edf in db.get("edfs", []):
        customer = edf.get("customer") or {}
        repayment = period_map.get(edf.get("id"), get_repayment(edf))
        if use_period and edf.get("status") == "PDV":
            period_hl = business_hl_for_period(
                customer,
                edf.get("business") or "OTROS",
                periods,
                average=period_mode == "Trimestre promedio",
            )
            if repayment["hl"] > period_hl:
                target = repayment["target"] or get_repayment(edf)["target"] or 1.6
                repayment = repayment_for_values(min(period_hl, target), target)
        rows.append({
            "Cliente": customer.get("name") or "",
            "Nombre fantasia": customer.get("fantasyName") or customer.get("name") or "",
            "Razon social": customer.get("legalName") or "",
            "Codigo cliente": customer.get("id") or edf.get("customerId") or "",
            "Negocio": edf.get("business") or "OTROS",
            "Supervisor": customer.get("supervisor") or "Sin supervisor",
            "Promotor": customer.get("promoter") or customer.get("seller") or "Sin promotor",
            "Ruta": customer.get("route") or "",
            "Activo": edf.get("asset") or "",
            "Serie": edf.get("serial") or "",
            "Modelo": edf.get("model") or "",
            "Estado": status_label(edf.get("status")),
            "Deposito": edf.get("deposit") or "",
            "HL": repayment["hl"],
            "Objetivo": repayment["target"],
            "Minimo": repayment["minimum"],
            "% Repago": repayment["pct"],
            "Banda": repayment["band"],
            "Periodo": period_mode,
            "Meses usados": ", ".join(periods) if periods else "Sin ventas",
        })
    return pd.DataFrame(rows)


def build_customer_rows(db):
    rows = []
    for customer in db.get("customers", []):
        sales = customer.get("salesByBusiness") or {}
        rows.append({
            "Codigo": customer.get("id") or "",
            "Cliente": customer.get("name") or "",
            "Nombre fantasia": customer.get("fantasyName") or customer.get("name") or "",
            "Razon social": customer.get("legalName") or "",
            "Direccion": customer.get("address") or "",
            "Localidad": customer.get("city") or "",
            "Ruta": customer.get("route") or "",
            "Promotor": customer.get("promoter") or customer.get("seller") or "Sin promotor",
            "Supervisor": customer.get("supervisor") or "Sin supervisor",
            "PI": "Si" if customer.get("pi") else "No",
            "PI tipos": ", ".join(customer.get("piTypes") or []),
            "HL CZA": sales.get("CZA") or 0,
            "HL UNG": sales.get("UNG") or 0,
            "HL AGUAS": sales.get("AGUAS") or 0,
            "HL RB": sales.get("RB") or 0,
        })
    return pd.DataFrame(rows)


def equipment_reference(avg_hl):
    if avg_hl >= 1.875:
        return "Puede colocar Vertical grande"
    if avg_hl >= 0.9:
        return "Puede colocar Slim"
    if avg_hl > 0:
        return "No colocar todavia"
    return "Sin venta trimestre"


def build_opportunity_rows(db):
    periods = selected_periods(db, "Trimestre promedio")
    edf_counts = {}
    for edf in db.get("edfs", []):
        if edf.get("status") != "PDV" or not edf.get("customerId"):
            continue
        key = (str(edf.get("customerId")), edf.get("business") or "OTROS")
        edf_counts[key] = edf_counts.get(key, 0) + 1

    rows = []
    for customer in db.get("customers", []):
        customer_id = str(customer.get("id") or "")
        for business in ["CZA", "UNG", "AGUAS", "RB"]:
            total_hl = business_hl_for_period(customer, business, periods, average=False)
            avg_hl = business_hl_for_period(customer, business, periods, average=True)
            if avg_hl <= 0 and edf_counts.get((customer_id, business), 0) == 0:
                continue
            reference = equipment_reference(avg_hl)
            can_place = reference.startswith("Puede")
            rows.append({
                "Codigo cliente": customer_id,
                "Cliente": customer.get("name") or "",
                "Nombre fantasia": customer.get("fantasyName") or customer.get("name") or "",
                "Razon social": customer.get("legalName") or "",
                "Negocio": business,
                "Supervisor": customer.get("supervisor") or "Sin supervisor",
                "Promotor": customer.get("promoter") or customer.get("seller") or "Sin promotor",
                "Ruta": customer.get("route") or "",
                "HL total trimestre": total_hl,
                "HL trimestre promedio": avg_hl,
                "Referencia": reference,
                "Puede colocar": "Si" if can_place else "No",
                "EDF actuales negocio": edf_counts.get((customer_id, business), 0),
                "Meses usados": ", ".join(periods) if periods else "Sin ventas",
            })
    return pd.DataFrame(rows)


def csv_download(df):
    return df.to_csv(index=False, sep=";").encode("utf-8-sig")


def compact_text(value, fallback="-"):
    text = "" if pd.isna(value) else str(value)
    return text if text.strip() else fallback


def render_card_list(df, kind, limit=80):
    if df.empty:
        st.info("No hay resultados para mostrar.")
        return
    st.caption(f"Mostrando {min(len(df), limit)} de {len(df)} registros en vista celular.")
    for _, row in df.head(limit).iterrows():
        if kind == "repago":
            title = f"{compact_text(row.get('Codigo cliente'))} · {compact_text(row.get('Nombre fantasia') or row.get('Cliente'))}"
            sub = f"{compact_text(row.get('Negocio'))} · {compact_text(row.get('Modelo'))} · Serie {compact_text(row.get('Serie'))}"
            badges = [
                compact_text(row.get("Estado")),
                compact_text(row.get("Supervisor")),
                f"{compact_text(row.get('HL'))} HL",
                f"{compact_text(row.get('% Repago'))}%",
                compact_text(row.get("Banda")),
            ]
        elif kind == "opportunity":
            title = f"{compact_text(row.get('Codigo cliente'))} · {compact_text(row.get('Nombre fantasia') or row.get('Cliente'))}"
            sub = f"{compact_text(row.get('Negocio'))} · {compact_text(row.get('Supervisor'))} · {compact_text(row.get('Promotor'))}"
            badges = [
                f"{compact_text(row.get('HL trimestre promedio'))} HL prom.",
                f"{compact_text(row.get('HL total trimestre'))} HL trim.",
                compact_text(row.get("Referencia")),
                f"EDF {compact_text(row.get('EDF actuales negocio'))}",
            ]
        else:
            title = f"{compact_text(row.get('Codigo') or row.get('Codigo cliente'))} · {compact_text(row.get('Nombre fantasia') or row.get('Cliente'))}"
            sub = f"{compact_text(row.get('Supervisor'))} · {compact_text(row.get('Promotor'))}"
            badges = [compact_text(row.get("Ruta")), compact_text(row.get("PI"))]
        badge_html = "".join(f"<span class='edf-badge'>{badge}</span>" for badge in badges if badge and badge != "-")
        st.markdown(
            f"""
            <div class="edf-card">
              <div class="edf-card-title">{title}</div>
              <div class="edf-card-sub">{sub}</div>
              <div class="edf-badges">{badge_html}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_filters(df):
    f1, f2, f3, f4, f5, f6 = st.columns(6)
    business = f1.selectbox("Negocio", ["Todos"] + sorted(df["Negocio"].dropna().unique().tolist()))
    supervisor = f2.selectbox("Supervisor", ["Todos"] + sorted(df["Supervisor"].dropna().unique().tolist()))
    promoter = f3.selectbox("Promotor", ["Todos"] + sorted(df["Promotor"].dropna().unique().tolist()))
    state_order = ["En PDV", "Deposito", "Baja definitiva", "Reparacion", "Stock"]
    states = [state for state in state_order if state in set(df["Estado"].dropna().unique())]
    status = f4.selectbox("Estado", ["Todos"] + states)
    search_by = f5.selectbox("Buscar por", ["Todo", "Codigo cliente", "Cliente", "Activo", "Serie"])
    query = f6.text_input("Buscar")

    filtered = df.copy()
    if query and search_by == "Codigo cliente":
        q = query.lower()
        normalized = filtered["Codigo cliente"].astype(str).str.replace(r"\.0$", "", regex=True).str.lower()
        return filtered[normalized.str.startswith(q, na=False) | normalized.eq(q)]

    if business != "Todos":
        filtered = filtered[filtered["Negocio"] == business]
    if supervisor != "Todos":
        filtered = filtered[filtered["Supervisor"] == supervisor]
    if promoter != "Todos":
        filtered = filtered[filtered["Promotor"] == promoter]
    if status != "Todos":
        filtered = filtered[filtered["Estado"] == status]
    if query:
        q = query.lower()
        normalized_query = q.replace("%", "").replace("-", " ").strip()
        if normalized_query in {"venta 0", "venta cero", "sin venta"}:
            filtered = filtered[filtered["Banda"].astype(str).str.lower().eq("venta 0")]
        elif normalized_query in {"0 25", "0 a 25"}:
            filtered = filtered[filtered["Banda"].astype(str).str.lower().eq("0%-25%")]
        elif normalized_query in {"25 50", "25 a 50"}:
            filtered = filtered[filtered["Banda"].astype(str).str.lower().eq("25%-50%")]
        elif normalized_query in {"50 75", "50 a 75"}:
            filtered = filtered[filtered["Banda"].astype(str).str.lower().eq("50%-75%")]
        elif normalized_query in {"75 99", "75 100", "75 a 100"}:
            filtered = filtered[filtered["Banda"].astype(str).str.lower().eq("75%-99%")]
        elif normalized_query in {"100", "100 mas", "100 plus"}:
            filtered = filtered[filtered["Banda"].astype(str).str.lower().eq("100%+")]
        elif search_by == "Cliente":
            filtered = filtered[filtered["Cliente"].astype(str).str.lower().str.contains(q, na=False)]
        elif search_by == "Activo":
            filtered = filtered[filtered["Activo"].astype(str).str.lower().str.contains(q, na=False)]
        elif search_by == "Serie":
            filtered = filtered[filtered["Serie"].astype(str).str.lower().str.contains(q, na=False)]
        else:
            full_match = filtered.apply(lambda row: q in " ".join(map(str, row.values)).lower(), axis=1)
            filtered = filtered[full_match]
    return filtered


def render_opportunity_filters(df):
    f1, f2, f3, f4, f5, f6 = st.columns(6)
    business = f1.selectbox("Negocio", ["Todos"] + sorted(df["Negocio"].dropna().unique().tolist()), key="opp_business")
    supervisor = f2.selectbox("Supervisor", ["Todos"] + sorted(df["Supervisor"].dropna().unique().tolist()), key="opp_supervisor")
    promoter = f3.selectbox("Promotor", ["Todos"] + sorted(df["Promotor"].dropna().unique().tolist()), key="opp_promoter")
    placement = f4.selectbox("Colocacion", ["Todos", "Puede colocar", "No colocar", "Sin venta trimestre"], key="opp_placement")
    customer_code = f5.text_input("Codigo cliente", key="opp_customer_code")
    query = f6.text_input("Buscar cliente", key="opp_query")

    filtered = df.copy()
    if business != "Todos":
        filtered = filtered[filtered["Negocio"] == business]
    if supervisor != "Todos":
        filtered = filtered[filtered["Supervisor"] == supervisor]
    if promoter != "Todos":
        filtered = filtered[filtered["Promotor"] == promoter]
    if placement == "Puede colocar":
        filtered = filtered[filtered["Puede colocar"] == "Si"]
    elif placement == "No colocar":
        filtered = filtered[(filtered["Puede colocar"] == "No") & (filtered["Referencia"] != "Sin venta trimestre")]
    elif placement == "Sin venta trimestre":
        filtered = filtered[filtered["Referencia"] == "Sin venta trimestre"]
    if customer_code:
        q_code = customer_code.strip().lower()
        normalized = filtered["Codigo cliente"].astype(str).str.replace(r"\.0$", "", regex=True).str.lower()
        filtered = filtered[normalized.str.startswith(q_code, na=False) | normalized.eq(q_code)]
    if query:
        q = query.lower()
        full_match = filtered.apply(lambda row: q in " ".join(map(str, row.values)).lower(), axis=1)
        filtered = filtered[full_match]
    return filtered


st.title("EDF Repago")
st.caption("Dashboard operativo by QπU")

with st.sidebar:
    st.header("Datos")
    st.caption(f"Version: {APP_VERSION}")
    st.caption("Fuente principal: Google Drive")
    st.header("Google Drive")
    drive_url = st.text_input("Carpeta Drive", value=DRIVE_URL)
    sync_now = st.button("Sincronizar Drive e importar")

if sync_now:
    load_db_from_drive.clear()

try:
    with st.spinner("Leyendo Drive y generando base..."):
        db = load_db_from_drive(drive_url)
except Exception as exc:
    st.error("No se pudo importar desde Drive.")
    st.write("Revisa que la carpeta de Drive este compartida como publica o accesible por enlace y que tenga los archivos fuente.")
    st.exception(exc)
    st.stop()

with st.sidebar:
    meta = db.get("meta") or {}
    if meta:
        st.divider()
        st.caption(f"Ultima importacion: {meta.get('importedAt', '-')}")
        if meta.get("semaforoFile"):
            st.caption(f"Semaforo leido: {meta.get('semaforoFile')}")
            st.caption(f"Filas semaforo: {meta.get('semaforoRows', 0)}")
        semaforo_candidates = meta.get("semaforoCandidates") or []
        if semaforo_candidates:
            with st.expander("Semaforos encontrados"):
                for file_name in semaforo_candidates:
                    st.caption(f"- {file_name}")
        sales_files = meta.get("salesFiles") or []
        if sales_files:
            st.caption("Ventas leidas:")
            for file_name in sales_files:
                st.caption(f"- {file_name}")
        ignored_sales_files = meta.get("ignoredSalesFiles") or []
        if ignored_sales_files:
            st.caption("Ventas ignoradas:")
            for file_name in ignored_sales_files:
                st.caption(f"- {file_name}")
        ignored_drive_files = meta.get("ignoredDriveFiles") or []
        if ignored_drive_files:
            with st.expander("Archivos de Drive ignorados"):
                for file_name in ignored_drive_files:
                    st.caption(f"- {file_name}")

period_mode = st.selectbox("Periodo de repago", ["Trimestre promedio", "Mes corriente"])
edf_df = build_edf_rows(db, period_mode)
customer_df = build_customer_rows(db)
opportunity_df = build_opportunity_rows(db)

placed = edf_df[edf_df["Estado"] == "En PDV"] if not edf_df.empty else edf_df
available = edf_df[edf_df["Estado"].isin(["Stock", "Deposito"])] if not edf_df.empty else edf_df
under_75 = placed[placed["% Repago"] < 75] if not placed.empty else placed

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total EDF", len(edf_df))
c2.metric("Disponibles", len(available))
c3.metric("En PDV", len(placed))
c4.metric("Bajo 75%", len(under_75))

tab_repago, tab_clientes, tab_oportunidad, tab_rankings = st.tabs(["Repago", "Clientes", "Oportunidad EDF", "Rankings"])

with tab_repago:
    st.subheader("Listado de repago")
    filtered = render_filters(edf_df)
    repago_view = st.radio("Vista", ["Tarjetas celular", "Tabla completa"], horizontal=True, key="repago_view")
    if repago_view == "Tarjetas celular":
        render_card_list(
            filtered.sort_values(["% Repago", "Codigo cliente"], ascending=[True, True]),
            "repago",
        )
    else:
        st.dataframe(filtered, width="stretch", hide_index=True)
    st.download_button("Exportar listado CSV", csv_download(filtered), "repago_edf.csv", "text/csv")

with tab_clientes:
    st.subheader("Clientes")
    query = st.text_input("Buscar cliente o codigo", key="customer_query")
    filtered_customers = customer_df.copy()
    if query:
        q = query.lower()
        filtered_customers = filtered_customers[filtered_customers.apply(lambda row: q in " ".join(map(str, row.values)).lower(), axis=1)]
    clientes_view = st.radio("Vista", ["Tarjetas celular", "Tabla completa"], horizontal=True, key="clientes_view")
    if clientes_view == "Tarjetas celular":
        render_card_list(filtered_customers, "clientes")
    else:
        st.dataframe(filtered_customers, width="stretch", hide_index=True)
    st.download_button("Exportar clientes CSV", csv_download(filtered_customers), "clientes_edf.csv", "text/csv")

with tab_oportunidad:
    st.subheader("Oportunidad de colocacion por trimestre promedio")
    st.caption("Referencia: Slim desde 0.9 HL promedio mensual del trimestre; Vertical grande desde 1.875 HL promedio mensual del trimestre.")
    if not opportunity_df.empty:
        opp_filtered = render_opportunity_filters(opportunity_df)
        o1, o2, o3 = st.columns(3)
        o1.metric("Clientes/negocio", len(opp_filtered))
        o2.metric("Pueden colocar", int((opp_filtered["Puede colocar"] == "Si").sum()))
        o3.metric("HL promedio", round(float(opp_filtered["HL trimestre promedio"].sum()), 2) if not opp_filtered.empty else 0)
        opp_sorted = opp_filtered.sort_values(["Puede colocar", "HL trimestre promedio"], ascending=[False, False])
        opp_view = st.radio("Vista", ["Tarjetas celular", "Tabla completa"], horizontal=True, key="opp_view")
        if opp_view == "Tarjetas celular":
            render_card_list(opp_sorted, "opportunity")
        else:
            st.dataframe(opp_sorted, width="stretch", hide_index=True)
        st.download_button("Exportar oportunidad CSV", csv_download(opp_filtered), "oportunidad_edf.csv", "text/csv")
    else:
        st.info("No hay ventas trimestrales para evaluar oportunidades.")

with tab_rankings:
    st.subheader("Peores clientes por repago")
    if not placed.empty:
        ranking = (
            placed.groupby(["Codigo cliente", "Cliente", "Negocio", "Supervisor", "Promotor"], as_index=False)
            .agg(EDF=("Activo", "count"), RepagoPromedio=("% Repago", "mean"), HL=("HL", "sum"))
            .sort_values(["RepagoPromedio", "EDF"], ascending=[True, False])
            .head(50)
        )
        st.dataframe(ranking, width="stretch", hide_index=True)
        st.bar_chart(ranking.set_index("Cliente")["RepagoPromedio"].head(15))
    else:
        st.info("No hay EDF en PDV para rankear.")
