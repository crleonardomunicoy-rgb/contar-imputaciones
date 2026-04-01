import streamlit as st
import pandas as pd
import zipfile
import io
import os
import re
import pdfplumber

st.set_page_config(page_title="Contar - Compras + Padrón + Plan de Cuentas", layout="wide")

st.title("📊 Contar 2.0 - Procesamiento de Compras + Padrón + Plan de Cuentas")

# ---------------------------
# FUNCIONES
# ---------------------------

def limpiar_cuit(cuit):
    if pd.isna(cuit):
        return ""
    return re.sub(r"\D", "", str(cuit))

def formatear_fecha(fecha):
    try:
        return pd.to_datetime(fecha).strftime("%d/%m/%Y")
    except:
        return "-"

def limpiar_numero(valor):
    try:
        return float(valor)
    except:
        return "-"

# ---------------------------
# LECTURA DE COMPRAS DESDE ZIP
# ---------------------------

def procesar_zip(zip_file):
    dfs = []

    with zipfile.ZipFile(zip_file) as z:
        for file in z.namelist():
            if "comprobantes_compras" in file and file.endswith(".csv"):
                with z.open(file) as f:
                    df = pd.read_csv(f, sep=None, engine='python')

                    # LIMPIEZA BASE
                    df.columns = [c.strip() for c in df.columns]

                    # FECHA
                    if "Fecha de Emisión" in df.columns:
                        df["Fecha de Emisión"] = df["Fecha de Emisión"].apply(formatear_fecha)

                    # NUMÉRICOS
                    columnas_numericas = [
                        "Tipo de Comprobante",
                        "Punto de Venta",
                        "Número de Comprobante",
                        "Tipo Doc. Vendedor",
                        "Nro. Doc. Vendedor",
                        "Importe Total",
                        "Tipo de Cambio"
                    ]

                    for col in columnas_numericas:
                        if col in df.columns:
                            df[col] = pd.to_numeric(df[col], errors='coerce')

                    # LIMPIAR CEROS
                    df = df.fillna("-")

                    dfs.append(df)

    if dfs:
        return pd.concat(dfs, ignore_index=True)
    else:
        return pd.DataFrame()

# ---------------------------
# PADRÓN DE PROVEEDORES
# ---------------------------

def generar_padron(df):
    df["CUIT_Limpio"] = df["Nro. Doc. Vendedor"].apply(limpiar_cuit)

    padron = (
        df.groupby("CUIT_Limpio")
        .agg({
            "Denominación del Vendedor": "last",
            "Importe Total": "sum",
            "Nro. Doc. Vendedor": "count"
        })
        .reset_index()
    )

    padron.columns = [
        "CUIT",
        "Proveedor",
        "Importe Total",
        "Cantidad Comprobantes"
    ]

    return padron

# ---------------------------
# PLAN DE CUENTAS DESDE PDF
# ---------------------------

def leer_plan_cuentas_pdf(file):
    cuentas = []

    with pdfplumber.open(file) as pdf:
        texto_total = ""

        for page in pdf.pages:
            texto = page.extract_text()
            if texto:
                texto_total += texto + "\n"

    lineas = texto_total.split("\n")

    for linea in lineas:
        linea = linea.strip()

        if not linea:
            continue

        match = re.match(r"^([\d\.\-]+)\s+(.*)$", linea)

        if match:
            codigo = match.group(1).strip()
            nombre = match.group(2).strip()

            if len(nombre) > 2:
                cuentas.append({
                    "Codigo": codigo,
                    "Cuenta": nombre
                })

    df = pd.DataFrame(cuentas)
    df = df.drop_duplicates()

    return df

# ---------------------------
# INTERFAZ
# ---------------------------

st.header("1️⃣ Subir ZIP de Compras")
zip_file = st.file_uploader("Subir archivo ZIP de AFIP/ARCA", type=["zip"])

st.header("2️⃣ Subir Plan de Cuentas (PDF)")
plan_pdf = st.file_uploader("Subir PDF del Plan de Cuentas", type=["pdf"])

# ---------------------------
# PROCESAMIENTO
# ---------------------------

if zip_file:

    df_compras = procesar_zip(zip_file)

    if not df_compras.empty:

        st.success("✅ Compras procesadas")

        st.subheader("📋 Vista Compras")
        st.dataframe(df_compras.head(50))

        # PADRÓN
        padron = generar_padron(df_compras)

        st.subheader("📇 Padrón de Proveedores")
        st.dataframe(padron)

        # PLAN DE CUENTAS
        if plan_pdf:
            df_plan = leer_plan_cuentas_pdf(plan_pdf)

            st.subheader("📚 Plan de Cuentas Detectado")
            st.dataframe(df_plan)

        # EXPORTAR
        output = io.BytesIO()

        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_compras.to_excel(writer, sheet_name="Compras", index=False)
            padron.to_excel(writer, sheet_name="Padron", index=False)

            if plan_pdf:
                df_plan.to_excel(writer, sheet_name="Plan_Cuentas", index=False)

        st.download_button(
            label="📥 Descargar Excel Completo",
            data=output.getvalue(),
            file_name="compras_padron_plan.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    else:
        st.warning("No se encontraron datos de compras en el ZIP")
