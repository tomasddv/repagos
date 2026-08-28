import json
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import streamlit as st

from edf_importer import DRIVE_URL, import_data


ROOT = Path(__file__).parent
DATA_PATH = ROOT / "data" / "db.json"
MAIL_SETTINGS_PATH = ROOT / "data" / "mail_settings.json"
APP_VERSION = "periodo-sin-total-2026-08-03"

DEFAULT_TEMPLATES = {
    "COMODATO": "Buenas,\n\nSolicito gestionar el comodato de los siguientes EDF:\n\n{{edf_table}}\n\nGracias.",
    "CONTRA COMODATO": "Buenas,\n\nSolicito gestionar el contra comodato de los siguientes EDF:\n\n{{edf_table}}\n\nGracias.",
}


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


def load_mail_settings(db):
    supervisors = sorted({
        customer.get("supervisor") or "Sin supervisor"
        for customer in db.get("customers", [])
    })
    if MAIL_SETTINGS_PATH.exists():
        settings = json.loads(MAIL_SETTINGS_PATH.read_text(encoding="utf-8"))
    else:
        settings = {}
    saved_rows = {
        row.get("supervisor"): row.get("recipients", "")
        for row in settings.get("supervisorRecipients", [])
        if row.get("supervisor")
    }
    supervisor_rows = [
        {"supervisor": supervisor, "recipients": saved_rows.get(supervisor, "")}
        for supervisor in supervisors
    ]
    for supervisor, recipients in saved_rows.items():
        if supervisor not in supervisors:
            supervisor_rows.append({"supervisor": supervisor, "recipients": recipients})
    return {
        "supervisorRecipients": supervisor_rows,
        "templates": {**DEFAULT_TEMPLATES, **settings.get("templates", {})},
    }


def save_mail_settings(settings):
    MAIL_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    MAIL_SETTINGS_PATH.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")


def customer_name(customer):
    if not customer:
        return ""
    return customer.get("legalName") or customer.get("fantasyName") or customer.get("name") or ""


def build_mail_table(rows):
    lines = ["SKU EDF | Modelo | Nro de serie | Codigo cliente | Razon social"]
    for row in rows:
        lines.append(
            f"{row['SKU EDF']} | {row['Modelo']} | {row['Nro de serie']} | "
            f"{row['Codigo cliente']} | {row['Razon social']}"
        )
    return "\n".join(lines)


def build_mail_body(template, table_text):
    if "{{edf_table}}" in template:
        return template.replace("{{edf_table}}", table_text)
    return f"{template}\n\n{table_text}"


def mailto_url(recipients, subject, body):
    return f"mailto:{quote(recipients)}?subject={quote(subject)}&body={quote(body)}"


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

tab_repago, tab_clientes, tab_oportunidad, tab_rankings, tab_mails = st.tabs(["Repago", "Clientes", "Oportunidad EDF", "Rankings", "Mails"])

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

