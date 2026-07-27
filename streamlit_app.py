import json
from pathlib import Path

import pandas as pd
import streamlit as st

from edf_importer import DRIVE_URL, import_data


ROOT = Path(__file__).parent
DATA_PATH = ROOT / "data" / "db.json"


st.set_page_config(page_title="EDF Repago", page_icon="EDF", layout="wide")


def load_db_from_disk():
    if not DATA_PATH.exists():
        return None
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def load_db_from_upload(uploaded_file):
    if uploaded_file is None:
        return None
    return json.loads(uploaded_file.getvalue().decode("utf-8"))


def get_repayment(edf):
    repayment = edf.get("repayment") or {}
    return {
        "hl": repayment.get("hl") or 0,
        "pct": repayment.get("pct") or 0,
        "target": repayment.get("target") or 0,
        "minimum": repayment.get("minimum") or 0,
        "band": (repayment.get("band") or {}).get("label") or "",
    }


def status_label(status):
    labels = {
        "PDV": "En PDV",
        "DEPOSITO": "Deposito",
        "STOCK": "Stock",
        "REPARACION": "Reparacion",
        "BAJA DEFINITIVA": "Baja definitiva",
    }
    return labels.get(status or "", status or "-")


def build_edf_rows(db):
    rows = []
    for edf in db.get("edfs", []):
        customer = edf.get("customer") or {}
        repayment = get_repayment(edf)
        rows.append({
            "Cliente": customer.get("name") or "",
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
        })
    return pd.DataFrame(rows)


def build_customer_rows(db):
    rows = []
    for customer in db.get("customers", []):
        sales = customer.get("salesByBusiness") or {}
        rows.append({
            "Codigo": customer.get("id") or "",
            "Cliente": customer.get("name") or "",
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


def csv_download(df):
    return df.to_csv(index=False, sep=";").encode("utf-8-sig")


def render_filters(df):
    f1, f2, f3, f4 = st.columns(4)
    business = f1.selectbox("Negocio", ["Todos"] + sorted(df["Negocio"].dropna().unique().tolist()))
    supervisor = f2.selectbox("Supervisor", ["Todos"] + sorted(df["Supervisor"].dropna().unique().tolist()))
    promoter = f3.selectbox("Promotor", ["Todos"] + sorted(df["Promotor"].dropna().unique().tolist()))
    query = f4.text_input("Buscar")

    filtered = df.copy()
    if business != "Todos":
        filtered = filtered[filtered["Negocio"] == business]
    if supervisor != "Todos":
        filtered = filtered[filtered["Supervisor"] == supervisor]
    if promoter != "Todos":
        filtered = filtered[filtered["Promotor"] == promoter]
    if query:
        q = query.lower()
        filtered = filtered[filtered.apply(lambda row: q in " ".join(map(str, row.values)).lower(), axis=1)]
    return filtered


st.title("EDF Repago")
st.caption("Dashboard operativo by QπU")

with st.sidebar:
    st.header("Datos")
    uploaded = st.file_uploader("Subir db.json", type=["json"])
    st.caption("Tambien puede existir como data/db.json dentro del repo.")
    st.divider()
    st.header("Google Drive")
    drive_url = st.text_input("Carpeta Drive", value=DRIVE_URL)
    if st.button("Sincronizar Drive e importar"):
        try:
            with st.spinner("Leyendo Drive y generando base..."):
                db = import_data(sync=True, folder_url=drive_url)
            st.success("Base actualizada desde Drive.")
            st.rerun()
        except Exception as exc:
            st.error("No se pudo importar desde Drive.")
            st.exception(exc)

db = load_db_from_upload(uploaded) or load_db_from_disk()

if db is None:
    st.warning("Falta cargar la base del dashboard.")
    st.write("Subi el archivo `db.json` desde la barra lateral, o agregalo al repo en `data/db.json`.")
    st.stop()

edf_df = build_edf_rows(db)
customer_df = build_customer_rows(db)

placed = edf_df[edf_df["Estado"] == "En PDV"] if not edf_df.empty else edf_df
available = edf_df[edf_df["Estado"].isin(["Stock", "Deposito"])] if not edf_df.empty else edf_df
under_75 = placed[placed["% Repago"] < 75] if not placed.empty else placed

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total EDF", len(edf_df))
c2.metric("Disponibles", len(available))
c3.metric("En PDV", len(placed))
c4.metric("Bajo 75%", len(under_75))

tab_repago, tab_clientes, tab_rankings = st.tabs(["Repago", "Clientes", "Rankings"])

with tab_repago:
    st.subheader("Listado de repago")
    filtered = render_filters(edf_df)
    st.dataframe(filtered, width="stretch", hide_index=True)
    st.download_button("Exportar listado CSV", csv_download(filtered), "repago_edf.csv", "text/csv")

with tab_clientes:
    st.subheader("Clientes")
    query = st.text_input("Buscar cliente o codigo", key="customer_query")
    filtered_customers = customer_df.copy()
    if query:
        q = query.lower()
        filtered_customers = filtered_customers[filtered_customers.apply(lambda row: q in " ".join(map(str, row.values)).lower(), axis=1)]
    st.dataframe(filtered_customers, width="stretch", hide_index=True)
    st.download_button("Exportar clientes CSV", csv_download(filtered_customers), "clientes_edf.csv", "text/csv")

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