with tab_mails:
    st.subheader("Plantilla de solicitud EDF")
    st.caption("Los EDF y clientes salen de la misma base importada desde Drive.")
    mail_settings = load_mail_settings(db)
    customer_lookup = {str(customer.get("id")): customer for customer in db.get("customers", [])}

    settings_col, preview_col = st.columns([1, 1])
    with settings_col:
        request_type = st.selectbox("Tipo de solicitud", ["COMODATO", "CONTRA COMODATO"], key="mail_type")
        supervisor_options = [row["supervisor"] for row in mail_settings["supervisorRecipients"]]
        selected_supervisor = st.selectbox("Supervisor", supervisor_options, key="mail_supervisor")
        recipients_by_supervisor = {
            row["supervisor"]: row.get("recipients", "")
            for row in mail_settings["supervisorRecipients"]
        }
        recipients = st.text_input("Destinatarios", value=recipients_by_supervisor.get(selected_supervisor, ""), key="mail_recipients")

        st.markdown("**Buscar EDF**")
        mail_search_by = st.selectbox("Buscar EDF por", ["Todo", "SKU / activo", "Serie", "Codigo cliente"], key="mail_search_by")
        mail_query = st.text_input("Buscar EDF", placeholder="Serie, activo o codigo de cliente", key="mail_query")
        mail_df = edf_df.copy()
        if mail_query:
            q = mail_query.lower().strip()
            if mail_search_by == "SKU / activo":
                mail_df = mail_df[mail_df["Activo"].astype(str).str.lower().str.contains(q, na=False)]
            elif mail_search_by == "Serie":
                mail_df = mail_df[mail_df["Serie"].astype(str).str.lower().str.contains(q, na=False)]
            elif mail_search_by == "Codigo cliente":
                code_series = mail_df["Codigo cliente"].astype(str).str.replace(r"\.0$", "", regex=True).str.lower()
                mail_df = mail_df[code_series.str.startswith(q, na=False) | code_series.eq(q)]
            else:
                mail_df = mail_df[mail_df.apply(lambda row: q in " ".join(map(str, row.values)).lower(), axis=1)]
        mail_df = mail_df.head(150)
        option_labels = {}
        for index, row in enumerate(mail_df.to_dict("records")):
            label = (
                f"{row.get('Activo') or 'Sin SKU'} | {row.get('Serie') or 'Sin serie'} | "
                f"{row.get('Modelo')} | {row.get('Codigo cliente') or 'sin cliente'}"
            )
            option_labels[f"{label} #{index + 1}"] = row
        selected_labels = st.multiselect("EDF para incluir", list(option_labels.keys()), key="mail_selected_edfs")

        template = st.text_area(
            "Cuerpo base",
            value=mail_settings["templates"].get(request_type, DEFAULT_TEMPLATES[request_type]),
            height=220,
            key=f"mail_current_template_{request_type}",
        )

    selected_rows = []
    with preview_col:
        st.markdown("**Detalle EDF**")
        for index, label in enumerate(selected_labels):
            source = option_labels[label]
            edf_key = f"{source.get('Activo')}-{source.get('Serie')}-{index}"
            customer_code = str(source.get("Codigo cliente") or "")
            social_reason = str(source.get("Razon social") or source.get("Nombre fantasia") or source.get("Cliente") or "")
            if request_type == "COMODATO":
                customer_code = st.text_input(
                    f"Codigo cliente para {source.get('Serie') or source.get('Activo')}",
                    value="",
                    key=f"mail_customer_{edf_key}",
                )
                customer = customer_lookup.get(customer_code)
                social_reason = customer_name(customer)
            selected_rows.append({
                "SKU EDF": source.get("Activo") or "Sin SKU",
                "Modelo": source.get("Modelo") or "",
                "Nro de serie": source.get("Serie") or "",
                "Codigo cliente": customer_code,
                "Razon social": social_reason,
            })

        detail_df = pd.DataFrame(selected_rows)
        if not detail_df.empty:
            st.dataframe(detail_df, width="stretch", hide_index=True)
        else:
            st.info("Selecciona uno o mas EDF para armar el mail.")

    table_text = build_mail_table(selected_rows)
    body = build_mail_body(template, table_text)
    subject = f"[EDF] Solicitud {request_type} - {len(selected_rows)} equipo(s) - {selected_supervisor}"

    action_col1, action_col2 = st.columns([1, 1])
    with action_col1:
        if selected_rows:
            st.link_button("Abrir mail", mailto_url(recipients, subject, body))
        st.download_button("Descargar cuerpo TXT", body.encode("utf-8"), "solicitud_edf.txt", "text/plain")
    with action_col2:
        st.text_area("Mail generado", value=body, height=260, key="mail_generated_body")

    st.divider()
    st.markdown("**Destinatarios por supervisor**")
    recipients_df = pd.DataFrame(mail_settings["supervisorRecipients"])
    edited_recipients = st.data_editor(recipients_df, width="stretch", hide_index=True, num_rows="dynamic", key="mail_recipients_editor")

    st.markdown("**Plantillas guardadas**")
    template_comodato = st.text_area("Plantilla comodato", value=mail_settings["templates"].get("COMODATO", DEFAULT_TEMPLATES["COMODATO"]), height=160, key="mail_template_comodato")
    template_contra = st.text_area("Plantilla contra comodato", value=mail_settings["templates"].get("CONTRA COMODATO", DEFAULT_TEMPLATES["CONTRA COMODATO"]), height=160, key="mail_template_contra")
    if st.button("Guardar configuracion de mails"):
        saved_templates = {
            "COMODATO": template_comodato,
            "CONTRA COMODATO": template_contra,
        }
        saved_templates[request_type] = template
        saved_settings = {
            "supervisorRecipients": edited_recipients.fillna("").to_dict("records"),
            "templates": saved_templates,
        }
        save_mail_settings(saved_settings)
        st.success("Configuracion guardada.")
        st.rerun()
